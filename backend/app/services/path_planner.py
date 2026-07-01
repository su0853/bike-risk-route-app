import logging

import networkx as nx
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge

from app.services.graph_builder import get_nearest_node

logger = logging.getLogger(__name__)

_transformer_to_wgs84 = Transformer.from_crs(3857, 4326, always_xy=True)


def _edge_length(edge_data: dict) -> float:
    return float(edge_data.get("length_m", 1.0))


def apply_risk_weights(
    G: nx.MultiGraph,
    risk_scores: dict[str, float],
    lambda_coef: float = 0.5,
) -> nx.MultiGraph:
    """
    回傳 G 的副本，加上 risk_weight 邊屬性：
    risk_weight = length_m × (1 + λ × normalized_risk)
    以邊的 osm_id (str) 查詢 risk_scores。
    """
    G_w = G.copy()
    for u, v, k, data in G_w.edges(data=True, keys=True):
        osm_id = data.get("osm_id")
        risk = risk_scores.get(str(osm_id), 0.0) if osm_id else 0.0
        length_m = _edge_length(data)
        G_w[u][v][k]["risk_weight"] = length_m * (1.0 + lambda_coef * risk)
    return G_w


def compute_route_stats(
    node_path: list,
    G: nx.MultiGraph,
    risk_scores: dict[str, float],
) -> dict:
    """從節點路徑計算總距離、長度加權風險分數、幾何及路標（WGS84）。"""
    geometries = []
    total_distance_m = 0.0
    weighted_risk_sum = 0.0

    for i in range(len(node_path) - 1):
        u, v = node_path[i], node_path[i + 1]
        edge_data = min(G[u][v].values(), key=_edge_length)

        length_m = _edge_length(edge_data)
        risk = risk_scores.get(str(edge_data.get("osm_id", "")), 0.0)

        total_distance_m += length_m
        weighted_risk_sum += risk * length_m

        geom = edge_data.get("geometry")
        if geom is not None:
            # 確認幾何方向與遍歷方向一致（起點應靠近節點 u）
            u_xy = (G.nodes[u]["x"], G.nodes[u]["y"])
            g_start = geom.coords[0]
            g_end = geom.coords[-1]
            d_start = (g_start[0] - u_xy[0]) ** 2 + (g_start[1] - u_xy[1]) ** 2
            d_end = (g_end[0] - u_xy[0]) ** 2 + (g_end[1] - u_xy[1]) ** 2
            if d_end < d_start:
                geom = LineString(list(geom.coords)[::-1])
            geometries.append(geom)

    total_risk_score = (weighted_risk_sum / total_distance_m) if total_distance_m > 0 else 0.0

    if geometries:
        merged = linemerge(geometries)
        if isinstance(merged, MultiLineString):
            all_coords = [c for line in merged.geoms for c in line.coords]
            merged = LineString(all_coords)
        coords_3857 = list(merged.coords)
    else:
        coords_3857 = [(G.nodes[n]["x"], G.nodes[n]["y"]) for n in node_path]

    coords_wgs84 = [_transformer_to_wgs84.transform(x, y) for x, y in coords_3857]

    return {
        "geometry": {
            "type": "LineString",
            "coordinates": [[lon, lat] for lon, lat in coords_wgs84],
        },
        "total_distance_m": total_distance_m,
        "total_risk_score": total_risk_score,
        "risk_category": categorize_risk(total_risk_score),
        "waypoints": [[lat, lon] for lon, lat in coords_wgs84],
    }


def categorize_risk(score: float) -> str:
    if score < 0.2:
        return "low"
    if score < 0.5:
        return "medium"
    return "high"


def find_safest_route(
    G: nx.MultiGraph,
    risk_scores: dict[str, float],
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    lambda_coef: float = 0.5,
) -> dict | None:
    """Dijkstra + 風險加權，找最安全路線。"""
    start_node = get_nearest_node(G, start_lat, start_lon)
    end_node = get_nearest_node(G, end_lat, end_lon)

    if start_node == end_node:
        logger.warning("Start and end nodes are the same")
        return None

    G_w = apply_risk_weights(G, risk_scores, lambda_coef)

    try:
        node_path = nx.shortest_path(
            G_w, source=start_node, target=end_node, weight="risk_weight"
        )
    except nx.NetworkXNoPath:
        logger.warning("No path between %s and %s", start_node, end_node)
        return None
    except nx.NodeNotFound as e:
        logger.warning("Node not found: %s", e)
        return None

    stats = compute_route_stats(node_path, G, risk_scores)
    stats["route_type"] = "safety_optimized"

    logger.info(
        "Safety route: %.0fm, risk=%.3f (%s)",
        stats["total_distance_m"],
        stats["total_risk_score"],
        stats["risk_category"],
    )
    return stats
