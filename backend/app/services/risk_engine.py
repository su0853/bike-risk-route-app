import json
import logging
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from app.config import Settings

logger = logging.getLogger(__name__)


def load_accidents(gpkg_path: str) -> gpd.GeoDataFrame:
    """讀取已 Snap 完成的事故 GPKG，確保 CRS 為 EPSG:3857。"""
    logger.info("Loading accidents from %s", gpkg_path)
    gdf = gpd.read_file(gpkg_path)

    if gdf.crs is None or gdf.crs.to_epsg() != 3857:
        gdf = gdf.to_crs(epsg=3857)

    # 解析 datetime
    if "accident_datetime" in gdf.columns:
        gdf["accident_datetime"] = pd.to_datetime(gdf["accident_datetime"], errors="coerce")
    else:
        # 嘗試自動偵測日期欄位
        for col in ["date", "事故日期", "datetime"]:
            if col in gdf.columns:
                gdf["accident_datetime"] = pd.to_datetime(gdf[col], errors="coerce")
                break

    # 確保 death/injury 欄位存在
    for field, candidates in {
        "death_count": ["death_count", "deaths", "死亡人數", "fatalities"],
        "injury_count": ["injury_count", "injuries", "受傷人數"],
        "case_type": ["case_type", "accident_type", "事故類型", "A1A2"],
    }.items():
        if field not in gdf.columns:
            for c in candidates:
                if c in gdf.columns:
                    gdf[field] = gdf[c]
                    break

    # 移除無效座標
    before = len(gdf)
    gdf = gdf.dropna(subset=["geometry", "accident_datetime"]).copy()
    logger.info("Accidents loaded: %d (dropped %d invalid)", len(gdf), before - len(gdf))

    return gdf


def compute_accident_weights(gdf: gpd.GeoDataFrame, settings: Settings) -> pd.Series:
    """
    計算每筆事故的複合風險權重：weight = severity × time_decay

    事故類型定義（法規）：
      A1：當場或 24 小時內死亡的事故
      A2：受傷，或超過 24 小時後死亡的事故（仍可能有死亡）

    嚴重程度依 case_type 分別計算：
      A1: death × RISK_A1_DEATH_WEIGHT + injury × RISK_A1_INJURY_WEIGHT
      A2: death × RISK_A2_DEATH_WEIGHT + injury × RISK_A2_INJURY_WEIGHT
    """
    reference_date = datetime.now()

    deaths = gdf.get("death_count", pd.Series(0, index=gdf.index)).fillna(0).astype(float)
    injuries = gdf.get("injury_count", pd.Series(0, index=gdf.index)).fillna(0).astype(float)
    case_type = gdf.get("case_type", pd.Series("A2", index=gdf.index)).fillna("A2").astype(str)

    is_a1 = case_type.str.upper().str.contains("A1", na=False)

    # A1：24h 內死亡最嚴重，受傷也在更危險的事故情境下
    a1_severity = deaths * settings.RISK_A1_DEATH_WEIGHT + injuries * settings.RISK_A1_INJURY_WEIGHT
    # A2：24h 後死亡次嚴重，受傷為基準
    a2_severity = deaths * settings.RISK_A2_DEATH_WEIGHT + injuries * settings.RISK_A2_INJURY_WEIGHT

    severity = pd.Series(0.0, index=gdf.index)
    severity[is_a1] = a1_severity[is_a1]
    severity[~is_a1] = a2_severity[~is_a1]

    # 時間衰減（指數衰減，半衰期 RISK_DECAY_HALF_LIFE_YEARS 年）
    decay_lambda = np.log(2) / settings.RISK_DECAY_HALF_LIFE_YEARS
    years_ago = (reference_date - gdf["accident_datetime"]).dt.days / 365.25
    time_decay = np.exp(-decay_lambda * years_ago.clip(lower=0))

    weights = severity * time_decay
    logger.info(
        "Weights computed: A1=%d件 A2=%d件 mean=%.4f max=%.4f nonzero=%d",
        is_a1.sum(),
        (~is_a1).sum(),
        weights.mean(),
        weights.max(),
        (weights > 0).sum(),
    )
    return weights


