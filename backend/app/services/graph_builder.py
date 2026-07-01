"""
Road graph builder.

路由圖：直接從 Geofabrik GPKG 建立，並透過「路口座標分割」修復拓撲。
- 找出所有「中間點被兩條以上道路共享」的路口座標
- 在這些路口座標將 LineString 切割成小段
- 以座標（1m 精度捨入）作為節點，建立正確連通的 NetworkX 圖

Snap（事故對應）與 risk_scores 仍以 Geofabrik osm_id 為 key，
path_planner 在取得路段風險值時讀取邊的 osm_id 屬性，兩邊對齊。
"""
import logging
import pickle
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import LineString

logger = logging.getLogger(__name__)

# 全域 KDTree 快取
_node_tree: cKDTree | None = None
_node_ids: list | None = None

_transformer_to_3857 = Transformer.from_crs(4326, 3857, always_xy=True)
_transformer_to_wgs84 = Transformer.from_crs(3857, 4326, always_xy=True)

# 節點座標捨入精度 (公尺)：1m 足以合併同一路口座標
_COORD_PRECISION_M = 1


def _round_coord(x: float, y: float) -> tuple[int, int]:
    return (round(x / _COORD_PRECISION_M), round(y / _COORD_PRECISION_M))


def load_and_filter_roads(gpkg_path: str, excluded_fclasses: list[str]) -> gpd.GeoDataFrame:
    """讀取 Geofabrik GPKG，篩選不適合自行車的道路類型，回傳 EPSG:3857 GeoDataFrame。"""
    logger.info("Loading roads from %s", gpkg_path)
    roads = gpd.read_file(gpkg_path)

    original_count = len(roads)
    roads = roads[~roads["fclass"].isin(excluded_fclasses)].copy()
    logger.info("Filtered roads: %d → %d (removed %d)", original_count, len(roads), original_count - len(roads))

    if roads.crs is None or roads.crs.to_epsg() != 3857:
        roads = roads.to_crs(epsg=3857)

    # 爆炸 MultiLineString → 單純 LineString
    multi_count = (roads.geometry.geom_type != "LineString").sum()
    if multi_count > 0:
        logger.info("Exploding %d multi-part geometries...", multi_count)
        roads = roads.explode(index_parts=False).reset_index(drop=True)
        roads = roads[roads.geometry.geom_type == "LineString"].copy()

    roads["length_m"] = roads.geometry.length
    roads["length_km"] = roads["length_m"] / 1000.0

    keep_cols = ["osm_id", "fclass", "name", "oneway", "length_m", "length_km", "geometry"]
    roads = roads[[c for c in keep_cols if c in roads.columns]].reset_index(drop=True)

    logger.info("Roads loaded: %d segments", len(roads))
    return roads


def build_graph(roads_gdf: gpd.GeoDataFrame) -> nx.MultiGraph:
    """
    從 Geofabrik 道路 GeoDataFrame 建立連通路網圖。

    步驟：
    1. 為所有道路的每個座標點建立索引（1m 精度）
    2. 找出同時出現在兩條以上道路（任意位置）的路口座標
    3. 在路口座標將道路切割為小段
    4. 建立 NetworkX MultiGraph，確保路口處節點共享

    邊屬性: osm_id (str), fclass, length_m, geometry
    節點屬性: x, y (EPSG:3857 原始座標)
    節點 ID: (rounded_x, rounded_y) 整數 tuple
    """
    logger.info("Building graph from %d road segments...", len(roads_gdf))

    # 步驟 1: 建立座標 → 道路集合索引
    coord_to_roads: dict[tuple, set] = defaultdict(set)
    road_data: list[tuple] = []

    for iloc_idx, (_, row) in enumerate(roads_gdf.iterrows()):
        coords = list(row.geometry.coords)
        road_data.append((coords, row))
        for c in coords:
            coord_to_roads[_round_coord(*c)].add(iloc_idx)

    # 步驟 2: 找路口座標（同時出現在 2+ 條道路）
    intersection_set = frozenset(c for c, roads in coord_to_roads.items() if len(roads) >= 2)
    logger.info("Intersection coordinates found: %d (of %d unique)", len(intersection_set), len(coord_to_roads))

    # 步驟 3 & 4: 在路口切割道路並建圖
    G = nx.MultiGraph()
    total_segments = 0

    for coords, row in road_data:
        osm_id_str = str(row["osm_id"])
        fclass = row.get("fclass", "")
        oneway = row.get("oneway", "B")

        # 找需要切割的中間點索引
        split_indices = [0]
        for i, c in enumerate(coords):
            if 0 < i < len(coords) - 1 and _round_coord(*c) in intersection_set:
                split_indices.append(i)
        split_indices.append(len(coords) - 1)

        for j in range(len(split_indices) - 1):
            s, e = split_indices[j], split_indices[j + 1]
            if s >= e:
                continue
            seg = coords[s : e + 1]
            if len(seg) < 2:
                continue

            n_start = _round_coord(*seg[0])
            n_end = _round_coord(*seg[-1])

            if not G.has_node(n_start):
                G.add_node(n_start, x=seg[0][0], y=seg[0][1])
            if not G.has_node(n_end):
                G.add_node(n_end, x=seg[-1][0], y=seg[-1][1])

            geom = LineString(seg)
            G.add_edge(
                n_start,
                n_end,
                osm_id=osm_id_str,
                fclass=fclass,
                length_m=geom.length,
                geometry=geom,
                oneway=oneway,
            )
            total_segments += 1

    logger.info(
        "Graph built: %d nodes, %d edges (from %d original segments)",
        G.number_of_nodes(),
        G.number_of_edges(),
        len(roads_gdf),
    )
    return G


def build_node_tree(G: nx.MultiGraph) -> None:
    """建立全域 KDTree（EPSG:3857 座標）以加速最近節點查詢。"""
    global _node_tree, _node_ids

    nodes = list(G.nodes(data=True))
    coords = np.array([[d["x"], d["y"]] for _, d in nodes])
    _node_ids = [nid for nid, _ in nodes]
    _node_tree = cKDTree(coords)
    logger.info("KDTree built with %d nodes", len(_node_ids))


def get_nearest_node(G: nx.MultiGraph, lat: float, lon: float) -> tuple:
    """WGS84 → EPSG:3857 → 最近節點 ID。"""
    global _node_tree, _node_ids
    if _node_tree is None:
        build_node_tree(G)
    x_m, y_m = _transformer_to_3857.transform(lon, lat)
    _, idx = _node_tree.query([x_m, y_m])
    return _node_ids[idx]


# ──────────────────────────────────────────────
# Persistence helpers
# ──────────────────────────────────────────────

def save_graph(G: nx.MultiGraph, filepath: str) -> None:
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)
    logger.info("Graph saved to %s", filepath)


def load_graph(filepath: str) -> nx.MultiGraph:
    with open(filepath, "rb") as f:
        G = pickle.load(f)
    logger.info("Graph loaded: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


def save_roads_gdf(gdf: gpd.GeoDataFrame, filepath: str) -> None:
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "wb") as f:
        pickle.dump(gdf, f, protocol=pickle.HIGHEST_PROTOCOL)
    logger.info("Roads GDF saved to %s (%d rows)", filepath, len(gdf))


def load_roads_gdf(filepath: str) -> gpd.GeoDataFrame:
    with open(filepath, "rb") as f:
        gdf = pickle.load(f)
    logger.info("Roads GDF loaded: %d rows", len(gdf))
    return gdf
