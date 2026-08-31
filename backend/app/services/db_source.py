"""
從 PostGIS 載入 runtime 資料（002 Wave 2）。

只在 settings.USE_POSTGIS 開啟時使用；否則 runtime 照舊讀 pkl/json。
graph 仍走 pkl（NetworkX 不從 DB 建）；這裡只載 roads_gdf 與 risk_scores。
需要 [db] 依賴（sqlalchemy / geoalchemy2 / psycopg）與已跑過 load_to_postgis 的 DB。
"""
import logging

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def make_engine(url: str):
    """建立 SQLAlchemy engine（含連線 pre-ping，避免死連線）。"""
    return create_engine(url, pool_pre_ping=True)


def load_roads_gdf_from_db(engine) -> gpd.GeoDataFrame:
    """
    從 roads 表載入 GeoDataFrame，作為 load_roads_gdf(pkl) 的替代。

    幾何欄回命名為 "geometry"（route_evaluator 依此名取用），CRS 由 DB 的 SRID(3857) 帶入。
    """
    gdf = gpd.read_postgis(
        "SELECT osm_id, fclass, name, oneway, length_m, length_km, geom FROM roads",
        engine,
        geom_col="geom",
    )
    gdf = gdf.rename_geometry("geometry")
    logger.info("Roads GDF loaded from PostGIS: %d rows", len(gdf))
    return gdf


def load_risk_scores_from_db(engine) -> dict[str, float]:
    """從 road_risk 表載入 {osm_id: normalized_risk}，作為 load_risk_scores(json) 的替代。"""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT osm_id, normalized_risk FROM road_risk")).all()
    scores = {str(osm_id): float(v) for osm_id, v in rows}
    logger.info("Risk scores loaded from PostGIS: %d entries", len(scores))
    return scores


def load_accidents_from_db(engine) -> gpd.GeoDataFrame:
    """
    從 accidents 表載入 GeoDataFrame，作為 risk_engine.load_accidents(gpkg) 的替代（002 甲-A）。

    對齊 load_accidents 的輸出：幾何欄命名 "geometry"、CRS 3857、accident_datetime 為 datetime、
    去除無效座標/時間。供 rebuild_from_db 從 DB primary 重算風險。
    """
    gdf = gpd.read_postgis(
        "SELECT case_type, accident_datetime, death_count, injury_count, location, geom FROM accidents",
        engine,
        geom_col="geom",
    )
    gdf = gdf.rename_geometry("geometry")
    gdf["accident_datetime"] = pd.to_datetime(gdf["accident_datetime"], errors="coerce")
    before = len(gdf)
    gdf = gdf.dropna(subset=["geometry", "accident_datetime"]).copy()
    logger.info("Accidents loaded from PostGIS: %d (dropped %d invalid)", len(gdf), before - len(gdf))
    return gdf