def assign_accidents_to_roads(
    accidents: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    tolerance_m: float = 20.0,
) -> gpd.GeoDataFrame:
    """
    使用 gpd.sjoin_nearest 將事故對應到最近道路路段。
    加入 matched_osm_id 欄位；超出 tolerance 的標記為 None。
    """
    logger.info(
        "Assigning %d accidents to %d road segments (tolerance=%.1fm)...",
        len(accidents),
        len(roads),
        tolerance_m,
    )

    # sjoin_nearest 需要相同 CRS
    roads_indexed = roads[["osm_id", "geometry"]].copy().reset_index(drop=True)

    joined = gpd.sjoin_nearest(
        accidents[["accident_datetime", "death_count", "injury_count", "geometry"]],
        roads_indexed,
        how="left",
        max_distance=tolerance_m,
        distance_col="snap_distance_m",
    )

    # 去重：同一事故可能因等距而匹配到多條道路，保留第一筆
    if len(joined) > len(accidents):
        logger.info("Removing %d duplicate matches from sjoin_nearest", len(joined) - len(accidents))
        joined = joined.groupby(joined.index).first()

    # 超出容差的事故
    out_of_tolerance = joined["osm_id"].isna().sum()
    success_rate = (1 - out_of_tolerance / len(accidents)) * 100
    logger.info(
        "Snap success: %.2f%% (%d/%d within %.1fm)",
        success_rate,
        len(accidents) - out_of_tolerance,
        len(accidents),
        tolerance_m,
    )

    return joined


def aggregate_edge_risk(
    joined: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    weights: pd.Series,
) -> dict[str, float]:
    """
    依 osm_id 累加風險權重，除以路段長度(km) → 風險密度。
    回傳 {osm_id: raw_risk_density}。
    """
    joined = joined.copy()
    joined["weight"] = weights.values

    # 移除未對應成功的事故
    valid = joined.dropna(subset=["osm_id"])

    # 累加權重
    risk_sum = valid.groupby("osm_id")["weight"].sum()

    # 建立 osm_id → length_km 映射
    length_map = roads.set_index("osm_id")["length_km"]

    # 計算密度 (per km)
    risk_density = {}
    for osm_id, total_weight in risk_sum.items():
        length_km = length_map.get(osm_id, 0.1)  # 預設 0.1km 避免除零
        risk_density[str(osm_id)] = total_weight / max(length_km, 0.001)

    logger.info(
        "Risk density computed for %d road segments (out of %d total)",
        len(risk_density),
        len(roads),
    )
    return risk_density


def normalize_risk_scores(
    raw_scores: dict[str, float],
    clip_percentile: float = 99.0,
) -> dict[str, float]:
    """P99 截斷後縮放到 [0, 1]。"""
    values = np.array(list(raw_scores.values()))
    nonzero = values[values > 0]

    if len(nonzero) == 0:
        logger.warning("All risk scores are zero — normalization skipped")
        return {k: 0.0 for k in raw_scores}

    clip_val = np.percentile(nonzero, clip_percentile)
    logger.info(
        "Normalization clip value (P%.0f): %.4f, max raw: %.4f",
        clip_percentile,
        clip_val,
        values.max(),
    )

    normalized = {k: float(min(v / clip_val, 1.0)) for k, v in raw_scores.items()}
    return normalized


def build_risk_scores(
    gpkg_path: str,
    roads: gpd.GeoDataFrame,
    settings: Settings,
) -> dict[str, float]:
    """主入口：load → weights → assign → aggregate → normalize。"""
    accidents = load_accidents(gpkg_path)
    weights = compute_accident_weights(accidents, settings)
    joined = assign_accidents_to_roads(accidents, roads, settings.SNAP_TOLERANCE_M)
    raw_scores = aggregate_edge_risk(joined, roads, weights)

    # 初始化所有路段為 0
    all_scores = {str(osm_id): 0.0 for osm_id in roads["osm_id"]}
    all_scores.update(raw_scores)

    normalized = normalize_risk_scores(all_scores, settings.RISK_CLIP_PERCENTILE)

    nonzero = sum(1 for v in normalized.values() if v > 0)
    logger.info(
        "Risk scores: total=%d, nonzero=%d, max=%.4f",
        len(normalized),
        nonzero,
        max(normalized.values()),
    )
    return normalized


def save_risk_scores(scores: dict[str, float], filepath: str) -> None:
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(scores, f)
    logger.info("Risk scores saved to %s (%d entries)", filepath, len(scores))


def load_risk_scores(filepath: str) -> dict[str, float]:
    with open(filepath, encoding="utf-8") as f:
        scores = json.load(f)
    logger.info("Risk scores loaded: %d entries", len(scores))
    return scores
