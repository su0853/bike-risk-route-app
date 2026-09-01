"""
將既有 pipeline 產物載入 PostGIS（002 Wave 1）。

定位：PostGIS 作為真相來源 / 查詢 / QGIS 圖層；API runtime 目前不依賴它。
本 script 為一次性、冪等匯入（if_exists="replace"）。

資料來源（刻意不讀 roads_gdf.pkl —— 它跨 pandas 版本無法反序列化，見 docs/data_dictionary.md）：
  roads        ← load_and_filter_roads(現算，避開壞掉的 pkl)
  accidents    ← accidents_epsg3857.gpkg
  road_risk    ← risk_scores.json(normalized) + aggregate_edge_risk 重算 raw
  graph_nodes  ← taiwan_graph.pkl
  graph_edges  ← taiwan_graph.pkl

連線：預設 localhost:5432（host 端執行 / QGIS）。容器內執行時由 DATABASE_URL(env) 覆蓋為 host=postgis。

用法：
  # host 端（後端 venv，已 pip install -e ".[db]"）
  python -m scripts.load_to_postgis                       # 全部表
  python -m scripts.load_to_postgis --tables roads,accidents,road_risk
  # 容器內
  docker compose run --rm backend python -m scripts.load_to_postgis
"""
import argparse
import json
import logging

import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import Point
from sqlalchemy import create_engine, text

from app.config import settings
from app.services import risk_engine
from app.services.graph_builder import load_and_filter_roads, load_graph

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("load_to_postgis")

ALL_TABLES = ["roads", "accidents", "road_risk", "graph_nodes", "graph_edges"]
SRID = settings.CRS_METRIC  # 3857


def get_engine(url: str):
    logger.info("Connecting: %s", url.rsplit("@", 1)[-1])  # 不印帳密
    return create_engine(url)


def _exec(engine, *statements: str) -> None:
    with engine.begin() as conn:
        for s in statements:
            conn.execute(text(s))


def ensure_postgis(engine) -> None:
    _exec(engine, "CREATE EXTENSION IF NOT EXISTS postgis;")


def _node_id(n: tuple) -> str:
    """(rounded_x, rounded_y) tuple → 'rx_ry' text（SQL 存不了 tuple）。"""
    return f"{n[0]}_{n[1]}"


# ── 各表載入 ──────────────────────────────────────────────

def load_roads(engine) -> gpd.GeoDataFrame:
    logger.info("roads: load_and_filter_roads（現算，不讀 pkl）...")
    roads = load_and_filter_roads(settings.ROADS_GPKG_PATH, settings.EXCLUDED_FCLASSES)
    cols = ["osm_id", "fclass", "name", "oneway", "length_m", "length_km", "geometry"]
    g = roads[[c for c in cols if c in roads.columns]].copy().rename_geometry("geom")
    logger.info("roads: 寫入 %d 筆...", len(g))
    g.to_postgis("roads", engine, if_exists="replace", index=False, chunksize=50000)
    _exec(
        engine,
        "ALTER TABLE roads ADD COLUMN road_id BIGSERIAL PRIMARY KEY;",
        "CREATE INDEX roads_osm_id_idx ON roads (osm_id);",
        "CREATE INDEX roads_geom_gix ON roads USING GIST (geom);",
    )
    logger.info("roads: 完成（road_id PK + osm_id/GIST 索引）")
    return roads  # 供 road_risk 重用（省一次讀取）


def load_accidents(engine) -> None:
    logger.info("accidents: 讀 %s ...", settings.ACCIDENTS_GPKG_PATH)
    a = gpd.read_file(settings.ACCIDENTS_GPKG_PATH).rename_geometry("geom")
    logger.info("accidents: 寫入 %d 筆...", len(a))
    a.to_postgis("accidents", engine, if_exists="replace", index=False, chunksize=50000)
    _exec(
        engine,
        "ALTER TABLE accidents ADD COLUMN accident_id BIGSERIAL PRIMARY KEY;",
        "CREATE INDEX accidents_geom_gix ON accidents USING GIST (geom);",
    )
    logger.info("accidents: 完成（accident_id PK + GIST）")


