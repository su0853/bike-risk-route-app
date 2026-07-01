"""
CLI: 從 Geofabrik GPKG 建立路網圖（含路口拓撲修復）並儲存。

策略：
- 讀取 Geofabrik roads GPKG，篩選不適自行車的路段
- 透過「路口座標分割」修復拓撲：在兩條以上道路共享的中間點切割路段
- 以 1m 精度捨入座標作為節點 ID，確保路口正確連通
- 道路 GDF 額外儲存，供 risk_engine 與 route_evaluator 空間 Join 使用

注意: 此腳本全程離線，不需要網路。

執行方式:
    cd backend
    python -m scripts.build_graph
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    import networkx as nx

    from app.config import settings
    from app.services.graph_builder import (
        build_graph,
        load_and_filter_roads,
        save_graph,
        save_roads_gdf,
    )

    logger.info("=== Build Graph Script ===")
    logger.info("Roads GPKG: %s", settings.ROADS_GPKG_PATH)

    # 1. 載入並篩選
    roads = load_and_filter_roads(settings.ROADS_GPKG_PATH, settings.EXCLUDED_FCLASSES)

    # 2. 儲存道路 GDF（供 risk_engine + route_evaluator 使用）
    save_roads_gdf(roads, settings.ROADS_GDF_PATH)

    # 3. 建立帶有路口拓撲的圖
    G = build_graph(roads)

    # 4. 連通性報告
    comps = list(nx.connected_components(G))
    largest = max(comps, key=len)
    logger.info(
        "Connectivity: %d components, largest=%d/%d (%.1f%%)",
        len(comps),
        len(largest),
        G.number_of_nodes(),
        len(largest) / G.number_of_nodes() * 100,
    )

    # 5. 儲存圖
    save_graph(G, settings.GRAPH_FILE_PATH)

    # 6. 摘要
    logger.info("=== Summary ===")
    logger.info("Nodes: %d | Edges: %d", G.number_of_nodes(), G.number_of_edges())
    logger.info("fclass distribution:")
    for fclass, count in roads["fclass"].value_counts().items():
        logger.info("  %-25s %d", fclass, count)


if __name__ == "__main__":
    main()
