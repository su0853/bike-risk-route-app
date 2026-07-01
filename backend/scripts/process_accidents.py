"""
CLI: 從事故 GPKG 計算每條道路路段的風險分數並儲存。

前提: 必須先執行 build_graph.py (需要 roads_gdf.pkl)

執行方式:
    cd backend
    python -m scripts.process_accidents
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    import numpy as np

    from app.config import settings
    from app.services.graph_builder import load_roads_gdf
    from app.services.risk_engine import build_risk_scores, save_risk_scores

    logger.info("=== Process Accidents Script ===")
    logger.info("Accidents GPKG: %s", settings.ACCIDENTS_GPKG_PATH)
    logger.info("A1 weight: %.1f, A2 weight: %.1f", settings.RISK_A1_WEIGHT, settings.RISK_A2_WEIGHT)
    logger.info("Decay half-life: %.1f years", settings.RISK_DECAY_HALF_LIFE_YEARS)

    # 載入已篩選的道路 GeoDataFrame
    roads = load_roads_gdf(settings.ROADS_GDF_PATH)

    # 計算風險分數
    risk_scores = build_risk_scores(settings.ACCIDENTS_GPKG_PATH, roads, settings)

    # 儲存
    save_risk_scores(risk_scores, settings.RISK_SCORES_PATH)

    # 摘要報告
    values = list(risk_scores.values())
    nonzero = [v for v in values if v > 0]
    logger.info("=== Risk Score Summary ===")
    logger.info("Total road segments: %d", len(values))
    logger.info("Segments with risk > 0: %d (%.1f%%)", len(nonzero), 100 * len(nonzero) / len(values))
    if nonzero:
        logger.info("  min=%.6f", min(nonzero))
        logger.info("  p50=%.6f", float(np.percentile(nonzero, 50)))
        logger.info("  p99=%.6f", float(np.percentile(nonzero, 99)))
        logger.info("  max=%.6f", max(values))

    assert max(values) <= 1.0 + 1e-9, "Normalization error: max > 1.0"
    logger.info("Normalization check passed (max=%.6f)", max(values))


if __name__ == "__main__":
    main()
