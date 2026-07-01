import asyncio
import logging

import geopandas as gpd
import networkx as nx
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.models.schemas import NavigateRequest, NavigateResponse, RouteResult
from app.services.google_routes import fetch_cycling_routes
from app.services.path_planner import find_safest_route
from app.services.route_evaluator import evaluate_all_routes

logger = logging.getLogger(__name__)
router = APIRouter()

# 台灣合理範圍
TAIWAN_BOUNDS = {
    "lat_min": 21.5,
    "lat_max": 25.5,
    "lon_min": 119.0,
    "lon_max": 122.5,
}


def _validate_coordinate(lat: float, lon: float, name: str) -> None:
    b = TAIWAN_BOUNDS
    if not (b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]):
        raise HTTPException(
            status_code=400,
            detail=f"{name} coordinate ({lat}, {lon}) is outside Taiwan bounds",
        )


def _to_route_result(r: dict) -> RouteResult:
    return RouteResult(
        route_type=r["route_type"],
        geometry=r["geometry"],
        total_distance_m=r["total_distance_m"],
        total_risk_score=r["total_risk_score"],
        risk_category=r["risk_category"],
        waypoints=r.get("waypoints", []),
    )


@router.post("/api/navigate", response_model=NavigateResponse)
async def navigate(req: NavigateRequest, request: Request) -> NavigateResponse:
    _validate_coordinate(req.start.lat, req.start.lon, "start")
    _validate_coordinate(req.end.lat, req.end.lon, "end")

    state = request.app.state
    G: nx.MultiGraph | None = getattr(state, "graph", None)
    roads: gpd.GeoDataFrame | None = getattr(state, "roads_gdf", None)
    risk_scores: dict | None = getattr(state, "risk_scores", None)

    if G is None or roads is None:
        raise HTTPException(status_code=503, detail="Road graph not loaded yet")
    if risk_scores is None:
        raise HTTPException(status_code=503, detail="Risk scores not loaded yet")

    start = (req.start.lat, req.start.lon)
    end = (req.end.lat, req.end.lon)

    # 並行取得 Google 路線 + 本地安全路線
    google_task = asyncio.create_task(
        fetch_cycling_routes(
            settings.GOOGLE_ROUTES_API_KEY,
            start,
            end,
            settings.MAX_GOOGLE_ALTERNATIVES,
        )
    )

    safety_route = await asyncio.get_event_loop().run_in_executor(
        None,
        find_safest_route,
        G, risk_scores,
        req.start.lat, req.start.lon,
        req.end.lat, req.end.lon,
        req.lambda_coef,
    )

    try:
        google_routes = await google_task
    except HTTPException:
        google_routes = []
        logger.warning("Google Routes failed, returning local route only")

    all_routes = evaluate_all_routes(
        google_routes,
        roads,
        risk_scores,
        safety_route,
        settings.SNAP_TOLERANCE_M,
    )

    if not all_routes:
        return NavigateResponse(routes=[], status="no_routes_found")

    return NavigateResponse(
        routes=[_to_route_result(r) for r in all_routes],
        status="ok",
    )
