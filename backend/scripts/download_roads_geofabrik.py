"""
CLI: 從 Geofabrik 下載台灣 OSM 道路資料，抽出 roads 圖層，輸出成後端用的單圖層 GPKG。

流程:
    1. 下載 taiwan-latest-free.gpkg.zip（302 會導向日期版，~266MB）
    2. 解壓取得多圖層 gpkg（roads / waterways / buildings…，CRS EPSG:4326）
    3. 只抽出 roads 圖層（預設自動偵測名稱含 "roads" 者，通常是 gis_osm_roads_free_1）
    4. 重投影至 EPSG:3857，輸出成【單圖層】 gpkg

輸出:
    <output> (預設 data/raw/gis_osm_roads_free_1.gpkg)
      單一圖層，欄位沿用 Geofabrik（osm_id, code, fclass, name, ref, oneway, ...）
      graph_builder.load_and_filter_roads() 以 read_file() 讀預設圖層 + 依 fclass 篩選，
      故此腳本【不做 fclass 篩選】，保留全部道路。

執行:
    cd backend
    python -m scripts.download_roads_geofabrik
    # 或指定：
    python -m scripts.download_roads_geofabrik \\
        --url https://download.geofabrik.de/asia/taiwan-latest-free.gpkg.zip \\
        --output data/raw/gis_osm_roads_free_1.gpkg
"""
import argparse
import logging
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("download_roads_geofabrik")

DEFAULT_URL = "https://download.geofabrik.de/asia/taiwan-latest-free.gpkg.zip"
DEFAULT_OUTPUT = "data/raw/gis_osm_roads_free_1.gpkg"
TARGET_EPSG = 3857


def download(url: str, dest: Path) -> None:
    """串流下載，跟隨 302 導向，附簡單進度。"""
    logger.info("下載: %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": "bike-risk-route/1.0"})
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (信任 geofabrik 官方 URL)
        total = int(resp.headers.get("Content-Length", 0))
        logger.info("實際下載: %s (%.1f MB)", resp.url, total / 1e6 if total else 0)
        downloaded = 0
        next_mark = 50 * 1024 * 1024  # 每 50MB log 一次
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded >= next_mark:
                    pct = f" ({100 * downloaded / total:.0f}%)" if total else ""
                    logger.info("  ...%.0f MB%s", downloaded / 1e6, pct)
                    next_mark += 50 * 1024 * 1024
    logger.info("下載完成: %.1f MB → %s", dest.stat().st_size / 1e6, dest)


def find_gpkg(extract_dir: Path) -> Path:
    gpkgs = list(extract_dir.rglob("*.gpkg"))
    if not gpkgs:
        raise FileNotFoundError(f"解壓後找不到 .gpkg：{extract_dir}")
    if len(gpkgs) > 1:
        logger.warning("解壓後有多個 gpkg，取第一個：%s", [p.name for p in gpkgs])
    return gpkgs[0]


def detect_roads_layer(gpkg_path: Path, override: str | None) -> str:
    import pyogrio

    layers = [row[0] for row in pyogrio.list_layers(gpkg_path)]
    logger.info("gpkg 圖層: %s", layers)
    if override:
        if override not in layers:
            raise ValueError(f"指定圖層 {override} 不存在，可用: {layers}")
        return override
    # 優先完全相符，其次名稱含 roads
    if "gis_osm_roads_free_1" in layers:
        return "gis_osm_roads_free_1"
    roads = [ly for ly in layers if "roads" in ly.lower()]
    if not roads:
        raise ValueError(f"找不到 roads 圖層，可用: {layers}")
    if len(roads) > 1:
        logger.warning("多個疑似 roads 圖層 %s，取第一個", roads)
    return roads[0]


def main() -> None:
    import geopandas as gpd

    parser = argparse.ArgumentParser(description="下載 Geofabrik 台灣道路 → 單圖層 GPKG")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--roads-layer", default=None,
                        help="手動指定 roads 圖層名（預設自動偵測）")
    parser.add_argument("--target-epsg", type=int, default=TARGET_EPSG,
                        help=f"輸出 CRS（預設 {TARGET_EPSG}）")
    parser.add_argument("--keep-download", action="store_true",
                        help="保留下載的 zip 與解壓 gpkg（預設處理完刪除）")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("=== Download Roads (Geofabrik) ===")
    logger.info("Output: %s (EPSG:%d)", out_path, args.target_epsg)

    work = Path(tempfile.mkdtemp(prefix="geofabrik_roads_"))
    try:
        zip_path = work / "taiwan-free.gpkg.zip"
        download(args.url, zip_path)

        logger.info("解壓 %s", zip_path.name)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(work)
        src_gpkg = find_gpkg(work)
        logger.info("多圖層來源 gpkg: %s", src_gpkg.name)

        layer = detect_roads_layer(src_gpkg, args.roads_layer)
        logger.info("抽出 roads 圖層: %s", layer)
        roads = gpd.read_file(src_gpkg, layer=layer)
        logger.info("讀取 %d 條道路 | 來源 CRS: %s | 欄位: %s",
                    len(roads), roads.crs, list(roads.columns))

        if roads.crs is None or roads.crs.to_epsg() != args.target_epsg:
            logger.info("重投影 → EPSG:%d", args.target_epsg)
            roads = roads.to_crs(epsg=args.target_epsg)

        if out_path.exists():
            out_path.unlink()
        roads.to_file(out_path, layer="roads", driver="GPKG")

        # 摘要
        logger.info("=== Summary ===")
        logger.info("輸出道路數: %d → %s (%.1f MB)",
                    len(roads), out_path, out_path.stat().st_size / 1e6)
        if "fclass" in roads.columns:
            top = roads["fclass"].value_counts().head(10)
            logger.info("fclass 前 10:\n%s", top.to_string())
        logger.info("Done.")
    finally:
        if args.keep_download:
            logger.info("保留下載暫存: %s", work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
