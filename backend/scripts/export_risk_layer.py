"""
匯出風險分數圖層供 QGIS 視覺化。

輸入：
  data/processed/roads_gdf.pkl      ── 篩選後道路 GeoDataFrame (EPSG:3857)
  data/raw/accidents_epsg3857.gpkg  ── 原始事故資料 (ACCIDENTS_GPKG_PATH)

輸出：
  data/processed/risk_scores.gpkg
    圖層 risk_p95   ── P95 截斷正規化
    圖層 risk_p99   ── P99 截斷正規化（與 API 一致）
    圖層 risk_p995  ── P99.5 截斷正規化

欄位：
  osm_id, name, fclass, length_m, length_km,
  accident_count, weight_sum, raw_risk_density,
  normalized_risk, is_clipped

執行：
  cd backend && python scripts/export_risk_layer.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

from app.config import settings
from app.services.graph_builder import load_roads_gdf
from app.services.risk_engine import (
    assign_accidents_to_roads,
    compute_accident_weights,
    load_accidents,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("export_risk_layer")

OUTPUT_PATH = Path("data/processed/risk_scores.gpkg")
CLIP_PERCENTILES = {"p95": 95.0, "p99": 99.0, "p995": 99.5}


def build_risk_table(
    roads: gpd.GeoDataFrame,
    accidents_path: str,
) -> gpd.GeoDataFrame:
    """重跑事故→路段對應，回傳帶中間欄位的 GeoDataFrame。"""
    accidents = load_accidents(accidents_path)
    weights = compute_accident_weights(accidents, settings)
    joined = assign_accidents_to_roads(accidents, roads, settings.SNAP_TOLERANCE_M)

    joined = joined.copy()
    joined["weight"] = weights.values

    # 去除未對應的事故
    valid = joined.dropna(subset=["osm_id"])

    # 按 osm_id 統計事故數與權重和
    agg = valid.groupby("osm_id").agg(
        accident_count=("weight", "count"),
        weight_sum=("weight", "sum"),
    ).reset_index()
    agg["osm_id"] = agg["osm_id"].astype(str)

    # 合併到 roads
    roads_out = roads.copy()
    roads_out["osm_id"] = roads_out["osm_id"].astype(str)
    roads_out = roads_out.merge(agg, on="osm_id", how="left")
    roads_out["accident_count"] = roads_out["accident_count"].fillna(0).astype(int)
    roads_out["weight_sum"] = roads_out["weight_sum"].fillna(0.0)

    # raw risk density（每公里）
    length_km = roads_out.get("length_km")
    if length_km is None:
        roads_out["length_km"] = roads_out["length_m"] / 1000.0
    roads_out["raw_risk_density"] = roads_out["weight_sum"] / roads_out["length_km"].clip(lower=0.001)

    return roads_out


def add_normalized_layer(gdf: gpd.GeoDataFrame, clip_pct: float, col_prefix: str = "") -> gpd.GeoDataFrame:
    """在 gdf 上加入某個截斷點的正規化分數與 is_clipped 旗標。"""
    raw = gdf["raw_risk_density"].values
    nonzero = raw[raw > 0]

    if len(nonzero) == 0:
        gdf["normalized_risk"] = 0.0
        gdf["is_clipped"] = False
        return gdf

    clip_val = np.percentile(nonzero, clip_pct)
    gdf = gdf.copy()
    gdf["normalized_risk"] = np.minimum(raw / clip_val, 1.0)
    gdf["is_clipped"] = raw > clip_val

    logger.info(
        "P%.1f clip_val=%.4f  clipped=%d / %d segments (%.1f%%)",
        clip_pct,
        clip_val,
        gdf["is_clipped"].sum(),
        len(gdf),
        gdf["is_clipped"].mean() * 100,
    )
    return gdf


def main() -> None:
    logger.info("Loading roads GDF from %s", settings.ROADS_GDF_PATH)
    roads = load_roads_gdf(settings.ROADS_GDF_PATH)

    # 保留 QGIS 需要的欄位
    keep_cols = [c for c in ["osm_id", "name", "fclass", "length_m", "length_km", "geometry"] if c in roads.columns]
    roads = roads[keep_cols].copy()

    logger.info("Building risk table...")
    risk_table = build_risk_table(roads, settings.ACCIDENTS_GPKG_PATH)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    base_cols = ["osm_id", "name", "fclass", "length_m", "length_km",
                 "accident_count", "weight_sum", "raw_risk_density", "geometry"]
    base_cols = [c for c in base_cols if c in risk_table.columns]

    for layer_name, pct in CLIP_PERCENTILES.items():
        layer = add_normalized_layer(risk_table[base_cols].copy(), pct)
        layer.to_file(OUTPUT_PATH, layer=f"risk_{layer_name}", driver="GPKG")
        logger.info("Layer risk_%s written: %d rows", layer_name, len(layer))

    logger.info("Done → %s", OUTPUT_PATH)

    # 摘要統計
    ref = risk_table.copy()
    ref = add_normalized_layer(ref, 99.0)
    nonzero = ref[ref["normalized_risk"] > 0]
    logger.info(
        "\n  路段總數:         %d\n"
        "  有事故路段:       %d (%.1f%%)\n"
        "  事故總筆數:       %d\n"
        "  risk_density p50: %.4f\n"
        "  risk_density p99: %.4f\n"
        "  risk_density max: %.4f",
        len(ref),
        len(nonzero),
        len(nonzero) / len(ref) * 100,
        ref["accident_count"].sum(),
        np.percentile(nonzero["raw_risk_density"], 50) if len(nonzero) else 0,
        np.percentile(nonzero["raw_risk_density"], 99) if len(nonzero) else 0,
        ref["raw_risk_density"].max(),
    )


if __name__ == "__main__":
    main()
