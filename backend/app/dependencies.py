import geopandas as gpd
import networkx as nx
from fastapi import HTTPException, Request


def get_graph(request: Request) -> nx.MultiGraph:
    G = getattr(request.app.state, "graph", None)
    if G is None:
        raise HTTPException(status_code=503, detail="Road graph not loaded")
    return G


def get_roads_gdf(request: Request) -> gpd.GeoDataFrame:
    gdf = getattr(request.app.state, "roads_gdf", None)
    if gdf is None:
        raise HTTPException(status_code=503, detail="Roads GeoDataFrame not loaded")
    return gdf


def get_risk_scores(request: Request) -> dict:
    scores = getattr(request.app.state, "risk_scores", None)
    if scores is None:
        raise HTTPException(status_code=503, detail="Risk scores not loaded")
    return scores
