"""
OSMnx 台灣全島自行車路網下載腳本。

下載來源：OpenStreetMap（透過 Overpass API）
輸出：data/processed/osmnx_taiwan.gpkg
  - nodes layer：路口節點（點幾何，EPSG:3857）
  - edges layer：道路段（線幾何，含 osmid / highway / length / name）

執行：
    python -m scripts.download_osmnx_taiwan

注意：
  - 台灣全島面積大，Overpass API 會自動切成約 214 個子查詢
  - 首次下載預計需要 30–90 分鐘（視網路與 Overpass 負載）
  - 下載完成後 GPKG 可直接在 QGIS 開啟，或供後續比較用
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import osmnx as ox

# 顯示下載進度到終端機（預設關閉）
ox.settings.log_console = True
# 快取下載結果到 ./cache，重跑時不重複呼叫 Overpass API（預設已開啟）
ox.settings.use_cache = True
# 台灣全島子查詢多，拉長逾時避免中途中斷（預設 180 秒）
ox.settings.requests_timeout = 600

OUTPUT_GPKG = Path("data/processed/osmnx_taiwan.gpkg")


def main() -> None:
    print("=" * 60)
    print("OSMnx 台灣全島自行車路網下載")
    print("=" * 60)
    print(f"\n輸出路徑：{OUTPUT_GPKG.resolve()}")
    print("Overpass API 將自動分割為多個子查詢，請耐心等待...\n")

    t0 = time.time()

    try:
        G = ox.graph_from_place(
            "Taiwan",
            network_type="bike",
            simplify=True,
            retain_all=False,
        )
    except Exception as e:
        print(f"\n下載失敗：{type(e).__name__}: {e}")
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"\n下載完成！耗時：{elapsed / 60:.1f} 分鐘")
    print(f"節點數（有向）：{G.number_of_nodes():,}")
    print(f"邊數（有向）：{G.number_of_edges():,}")

    print("\n轉換為無向圖（雙向騎行）...")
    G_undirected = ox.convert.to_undirected(G)
    print(f"邊數（無向）：{G_undirected.number_of_edges():,}")

    print("投影至 EPSG:3857...")
    G_proj = ox.project_graph(G_undirected, to_crs="EPSG:3857")

    print(f"寫入 {OUTPUT_GPKG} ...")
    OUTPUT_GPKG.parent.mkdir(parents=True, exist_ok=True)
    nodes, edges = ox.convert.graph_to_gdfs(G_proj, nodes=True, edges=True)
    nodes.to_file(OUTPUT_GPKG, layer="nodes", driver="GPKG")
    edges.to_file(OUTPUT_GPKG, layer="edges", driver="GPKG")

    print(f"\n完成！")
    print(f"  nodes：{len(nodes):,} 筆")
    print(f"  edges：{len(edges):,} 筆")
    print(f"  檔案：{OUTPUT_GPKG.resolve()}")


if __name__ == "__main__":
    main()
