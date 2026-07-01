import logging

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

ROUTES_API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.legs.polyline,routes.distanceMeters,routes.duration"


async def fetch_cycling_routes(
    api_key: str,
    start: tuple[float, float],  # (lat, lon)
    end: tuple[float, float],
    max_alternatives: int = 2,
) -> list[dict]:
    """
    呼叫 Google Routes API v2 取得自行車候選路線。
    回傳原始 route dict 列表。
    """
    if not api_key:
        logger.warning("GOOGLE_ROUTES_API_KEY not set — skipping Google Routes")
        return []

    body = {
        "origin": {"location": {"latLng": {"latitude": start[0], "longitude": start[1]}}},
        "destination": {"location": {"latLng": {"latitude": end[0], "longitude": end[1]}}},
        "travelMode": "BICYCLE",
        "computeAlternativeRoutes": max_alternatives > 0,
    }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(ROUTES_API_URL, json=body, headers=headers)

        if resp.status_code != 200:
            logger.error("Google Routes API error %d: %s", resp.status_code, resp.text[:300])
            raise HTTPException(status_code=502, detail="Google Routes API error")

        data = resp.json()
        routes = data.get("routes", [])
        logger.info("Google Routes returned %d routes", len(routes))
        return routes[: max_alternatives + 1]

    except httpx.TimeoutException:
        logger.error("Google Routes API timeout")
        raise HTTPException(status_code=502, detail="Google Routes API timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Google Routes unexpected error: %s", e)
        raise HTTPException(status_code=502, detail="Google Routes API unavailable")


def extract_route_polyline(route: dict) -> str | None:
    """從 Google Routes 回應取得 encoded polyline。"""
    try:
        return route["legs"][0]["polyline"]["encodedPolyline"]
    except (KeyError, IndexError):
        logger.warning("Could not extract polyline from route")
        return None


def extract_route_distance_m(route: dict) -> float:
    """從 Google Routes 回應取得路線距離(公尺)。"""
    return float(route.get("distanceMeters", 0))
