"""
下載台灣 DEM（AW3D30 30m GeoTIFF）供坡度權重使用（§006-1）。

來源：OpenTopography Global DEM API（免費，需申請 API key）
  https://opentopography.org → 註冊 → myOpenTopo → 產生 API key
  設到 backend/.env 的 OPENTOPOGRAPHY_API_KEY，或用 --api-key 傳入。

用法：
  python -m scripts.download_dem                         # 用 config 的 bbox + .env 的 key
  python -m scripts.download_dem --api-key XXXX          # 直接傳 key
  python -m scripts.download_dem --output data/raw/dem_taiwan.tif

pipeline 只讀 config.DEM_PATH 指向的 GeoTIFF；要換更準的 DEM（如國土測繪 20m），
把檔案放到同一路徑即可，不必改其他程式。
"""
import argparse
import logging
import sys
from pathlib import Path

import httpx

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("download_dem")

# httpx 的 INFO log 會把完整請求 URL（含 ?API_Key=...）印出來 → 壓到 WARNING 避免外洩金鑰。
logging.getLogger("httpx").setLevel(logging.WARNING)

API_URL = "https://portal.opentopography.org/API/globaldem"


def main() -> None:
    ap = argparse.ArgumentParser(description="Download Taiwan AW3D30 DEM from OpenTopography (§006-1)")
    ap.add_argument("--api-key", default=settings.OPENTOPOGRAPHY_API_KEY)
    ap.add_argument("--output", default=settings.DEM_PATH)
    ap.add_argument("--demtype", default="AW3D30", help="AW3D30 / SRTMGL1 等 OpenTopography 資料集")
    ap.add_argument("--south", type=float, default=settings.DEM_BBOX_SOUTH)
    ap.add_argument("--north", type=float, default=settings.DEM_BBOX_NORTH)
    ap.add_argument("--west", type=float, default=settings.DEM_BBOX_WEST)
    ap.add_argument("--east", type=float, default=settings.DEM_BBOX_EAST)
    args = ap.parse_args()

    if not args.api_key:
        logger.error("缺 OpenTopography API key：設 backend/.env 的 OPENTOPOGRAPHY_API_KEY 或用 --api-key")
        sys.exit(1)

    params = {
        "demtype": args.demtype,
        "south": args.south, "north": args.north,
        "west": args.west, "east": args.east,
        "outputFormat": "GTiff",
        "API_Key": args.api_key,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    logger.info("下載 %s DEM bbox=(S%.2f N%.2f W%.2f E%.2f) → %s",
                args.demtype, args.south, args.north, args.west, args.east, out)
    with httpx.stream("GET", API_URL, params=params, timeout=600.0) as r:
        if r.status_code != 200:
            body = r.read()[:500].decode(errors="replace")
            logger.error("OpenTopography 回 %d：%s", r.status_code, body)
            sys.exit(1)
        total = 0
        with open(out, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
                total += len(chunk)
    logger.info("完成：%s（%.1f MB）", out, total / 1e6)


if __name__ == "__main__":
    main()
