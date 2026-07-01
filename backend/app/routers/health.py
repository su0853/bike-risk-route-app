import networkx as nx
from fastapi import APIRouter, Request

from app.models.schemas import HealthResponse

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    state = request.app.state
    G = getattr(state, "graph", None)
    risk_scores = getattr(state, "risk_scores", None)

    return HealthResponse(
        status="ok",
        graph_loaded=G is not None,
        risk_scores_loaded=risk_scores is not None,
        node_count=G.number_of_nodes() if G else 0,
        edge_count=G.number_of_edges() if G else 0,
        risk_score_count=len(risk_scores) if risk_scores else 0,
    )