def load_road_risk(engine, roads: gpd.GeoDataFrame | None) -> None:
    logger.info("road_risk: 載 normalized + 重算 raw density...")
    normalized = json.loads(open(settings.RISK_SCORES_PATH, encoding="utf-8").read())

    if roads is None:
        roads = load_and_filter_roads(settings.ROADS_GPKG_PATH, settings.EXCLUDED_FCLASSES)
    acc = risk_engine.load_accidents(settings.ACCIDENTS_GPKG_PATH)
    weights = risk_engine.compute_accident_weights(acc, settings)
    joined = risk_engine.assign_accidents_to_roads(acc, roads, settings.SNAP_TOLERANCE_M)
    raw = risk_engine.aggregate_edge_risk(joined, roads, weights)  # {osm_id(str): raw_density}

    df = pd.DataFrame(
        [(k, float(raw.get(k, 0.0)), float(v)) for k, v in normalized.items()],
        columns=["osm_id", "raw_risk_density", "normalized_risk"],
    )
    logger.info("road_risk: 寫入 %d 筆（%d 筆有 raw>0）...", len(df), int((df.raw_risk_density > 0).sum()))
    df.to_sql("road_risk", engine, if_exists="replace", index=False, chunksize=50000)
    _exec(engine, "ALTER TABLE road_risk ADD PRIMARY KEY (osm_id);")
    logger.info("road_risk: 完成（osm_id PK）")


def load_graph_nodes(engine, G: nx.MultiGraph) -> None:
    logger.info("graph_nodes: 建 %d 節點...", G.number_of_nodes())
    rows = [{"node_id": _node_id(n), "x": d["x"], "y": d["y"], "geom": Point(d["x"], d["y"])}
            for n, d in G.nodes(data=True)]
    g = gpd.GeoDataFrame(rows, geometry="geom", crs=SRID)
    g.to_postgis("graph_nodes", engine, if_exists="replace", index=False, chunksize=100000)
    _exec(
        engine,
        "ALTER TABLE graph_nodes ADD PRIMARY KEY (node_id);",
        "CREATE INDEX graph_nodes_geom_gix ON graph_nodes USING GIST (geom);",
    )
    logger.info("graph_nodes: 完成（node_id PK + GIST）")


def load_graph_edges(engine, G: nx.MultiGraph) -> None:
    logger.info("graph_edges: 建 %d 邊...", G.number_of_edges())
    rows = [{
        "source_node_id": _node_id(u),
        "target_node_id": _node_id(v),
        "osm_id": str(d.get("osm_id", "")),
        "oneway": d.get("oneway", ""),
        "length_m": float(d.get("length_m", 0.0)),
        "geom": d.get("geometry"),
    } for u, v, d in G.edges(data=True)]
    g = gpd.GeoDataFrame(rows, geometry="geom", crs=SRID)
    g.to_postgis("graph_edges", engine, if_exists="replace", index=False, chunksize=100000)
    _exec(
        engine,
        "ALTER TABLE graph_edges ADD COLUMN edge_id BIGSERIAL PRIMARY KEY;",
        "CREATE INDEX graph_edges_geom_gix ON graph_edges USING GIST (geom);",
        "CREATE INDEX graph_edges_osm_id_idx ON graph_edges (osm_id);",
    )
    logger.info("graph_edges: 完成（edge_id PK + GIST + osm_id 索引）")


def create_view(engine) -> None:
    _exec(engine, """
        CREATE OR REPLACE VIEW roads_with_risk AS
        SELECT r.road_id, r.osm_id, r.fclass, r.length_m,
               rr.raw_risk_density, rr.normalized_risk, r.geom
        FROM roads r LEFT JOIN road_risk rr USING (osm_id);
    """)
    logger.info("view roads_with_risk: 完成")


def main() -> None:
    ap = argparse.ArgumentParser(description="Load pipeline artifacts into PostGIS (002 Wave 1)")
    ap.add_argument("--database-url", default=settings.database_url)
    ap.add_argument("--tables", default=",".join(ALL_TABLES),
                    help=f"逗號分隔，可選：{','.join(ALL_TABLES)}（預設全部）")
    args = ap.parse_args()
    tables = [t.strip() for t in args.tables.split(",") if t.strip()]

    engine = get_engine(args.database_url)
    ensure_postgis(engine)

    # roads/road_risk 有 view 相依 → 先 DROP VIEW 才能 replace
    if {"roads", "road_risk"} & set(tables):
        _exec(engine, "DROP VIEW IF EXISTS roads_with_risk CASCADE;")

    roads_gdf = None
    if "roads" in tables:
        roads_gdf = load_roads(engine)
    if "accidents" in tables:
        load_accidents(engine)
    if "road_risk" in tables:
        load_road_risk(engine, roads_gdf)

    if {"graph_nodes", "graph_edges"} & set(tables):
        logger.info("載入 graph pkl（%s）...", settings.GRAPH_FILE_PATH)
        G = load_graph(settings.GRAPH_FILE_PATH)
        if "graph_nodes" in tables:
            load_graph_nodes(engine, G)
        if "graph_edges" in tables:
            load_graph_edges(engine, G)

    # 只有在載入 road_risk 時才建 view（否則 road_risk 表可能尚不存在，如 bootstrap 的
    # --tables roads,accidents；那條路徑的 view 由後續 rebuild_from_db 建立）
    if "road_risk" in tables:
        create_view(engine)

    logger.info("完成：%s", ", ".join(tables))


if __name__ == "__main__":
    main()
