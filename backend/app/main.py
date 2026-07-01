import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import geocode, health, navigate
from app.services.graph_builder import build_node_tree, load_graph, load_roads_gdf
from app.services.risk_engine import load_risk_scores

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時載入預先建立的 Graph、Roads GDF 與 Risk Scores
    logger.info("Starting Bike Risk API...")

    # Road Graph
    if Path(settings.GRAPH_FILE_PATH).exists():
        try:
            app.state.graph = load_graph(settings.GRAPH_FILE_PATH)
            build_node_tree(app.state.graph)
        except Exception as e:
            logger.error("Failed to load graph: %s", e)
            app.state.graph = None
    else:
        logger.warning("Graph file not found: %s — run scripts/build_graph.py first", settings.GRAPH_FILE_PATH)
        app.state.graph = None

    # Roads GeoDataFrame (用於 spatial join)
    if Path(settings.ROADS_GDF_PATH).exists():
        try:
            app.state.roads_gdf = load_roads_gdf(settings.ROADS_GDF_PATH)
        except Exception as e:
            logger.error("Failed to load roads GDF: %s", e)
            app.state.roads_gdf = None
    else:
        logger.warning("Roads GDF not found: %s", settings.ROADS_GDF_PATH)
        app.state.roads_gdf = None

    # Risk Scores
    if Path(settings.RISK_SCORES_PATH).exists():
        try:
            app.state.risk_scores = load_risk_scores(settings.RISK_SCORES_PATH)
        except Exception as e:
            logger.error("Failed to load risk scores: %s", e)
            app.state.risk_scores = None
    else:
        logger.warning("Risk scores not found: %s — run scripts/process_accidents.py first", settings.RISK_SCORES_PATH)
        app.state.risk_scores = None

    logger.info("Startup complete.")
    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="Bike Risk Route API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Phase 1 開發階段允許所有來源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(geocode.router)
app.include_router(navigate.router)
