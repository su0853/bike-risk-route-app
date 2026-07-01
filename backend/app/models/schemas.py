from typing import Literal
from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    lat: float
    lon: float


class NavigateRequest(BaseModel):
    start: Coordinate
    end: Coordinate
    lambda_coef: float = Field(default=0.5, ge=0.0, le=5.0)


class GeoJSONGeometry(BaseModel):
    type: Literal["LineString"]
    coordinates: list[list[float]]  # [lon, lat] GeoJSON 標準順序


class RouteResult(BaseModel):
    route_type: str  # "safety_optimized" | "google_0" | "google_1"
    geometry: GeoJSONGeometry
    total_distance_m: float
    total_risk_score: float  # 0–1 長度加權平均
    risk_category: str  # "low" | "medium" | "high"
    waypoints: list[list[float]]  # [[lat, lon]] for react-native-maps


class NavigateResponse(BaseModel):
    routes: list[RouteResult]
    status: str  # "ok" | "no_routes_found"


class HealthResponse(BaseModel):
    status: str
    graph_loaded: bool
    risk_scores_loaded: bool
    node_count: int
    edge_count: int
    risk_score_count: int
