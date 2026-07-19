"""
CLI: 將 ETL 後的分年度自行車事故 cleaned CSV 合併，轉成後端 risk_engine 需要的
     事故 GPKG（EPSG:3857）。

輸入:
    <cleaned-dir>/*_A1A2_bike_cleaned.csv
      欄位: case_type, datetime, location, death_count, injury_count,
            lon, lat, hour, time_period, risk_score
      lon/lat 為 EPSG:4326 (WGS84)
      上游 ETL 來源見 /home/su2270853/projects/data/（ETL流程說明_v3.0.md + scripts/etl_all.py）

輸出:
    <output> (預設 = settings.ACCIDENTS_GPKG_PATH = data/raw/accidents_epsg3857.gpkg)
      欄位: case_type, accident_datetime, death_count, injury_count, location, geometry
      geometry: Point, EPSG:3857

備註:
    - cleaned CSV 的 `risk_score`（A1=3/A2=2）是 ETL 簡易標籤，此處【不帶入】；
      後端 risk_engine 會用 severity × time-decay 另行重算正規化風險。
    - 106 年缺 lon/lat（見 ETL 說明 §7），只使用 107–109。
    - CSV header 帶 BOM，以 utf-8-sig 讀取。

執行:
    cd backend
    python -m scripts.prepare_accidents_gpkg \\
        --cleaned-dir /home/su2270853/projects/data/cleaned \\
        --output data/raw/accidents_epsg3857.gpkg
"""
import argparse
import glob
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("prepare_accidents_gpkg")

DEFAULT_CLEANED_DIR = "/home/su2270853/projects/data/cleaned"
CSV_GLOB = "*_A1A2_bike_cleaned.csv"

# ROC 領土（含金門 118.3E、馬祖 26.1N、澎湖、綠島、蘭嶼）的寬鬆 sanity 範圍。
# 目的是剔除亂碼座標（0,0 / 經緯顛倒），不是圈地理範圍 ——
# 真正的地理過濾由下游 assign_accidents_to_roads 的 snap 容差處理。
ROC_LON = (118.0, 122.5)
ROC_LAT = (21.5, 26.5)

# 輸出保留欄位
OUTPUT_COLS = ["case_type", "accident_datetime", "death_count", "injury_count", "location"]


def main() -> None:
    import geopandas as gpd
    import pandas as pd

    from app.config import settings

    parser = argparse.ArgumentParser(description="合併 cleaned 事故 CSV → EPSG:3857 GPKG")
    parser.add_argument("--cleaned-dir", default=DEFAULT_CLEANED_DIR,
                        help=f"cleaned CSV 目錄 (預設 {DEFAULT_CLEANED_DIR})")
    parser.add_argument("--output", default=settings.ACCIDENTS_GPKG_PATH,
                        help="輸出 gpkg 路徑 (預設 settings.ACCIDENTS_GPKG_PATH)")
    parser.add_argument("--layer", default="accidents", help="輸出圖層名稱 (預設 accidents)")
    parser.add_argument("--no-bbox-filter", action="store_true",
                        help="停用 ROC sanity bbox 過濾，保留所有座標")
    args = parser.parse_args()

    logger.info("=== Prepare Accidents GPKG ===")
    logger.info("Cleaned dir: %s", args.cleaned_dir)
    logger.info("Output:      %s (layer=%s)", args.output, args.layer)

    csv_paths = sorted(glob.glob(str(Path(args.cleaned_dir) / CSV_GLOB)))
    if not csv_paths:
        logger.error("在 %s 找不到 %s，中止。", args.cleaned_dir, CSV_GLOB)
        sys.exit(1)
    logger.info("找到 %d 個 cleaned CSV:", len(csv_paths))
    for p in csv_paths:
        logger.info("  - %s", Path(p).name)

    # --- 讀取並合併 ---
    frames = []
    for p in csv_paths:
        df = pd.read_csv(p, encoding="utf-8-sig")
        logger.info("讀取 %s: %d 列", Path(p).name, len(df))
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    total_raw = len(df)
    logger.info("合併後總列數: %d", total_raw)

    required = {"case_type", "datetime", "lon", "lat", "death_count", "injury_count"}
    missing = required - set(df.columns)
    if missing:
        logger.error("缺少必要欄位: %s。實際欄位: %s", missing, list(df.columns))
        sys.exit(1)

    # --- 型別清理 ---
    df["accident_datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["death_count"] = pd.to_numeric(df["death_count"], errors="coerce").fillna(0).astype(int)
    df["injury_count"] = pd.to_numeric(df["injury_count"], errors="coerce").fillna(0).astype(int)
    df["case_type"] = df["case_type"].astype(str).str.strip().str.upper()
    if "location" not in df.columns:
        df["location"] = ""

    # --- 過濾無效資料 ---
    n = len(df)
    df = df.dropna(subset=["accident_datetime"])
    dropped_dt = n - len(df); n = len(df)

    df = df.dropna(subset=["lon", "lat"])
    dropped_ll = n - len(df); n = len(df)

    if args.no_bbox_filter:
        dropped_bbox = 0
        logger.info("已停用 bbox 過濾（--no-bbox-filter）")
    else:
        in_roc = df["lon"].between(*ROC_LON) & df["lat"].between(*ROC_LAT)
        df = df[in_roc]
        dropped_bbox = n - len(df)

    logger.info("過濾: datetime 無效 -%d, lon/lat 無效 -%d, 超出 ROC sanity 範圍 -%d",
                dropped_dt, dropped_ll, dropped_bbox)
    if df.empty:
        logger.error("過濾後無有效事故，中止。")
        sys.exit(1)

    # --- 建立 geometry 並轉 CRS ---
    gdf = gpd.GeoDataFrame(
        df[OUTPUT_COLS].copy(),
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs="EPSG:4326",
    ).to_crs(epsg=3857)

    # --- 輸出 ---
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    gdf.to_file(out_path, layer=args.layer, driver="GPKG")

    # --- 摘要 ---
    a1 = int((gdf["case_type"].str.contains("A1")).sum())
    a2 = int((gdf["case_type"].str.contains("A2")).sum())
    logger.info("=== Summary ===")
    logger.info("輸出事故筆數: %d (原始 %d，保留 %.1f%%)",
                len(gdf), total_raw, 100 * len(gdf) / total_raw)
    logger.info("  A1: %d, A2: %d, 其他: %d", a1, a2, len(gdf) - a1 - a2)
    logger.info("  死亡總數: %d, 受傷總數: %d",
                int(gdf["death_count"].sum()), int(gdf["injury_count"].sum()))
    logger.info("  日期範圍: %s ~ %s",
                gdf["accident_datetime"].min(), gdf["accident_datetime"].max())
    logger.info("Done → %s", out_path)


if __name__ == "__main__":
    main()
