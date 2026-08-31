"""
甲-A：DB primary → derived + runtime cache（單一衍生引擎，002 DB-centric）。

讀 DB 的 roads / accidents（primary，可被使用者在 DB 直接編輯）→
  - build_graph（拓撲修復）→ taiwan_graph.pkl（DB-centric 下 runtime 唯一需要的 pkl cache）
  - 重算風險（raw + normalized）→ 刷新 road_risk 表 + roads_with_risk view
  - 刷新 graph_nodes / graph_edges 表（給 QGIS；可 --skip-graph-tables 略過以加速）

roads 表本身是 primary，不動。搭配 USE_POSTGIS=true 服務：API 的 graph 讀 pkl、roads/risk 讀 DB。

典型流程：
  在 DB 編輯 roads / accidents  →  python -m scripts.rebuild_from_db  →  重啟 API
"""
import argparse
import logging
import os

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
    DEFAULT_DB_URL,
    create_view,
    load_graph_edges,
    load_graph_nodes,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rebuild_from_db")


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


def main() -> None:
    ap = argparse.ArgumentParser(description="Rebuild derived + cache from DB primary (002 甲-A)")
    ap.add_argument("--database-url", default=os.getenv("DATABASE_URL", DEFAULT_DB_URL))
    ap.add_argument("--skip-graph-tables", action="store_true",
                    help="略過 graph_nodes/graph_edges 表刷新（僅 QGIS 用；加速）")
    args = ap.parse_args()
    engine = make_engine(args.database_url)

    # 1. 讀 DB primary
    logger.info("讀 DB primary：roads / accidents ...")
    roads = load_roads_gdf_from_db(engine)
    accidents = load_accidents_from_db(engine)

    # 2. 拓撲修復 → pkl cache（runtime 用）
    logger.info("build_graph（拓撲修復）...")
    G = build_graph(roads)
    save_graph(G, settings.GRAPH_FILE_PATH)

    # 3. 重算風險 → 刷新 road_risk 表
    logger.info("重算風險 ...")
    raw_all, normalized = compute_risk_from_accidents(accidents, roads, settings)
    refresh_road_risk(engine, raw_all, normalized)

    # 4. 刷新 graph_* 表（QGIS）
    if not args.skip_graph_tables:
        load_graph_nodes(engine, G)
        load_graph_edges(engine, G)

    # 5. 重建 view
    create_view(engine)

    logger.info("完成：taiwan_graph.pkl + road_risk%s + roads_with_risk view",
                "" if args.skip_graph_tables else " + graph_nodes/edges")


if __name__ == "__main__":
    main()
