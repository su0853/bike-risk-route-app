"""
甲-A：DB primary → derived + runtime cache（單一衍生引擎，002 DB-centric）。

讀 DB 的 roads / accidents（primary，可被使用者在 DB 直接編輯）→
  - build_graph（拓撲修復）→ taiwan_graph.pkl（DB-centric 下 runtime 唯一需要的 pkl cache）
  - 重算風險（raw + normalized）→ 刷新 road_risk 表 + roads_with_risk view
  - 刷新 graph_nodes / graph_edges 表（給 QGIS；可 --skip-graph-tables 略過以加速）

**變動偵測（Phase 2）**：對 roads / accidents 各算內容指紋，與上次 build 的指紋（rebuild_meta 表）比對：
  - 都沒變        → 跳過（除非 --force）
  - 只有 accidents → 部分重建：只刷新 road_risk（跳過 build_graph，快）
  - roads 有變     → 完整重建
  --check 只報告 stale/fresh，不重建。

典型流程：在 DB 編輯 roads / accidents  →  python -m scripts.rebuild_from_db  →  重啟 API
"""
import argparse
import logging

import pandas as pd
from sqlalchemy import text

from app.config import settings
from app.services.db_source import (
    load_accidents_from_db,
    load_roads_gdf_from_db,
    make_engine,
)
from app.services.graph_builder import build_graph, save_graph
from app.services.risk_engine import compute_risk_from_accidents
from scripts.load_to_postgis import (
    create_view,
    load_graph_edges,
    load_graph_nodes,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rebuild_from_db")


# ── 變動偵測（指紋 + rebuild_meta）────────────────────────────

def _fingerprint(engine, table: str) -> str:
    """順序無關的內容指紋：count + Σ hashtext(整列)。任何內容變動都會改變。"""
    q = text(f"SELECT count(*)::text || ':' || coalesce(sum(hashtext(t::text)::bigint),0)::text "
             f"FROM {table} t")
    with engine.connect() as c:
        return c.execute(q).scalar()


def _ensure_meta(engine) -> None:
    with engine.begin() as c:
        c.execute(text("CREATE TABLE IF NOT EXISTS rebuild_meta ("
                       "name text PRIMARY KEY, roads_fp text, accidents_fp text, built_at timestamptz)"))


def _read_meta(engine) -> tuple[str | None, str | None]:
    with engine.connect() as c:
        row = c.execute(text("SELECT roads_fp, accidents_fp FROM rebuild_meta WHERE name='cache'")).first()
    return (row.roads_fp, row.accidents_fp) if row else (None, None)


def _write_meta(engine, roads_fp: str, accidents_fp: str) -> None:
    with engine.begin() as c:
        c.execute(text("INSERT INTO rebuild_meta(name, roads_fp, accidents_fp, built_at) "
                       "VALUES('cache', :r, :a, now()) "
                       "ON CONFLICT (name) DO UPDATE SET roads_fp=:r, accidents_fp=:a, built_at=now()"),
                  {"r": roads_fp, "a": accidents_fp})


# ── 衍生 ──────────────────────────────────────────────────

def refresh_road_risk(engine, raw_all: dict, normalized: dict) -> None:
    """把重算好的 raw + normalized 寫回 road_risk 表（先 DROP 相依 view）。"""
    df = pd.DataFrame(
        [(k, float(raw_all.get(k, 0.0)), float(normalized[k])) for k in normalized],
        columns=["osm_id", "raw_risk_density", "normalized_risk"],
    )
    with engine.begin() as c:
        c.execute(text("DROP VIEW IF EXISTS roads_with_risk CASCADE;"))
    df.to_sql("road_risk", engine, if_exists="replace", index=False, chunksize=50000)
    with engine.begin() as c:
        c.execute(text("ALTER TABLE road_risk ADD PRIMARY KEY (osm_id);"))
    logger.info("road_risk 刷新：%d 列（%d 筆 raw>0）", len(df), int((df.raw_risk_density > 0).sum()))


def rebuild_full(engine, skip_graph_tables: bool) -> None:
    """roads 變動：完整重建 graph pkl + road_risk (+ graph_* 表)。"""
    roads = load_roads_gdf_from_db(engine)
    accidents = load_accidents_from_db(engine)
    logger.info("build_graph（拓撲修復）...")
    G = build_graph(roads)
    save_graph(G, settings.GRAPH_FILE_PATH)
    raw_all, normalized = compute_risk_from_accidents(accidents, roads, settings)
    refresh_road_risk(engine, raw_all, normalized)
    if not skip_graph_tables:
        load_graph_nodes(engine, G)
        load_graph_edges(engine, G)
    create_view(engine)


def rebuild_risk_only(engine) -> None:
    """只有 accidents 變動：跳過 build_graph，只刷新 road_risk。"""
    roads = load_roads_gdf_from_db(engine)
    accidents = load_accidents_from_db(engine)
    raw_all, normalized = compute_risk_from_accidents(accidents, roads, settings)
    refresh_road_risk(engine, raw_all, normalized)
    create_view(engine)


def main() -> None:
    ap = argparse.ArgumentParser(description="Rebuild derived + cache from DB primary (002 甲-A, change-aware)")
    ap.add_argument("--database-url", default=settings.database_url)
    ap.add_argument("--check", action="store_true", help="只報告 stale/fresh，不重建")
    ap.add_argument("--force", action="store_true", help="無論指紋是否變動，強制完整重建")
    ap.add_argument("--skip-graph-tables", action="store_true",
                    help="略過 graph_nodes/graph_edges 表刷新（僅 QGIS 用；加速）")
    args = ap.parse_args()
    engine = make_engine(args.database_url)
    _ensure_meta(engine)

    cur_r = _fingerprint(engine, "roads")
    cur_a = _fingerprint(engine, "accidents")
    old_r, old_a = _read_meta(engine)
    roads_changed = cur_r != old_r
    acc_changed = cur_a != old_a
    logger.info("變動偵測：roads_changed=%s  accidents_changed=%s", roads_changed, acc_changed)

    if args.check:
        if not roads_changed and not acc_changed:
            logger.info("[--check] up-to-date（cache 與 DB primary 一致，無需 rebuild）")
        else:
            what = ", ".join([t for t, c in (("roads", roads_changed), ("accidents", acc_changed)) if c])
            logger.info("[--check] STALE：%s 有變動 → 需要 rebuild", what)
        return

    if not roads_changed and not acc_changed and not args.force:
        logger.info("primary 未變動，跳過（--force 可強制）")
        return

    if roads_changed or args.force:
        logger.info("完整重建（roads 變動或 --force）...")
        rebuild_full(engine, args.skip_graph_tables)
    else:
        logger.info("部分重建（僅 accidents 變動 → 只刷新 road_risk，跳過 build_graph）...")
        rebuild_risk_only(engine)

    _write_meta(engine, cur_r, cur_a)
    logger.info("完成並更新 rebuild_meta")


if __name__ == "__main__":
    main()
