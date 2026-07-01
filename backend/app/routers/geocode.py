import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["geocode"])

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_HEADERS = {
    "User-Agent": "BikeRiskRouteApp/1.0 (github.com/bike-risk-route-app)",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}


@router.get("/geocode")
async def geocode(q: str = Query(..., min_length=1)):
    params = {
        "q": f"{q}, Taiwan",
        "format": "json",
        "limit": 5,
        "countrycodes": "tw",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(NOMINATIM_URL, params=params, headers=_HEADERS)
        if resp.status_code != 200:
            logger.error("Nominatim error %d: %s", resp.status_code, resp.text[:200])
            raise HTTPException(status_code=502, detail=f"Geocoder error {resp.status_code}")
        results = resp.json()
        return [
            {
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "display_name": r["display_name"],
            }
            for r in results
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Geocode unexpected error: %s", e)
        raise HTTPException(status_code=502, detail="Geocoder unavailable")
