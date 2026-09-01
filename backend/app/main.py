import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import geocode, health, navigate
from app.services.db_source import (
    load_risk_scores_from_db,
    load_roads_gdf_from_db,
    make_engine,
)
from app.services.graph_builder import build_node_tree, load_graph

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

    # Roads GDF + Risk Scores：一律從 PostGIS 載入（002 DB-centric）。graph 仍讀 pkl（上方）。
    app.state.db_engine = None
    try:
        engine = make_engine(settings.database_url)
        app.state.db_engine = engine
        app.state.roads_gdf = load_roads_gdf_from_db(engine)
        app.state.risk_scores = load_risk_scores_from_db(engine)
    except Exception as e:
        logger.error("無法從 PostGIS 載入（DB 起著、且 rebuild_from_db 跑過了嗎？）：%s", e)
        app.state.roads_gdf = None
        app.state.risk_scores = None

    logger.info("Startup complete.")
    yield

    logger.info("Shutting down...")
    if getattr(app.state, "db_engine", None) is not None:
        app.state.db_engine.dispose()


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
