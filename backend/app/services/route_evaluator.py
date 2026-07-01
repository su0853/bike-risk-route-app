import logging

import geopandas as gpd
import networkx as nx
import polyline as polyline_lib
from pyproj import Transformer
from shapely.geometry import Point

from app.services.google_routes import extract_route_distance_m, extract_route_polyline
from app.services.path_planner import categorize_risk

logger = logging.getLogger(__name__)

_transformer_to_3857 = Transformer.from_crs(4326, 3857, always_xy=True)
_transformer_to_wgs84 = Transformer.from_crs(3857, 4326, always_xy=True)


def _decode_polyline_to_gdf(encoded: str) -> gpd.GeoDataFrame:
    """Decode Google encoded polyline → GeoDataFrame (EPSG:3857)。"""
    # polyline.decode() 回傳 [(lat, lon), ...]
    points_latlon = polyline_lib.decode(encoded)
    geometries = []
    for lat, lon in points_latlon:
        x, y = _transformer_to_3857.transform(lon, lat)
        geometries.append(Point(x, y))

    gdf = gpd.GeoDataFrame(geometry=geometries, crs="EPSG:3857")
    return gdf


def _match_points_to_roads(
    points_gdf: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    tolerance_m: float = 20.0,
) -> list[str]:
    """將路線點對應到道路 osm_id，去重相鄰重複，回傳 osm_id 列表。"""
    if len(points_gdf) == 0:
        return []

    joined = gpd.sjoin_nearest(
        points_gdf,
        roads[["osm_id", "geometry"]],
        how="left",
        max_distance=tolerance_m,
    )

    osm_ids = joined["osm_id"].dropna().astype(str).tolist()

    # 去重相鄰重複
    deduped: list[str] = []
    for oid in osm_ids:
        if not deduped or deduped[-1] != oid:
            deduped.append(oid)

    return deduped


def _build_route_geometry(osm_ids: list[str], roads: gpd.GeoDataFrame) -> tuple[dict, list]:
    """從 osm_id 列表取得路線幾何，回傳 GeoJSON 和 waypoints。"""
    if not osm_ids:
        return {"type": "LineString", "coordinates": []}, []

    roads_indexed = roads.set_index("osm_id")
    coords_wgs84 = []

    for oid in osm_ids:
        if oid not in roads_indexed.index:
            continue
        geom = roads_indexed.loc[oid, "geometry"]
        for x, y in geom.coords:
            lon, lat = _transformer_to_wgs84.transform(x, y)
            coords_wgs84.append([lon, lat])

    # 去重相鄰重複座標
    deduped_coords = []
    for c in coords_wgs84:
        if not deduped_coords or deduped_coords[-1] != c:
            deduped_coords.append(c)

    geometry = {"type": "LineString", "coordinates": deduped_coords}
    waypoints = [[lat, lon] for lon, lat in deduped_coords]
    return geometry, waypoints


def _compute_risk_from_osm_ids(
    osm_ids: list[str],
    roads: gpd.GeoDataFrame,
    risk_scores: dict[str, float],
) -> dict:
    """計算 osm_id 列表的長度加權風險平均（不含幾何，內部使用）。"""
    roads_indexed = roads.set_index("osm_id")
    total_distance_m = 0.0
    weighted_risk_sum = 0.0

    for oid in osm_ids:
        if oid not in roads_indexed.index:
            continue
        row = roads_indexed.loc[oid]
        # 若同 osm_id 有多筆（原始路段被切割），取第一筆長度
        length_m = float(row["length_m"].iloc[0] if hasattr(row["length_m"], "iloc") else row["length_m"])
        risk = risk_scores.get(oid, 0.0)
        total_distance_m += length_m
        weighted_risk_sum += risk * length_m

    total_risk_score = (weighted_risk_sum / total_distance_m) if total_distance_m > 0 else 0.0
    return {
        "total_distance_m": total_distance_m,
        "total_risk_score": total_risk_score,
        "risk_category": categorize_risk(total_risk_score),
    }


def compute_route_stats_from_osm_ids(
    osm_ids: list[str],
    roads: gpd.GeoDataFrame,
    risk_scores: dict[str, float],
) -> dict:
    """計算路線距離、長度加權風險平均及幾何（供安全路線使用）。"""
    stats = _compute_risk_from_osm_ids(osm_ids, roads, risk_scores)
    geometry, waypoints = _build_route_geometry(osm_ids, roads)
    return {**stats, "geometry": geometry, "waypoints": waypoints}


def evaluate_google_route(
    route: dict,
    roads: gpd.GeoDataFrame,
    risk_scores: dict[str, float],
    snap_tolerance_m: float = 20.0,
    route_index: int = 0,
) -> dict | None:
    """評估單條 Google 路線的風險分數。

    顯示幾何：直接使用 Google polyline 解碼座標（方向正確，無鋸齒）
    距離：使用 Google 回傳的 distanceMeters（準確）
    風險分數：將 polyline 點 snap 到道路段，計算長度加權風險平均
    """
    encoded = extract_route_polyline(route)
    if not encoded:
        return None

    # ── 顯示幾何：直接解碼 polyline，不透過道路段重建 ──────────────────────
    points_latlon = polyline_lib.decode(encoded)  # [(lat, lon), ...]
    geometry = {
        "type": "LineString",
        "coordinates": [[lon, lat] for lat, lon in points_latlon],
    }
    waypoints = [[lat, lon] for lat, lon in points_latlon]

    # ── 距離：使用 Google 回傳值（比用路段長度累加準確）───────────────────
    google_distance_m = extract_route_distance_m(route)

    # ── 風險分數：snap polyline 點到道路段，計算加權平均 ─────────────────
    points_gdf = _decode_polyline_to_gdf(encoded)
    osm_ids = _match_points_to_roads(points_gdf, roads, snap_tolerance_m)

    if not osm_ids:
        logger.warning("No roads matched for google route %d", route_index)
        # 無法計算風險但仍回傳路線（風險設為 0）
        return {
            "route_type": f"google_{route_index}",
            "geometry": geometry,
            "waypoints": waypoints,
            "total_distance_m": google_distance_m,
            "total_risk_score": 0.0,
            "risk_category": categorize_risk(0.0),
        }

    risk_stats = _compute_risk_from_osm_ids(osm_ids, roads, risk_scores)

    result = {
        "route_type": f"google_{route_index}",
        "geometry": geometry,
        "waypoints": waypoints,
        "total_distance_m": google_distance_m if google_distance_m > 0 else risk_stats["total_distance_m"],
        "total_risk_score": risk_stats["total_risk_score"],
        "risk_category": risk_stats["risk_category"],
    }

    logger.info(
        "Google route %d: %.0fm, risk=%.3f (%s), matched %d segments",
        route_index,
        result["total_distance_m"],
        result["total_risk_score"],
        result["risk_category"],
        len(osm_ids),
    )
    return result


def evaluate_all_routes(
    google_routes: list[dict],
    roads: gpd.GeoDataFrame,
    risk_scores: dict[str, float],
    safety_route: dict | None,
    snap_tolerance_m: float = 20.0,
) -> list[dict]:
    """合併 Google 路線與安全優化路線，按風險分數排序。"""
    results: list[dict] = []

    if safety_route:
        results.append(safety_route)

    for i, route in enumerate(google_routes):
        evaluated = evaluate_google_route(route, roads, risk_scores, snap_tolerance_m, i)
        if evaluated:
            results.append(evaluated)

    # 按風險分數排序（低 → 高）
    results.sort(key=lambda r: r["total_risk_score"])
    return results
