"""
CLI: 事故 ETL —— 政府 A1/A2 原始 CSV → 只含自行車事故的分年度 cleaned CSV。

移植自外部資料專案的 etl_all.py（邏輯不變）；納入本專案以使整條管線自足。

輸入：<raw-dir>（預設 data/accidents_raw/）下 `x年度A1/A2交通事故資料[(...)].csv`
      （由 scripts.download_accidents_raw 下載）
輸出：<cleaned-dir>（預設 data/cleaned/）下 `{year}_A1A2_bike_cleaned.csv`
      欄位：case_type, datetime, location, death_count, injury_count, lon, lat, hour, time_period, risk_score
      （lon/lat 為 EPSG:4326 WGS84；risk_score 為 ETL 簡易標籤 A1=3/A2=2，後端 risk_engine 會另行重算）

下游：prepare_accidents_gpkg.py → data/raw/accidents_epsg3857.gpkg

執行：
    cd backend
    python -m scripts.etl_accidents
"""
import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("etl_accidents")

DEFAULT_RAW_DIR = "data/accidents_raw"
DEFAULT_CLEANED_DIR = "data/cleaned"

OUTPUT_COLS = [
    "case_type", "datetime", "location",
    "death_count", "injury_count", "lon", "lat",
    "hour", "time_period", "risk_score",
]


# ---- 共用清洗函式（與原 etl_all.py 一致）----
def convert_roc_datetime(text):
    """「107年01月01日 05時12分00秒」→ Timestamp（容錯）。"""
    import pandas as pd
    if pd.isna(text):
        return pd.NaT
    m = re.match(r"(\d+)年(\d+)月(\d+)日\s+(\d+)時(\d+)分(\d+)秒", str(text))
    if not m:
        return pd.NaT
    year = int(m.group(1)) + 1911
    month, day, hour, minute = (int(m.group(i)) for i in (2, 3, 4, 5))
    try:
        second = int(m.group(6))
    except ValueError:
        second = 0
    second = min(max(second, 0), 59)
    try:
        return pd.Timestamp(year, month, day, hour, minute, second)
    except ValueError:
        return pd.NaT


def split_casualty(text):
    """「死亡1;受傷3」→ (death_count, injury_count)。"""
    import pandas as pd
    if pd.isna(text):
        return pd.Series([0, 0])
    text = str(text)
    d = re.search(r"死亡(\d+)", text)
    i = re.search(r"受傷(\d+)", text)
    return pd.Series([int(d.group(1)) if d else 0, int(i.group(1)) if i else 0])


def contains_bike(vlist) -> bool:
    if not isinstance(vlist, list):
        return False
    return any(k in item for item in vlist for k in ("自行車", "腳踏"))


def hour_to_period(h):
    import pandas as pd
    if pd.isna(h):
        return None
    return "深夜" if h < 6 else "上午" if h < 12 else "下午" if h < 18 else "晚間"


def risk_weight(row) -> int:
    if row["death_count"] > 0:
        return 3
    if row["injury_count"] > 0:
        return 2
    return 1


def clean_file(path: Path, case_type: str):
    """清洗單一 A1/A2 原始檔 → 只含自行車事故的 DataFrame。"""
    import pandas as pd
    logger.info("  讀取：%s (%s)", path.name, case_type)
    df = pd.read_csv(path, encoding="utf-8")
    df = df.rename(columns={
        "發生時間": "datetime_raw", "發生地點": "location",
        "死亡受傷人數": "casualty", "車種": "vehicle",
        "經度": "lon", "緯度": "lat",
    })
    df["case_type"] = case_type
    df["datetime"] = df["datetime_raw"].apply(convert_roc_datetime)
    df[["death_count", "injury_count"]] = df["casualty"].apply(split_casualty)
    df["vehicle"] = df["vehicle"].fillna("")
    df["vehicle_list"] = df["vehicle"].str.split(";")
    df["is_bike"] = df["vehicle_list"].apply(contains_bike)
    df_bike = df[df["is_bike"]].copy()
    df_bike["hour"] = df_bike["datetime"].dt.hour
    df_bike["time_period"] = df_bike["hour"].apply(hour_to_period)
    df_bike["risk_score"] = df_bike.apply(risk_weight, axis=1)
    return df_bike.drop(columns=["datetime_raw", "casualty", "is_bike", "vehicle"], errors="ignore")


def main() -> None:
    import pandas as pd

    parser = argparse.ArgumentParser(description="政府 A1/A2 原始 CSV → 自行車事故 cleaned CSV")
    parser.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    parser.add_argument("--cleaned-dir", default=DEFAULT_CLEANED_DIR)
    parser.add_argument("--no-overwrite", action="store_true", help="已存在的年度檔就跳過")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    cleaned_dir = Path(args.cleaned_dir)
    cleaned_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== ETL Accidents ===")
    logger.info("raw: %s → cleaned: %s", raw_dir, cleaned_dir)

    csv_files = list(raw_dir.glob("*.csv"))
    if not csv_files:
        logger.error("%s 下無 CSV（先跑 scripts.download_accidents_raw）", raw_dir)
        sys.exit(1)

    pattern = re.compile(r"(\d+)年度(A[12])類?交通事故資料(?:\(.+\))?")
    year_case: dict[str, dict[str, list[Path]]] = {}
    for path in csv_files:
        m = pattern.search(path.stem)
        if not m:
            logger.warning("  無法解析檔名，跳過：%s", path.name)
            continue
        year_case.setdefault(m.group(1), {}).setdefault(m.group(2), []).append(path)

    if not year_case:
        logger.error("無符合命名格式的檔案。")
        sys.exit(1)

    total_out = 0
    for year, cases in sorted(year_case.items(), key=lambda x: int(x[0])):
        if int(year) < 107:
            logger.info("⏩ %s 年 (<107) 缺 lon/lat，跳過。", year)
            continue
        out_path = cleaned_dir / f"{year}_A1A2_bike_cleaned.csv"
        if out_path.exists() and args.no_overwrite:
            logger.info("✅ %s 已存在，--no-overwrite 跳過。", out_path.name)
            continue

        logger.info("=== 處理 %s 年度 ===", year)
        dfs = []
        for case in ("A1", "A2"):
            for p in cases.get(case, []):
                d = clean_file(p, case)
                dfs.append(d)
                logger.info("  %s %s 自行車事故：%d 筆", case, p.name, len(d))
        if not dfs:
            logger.warning("  %s 年無可用資料，跳過。", year)
            continue

        df_all = pd.concat(dfs, ignore_index=True)
        cols = [c for c in OUTPUT_COLS if c in df_all.columns]
        df_all[cols].to_csv(out_path, index=False, encoding="utf-8-sig")
        logger.info("  ✅ 輸出 %s（%d 筆）", out_path.name, len(df_all))
        total_out += len(df_all)

    logger.info("完成。cleaned 總筆數：%d。下一步：python -m scripts.prepare_accidents_gpkg", total_out)


if __name__ == "__main__":
    main()
