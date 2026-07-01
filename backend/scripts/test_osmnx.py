"""
OSMnx 試跑腳本：下載台北 bbox 的自行車路網，與 Geofabrik 結果比較。

執行：
    python -m scripts.test_osmnx

輸出：
    - 節點數 / 邊數 / 下載時間
    - EPSG:3857 投影後的邊屬性範例
    - 事故 snap 測試（最近邊）
    - 匯出 GPKG 供 QGIS 查看：data/processed/osmnx_taipei.gpkg
"""
import time
import sys
from pathlib import Path

# 讓 scripts 能 import app
sys.path.insert(0, str(Path(__file__).parent.parent))

import geopandas as gpd
import networkx as nx
import osmnx as ox
from pyproj import Transformer

# ── 台北 bbox（來自 config.py ROUTING_BBOX_*）────────────────────────────────
NORTH = 25.22
SOUTH = 24.95
EAST = 121.68
WEST = 121.42

OUTPUT_GPKG = Path("data/processed/osmnx_taipei.gpkg")


def main() -> None:
    print("=" * 60)
    print("OSMnx 試跑：台北自行車路網")
    print(f"  bbox: N{NORTH} S{SOUTH} E{EAST} W{WEST}")
    print("=" * 60)

    # ── 1. 下載 ──────────────────────────────────────────────────────────────
    print("\n[1] 從 Overpass API 下載路網...")
    t0 = time.time()
    G = ox.graph_from_bbox(
        bbox=(NORTH, SOUTH, EAST, WEST),
        network_type="bike",
        simplify=True,         # 移除非路口的中間節點
        retain_all=False,      # 只保留最大連通子圖
    )
    elapsed = time.time() - t0
    print(f"    下載完成：{elapsed:.1f} 秒")
    print(f"    節點數：{G.number_of_nodes():,}")
    print(f"    邊數（有向）：{G.number_of_edges():,}")

    # ── 2. 轉為無向圖（雙向騎行）────────────────────────────────────────────
    print("\n[2] 轉換為無向圖（自行車雙向）...")
    G_undirected = ox.convert.to_undirected(G)
    print(f"    節點數：{G_undirected.number_of_nodes():,}")
    print(f"    邊數（無向）：{G_undirected.number_of_edges():,}")

    # ── 3. 投影至 EPSG:3857 ──────────────────────────────────────────────────
    print("\n[3] 投影至 EPSG:3857（公尺單位）...")
    G_proj = ox.project_graph(G_undirected, to_crs="EPSG:3857")

    # ── 4. 邊屬性範例 ─────────────────────────────────────────────────────────
    print("\n[4] 邊屬性範例（前 3 條邊）：")
    for i, (u, v, data) in enumerate(G_proj.edges(data=True)):
        if i >= 3:
            break
        osmid = data.get("osmid", "?")
        highway = data.get("highway", "?")
        length = data.get("length", 0)
        name = data.get("name", "")
        print(f"    osmid={osmid}  highway={highway}  length={length:.1f}m  name={name}")

    # ── 5. highway 類型分布 ───────────────────────────────────────────────────
    print("\n[5] highway 類型分布：")
    from collections import Counter
    highway_counts: Counter = Counter()
    for _, _, data in G_proj.edges(data=True):
        hw = data.get("highway", "unknown")
        if isinstance(hw, list):
            for h in hw:
                highway_counts[h] += 1
        else:
            highway_counts[hw] += 1
    for hw, count in highway_counts.most_common(15):
        print(f"    {hw:<25} {count:>6,}")

    # ── 6. 事故 snap 測試 ─────────────────────────────────────────────────────
    print("\n[6] 事故 snap 測試（ox.distance.nearest_edges）...")
    accidents_path = Path("/home/su2270853/公共/geo-data/raw/accidents_epsg3857.gpkg")
    if accidents_path.exists():
        acc = gpd.read_file(accidents_path)
        if acc.crs and acc.crs.to_epsg() != 3857:
            acc = acc.to_crs(epsg=3857)

        # 只取台北 bbox 內的事故
        transformer = Transformer.from_crs(4326, 3857, always_xy=True)
        w_m, s_m = transformer.transform(WEST, SOUTH)
        e_m, n_m = transformer.transform(EAST, NORTH)
        acc_taipei = acc.cx[w_m:e_m, s_m:n_m].copy()
        print(f"    台北範圍內事故數：{len(acc_taipei):,}")

        if len(acc_taipei) > 0:
            # 取前 100 筆測試 snap 速度
            sample = acc_taipei.head(100)
            X = sample.geometry.x.values
            Y = sample.geometry.y.values

            t1 = time.time()
            ne = ox.distance.nearest_edges(G_proj, X, Y, return_dist=True)
            snap_elapsed = time.time() - t1

            edges, dists = ne
            import numpy as np
            print(f"    100 筆事故 snap 耗時：{snap_elapsed:.3f}s")
            print(f"    snap 距離：min={np.min(dists):.1f}m  median={np.median(dists):.1f}m  max={np.max(dists):.1f}m")
            within_20m = (np.array(dists) <= 20.0).sum()
            print(f"    20m 內命中率：{within_20m}/100 = {within_20m}%")
    else:
        print(f"    找不到事故資料：{accidents_path}")

    # ── 7. 匯出 GPKG ─────────────────────────────────────────────────────────
    print("\n[7] 匯出 GPKG 供 QGIS 查看...")
    OUTPUT_GPKG.parent.mkdir(parents=True, exist_ok=True)

    nodes_gdf, edges_gdf = ox.convert.graph_to_gdfs(G_proj, nodes=True, edges=True)

    nodes_gdf.to_file(OUTPUT_GPKG, layer="nodes", driver="GPKG")
    edges_gdf.to_file(OUTPUT_GPKG, layer="edges", driver="GPKG")
    print(f"    儲存至：{OUTPUT_GPKG}")
    print(f"    nodes layer：{len(nodes_gdf):,} 筆")
    print(f"    edges layer：{len(edges_gdf):,} 筆")

    # ── 8. 與 Geofabrik 比較（若 pkl 存在）──────────────────────────────────
    print("\n[8] 與現有 Geofabrik graph 比較（若存在）...")
    import pickle
    geofabrik_pkl = Path("data/processed/taiwan_graph.pkl")
    if geofabrik_pkl.exists():
        with open(geofabrik_pkl, "rb") as f:
            G_geo = pickle.load(f)
        print(f"    Geofabrik graph  — 節點：{G_geo.number_of_nodes():,}  邊：{G_geo.number_of_edges():,}")
        print(f"    OSMnx graph      — 節點：{G_proj.number_of_nodes():,}  邊：{G_proj.number_of_edges():,}")
        print(f"    (注意：Geofabrik 是全台灣，OSMnx 只有台北 bbox)")
    else:
        print(f"    找不到 {geofabrik_pkl}，略過比較")

    print("\n" + "=" * 60)
    print("試跑完成！可在 QGIS 開啟：")
    print(f"  {OUTPUT_GPKG.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
