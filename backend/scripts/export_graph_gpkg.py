"""
將 Geofabrik graph (pkl) 匯出為 GPKG 供 QGIS 查看。

執行：
    python -m scripts.export_graph_gpkg

輸出：data/processed/taiwan_graph.gpkg
  - nodes layer：節點（路口）點幾何
  - edges layer：邊（道路段）線幾何，含 osm_id / fclass / length_m / risk_score
"""
import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

GRAPH_PKL = Path("data/processed/taiwan_graph.pkl")
RISK_JSON = Path("data/processed/risk_scores.json")
OUTPUT_GPKG = Path("data/processed/taiwan_graph.gpkg")


def main() -> None:
    print("=" * 60)
    print("Geofabrik graph → GPKG 匯出")
    print("=" * 60)

    if not GRAPH_PKL.exists():
        print(f"找不到 {GRAPH_PKL}，請先執行 python -m scripts.build_graph")
        sys.exit(1)

    # ── 1. 載入 pkl ──────────────────────────────────────────────────────────
    print(f"\n[1] 載入 {GRAPH_PKL} ...")
    with open(GRAPH_PKL, "rb") as f:
        G = pickle.load(f)
    print(f"    節點數：{G.number_of_nodes():,}  邊數：{G.number_of_edges():,}")

    # ── 2. 載入 risk scores（若存在）────────────────────────────────────────
    risk_scores: dict = {}
    if RISK_JSON.exists():
        with open(RISK_JSON, encoding="utf-8") as f:
            risk_scores = json.load(f)
        print(f"    Risk scores 載入：{len(risk_scores):,} 筆")

    # ── 3. 節點 → GeoDataFrame ───────────────────────────────────────────────
    print("\n[2] 建立 nodes GeoDataFrame...")
    node_records = []
    for node_id, data in G.nodes(data=True):
        x = data.get("x")
        y = data.get("y")
        if x is not None and y is not None:
            node_records.append({
                "node_id": str(node_id),
                "x_3857": x,
                "y_3857": y,
                "geometry": Point(x, y),
            })
    nodes_gdf = gpd.GeoDataFrame(node_records, crs="EPSG:3857")
    print(f"    nodes：{len(nodes_gdf):,} 筆")

    # ── 4. 邊 → GeoDataFrame ─────────────────────────────────────────────────
    print("\n[3] 建立 edges GeoDataFrame...")
    edge_records = []
    for u, v, key, data in G.edges(keys=True, data=True):
        geom = data.get("geometry")
        if geom is None:
            continue
        osm_id = str(data.get("osm_id", ""))
        risk = risk_scores.get(osm_id, 0.0)
        edge_records.append({
            "u": str(u),
            "v": str(v),
            "key": key,
            "osm_id": osm_id,
            "fclass": data.get("fclass", ""),
            "length_m": round(data.get("length_m", 0.0), 2),
            "risk_score": round(risk, 6),
            "geometry": geom,
        })
    edges_gdf = gpd.GeoDataFrame(edge_records, crs="EPSG:3857")
    print(f"    edges：{len(edges_gdf):,} 筆")

    # fclass 分布
    print("\n    fclass 分布：")
    fc_counts = edges_gdf["fclass"].value_counts()
    for fc, cnt in fc_counts.head(15).items():
        print(f"      {fc:<25} {cnt:>8,}")

    # risk score 分布（若有）
    if risk_scores:
        nonzero = edges_gdf[edges_gdf["risk_score"] > 0]["risk_score"]
        if len(nonzero) > 0:
            import numpy as np
            print(f"\n    risk_score 分布（非零 {len(nonzero):,} 筆）：")
            print(f"      min={nonzero.min():.6f}  median={nonzero.median():.6f}  "
                  f"p99={np.percentile(nonzero, 99):.6f}  max={nonzero.max():.6f}")

    # ── 5. 寫入 GPKG ─────────────────────────────────────────────────────────
    print(f"\n[4] 寫入 {OUTPUT_GPKG} ...")
    OUTPUT_GPKG.parent.mkdir(parents=True, exist_ok=True)
    nodes_gdf.to_file(OUTPUT_GPKG, layer="nodes", driver="GPKG")
    edges_gdf.to_file(OUTPUT_GPKG, layer="edges", driver="GPKG")

    print(f"\n完成！QGIS 可開啟：{OUTPUT_GPKG.resolve()}")
    print("  - nodes layer：路口節點（點）")
    print("  - edges layer：道路段（線），含 fclass / length_m / risk_score")


if __name__ == "__main__":
    main()
