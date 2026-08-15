"""
CLI: 從政府開放資料平臺下載 107–109 年 A1/A2 交通事故原始 CSV。

來源：內政部警政署「道路交通事故資料」（政府資料開放平臺 data.gov.tw / opdadm.moi.gov.tw）
      dataset 67781E29-8AAD-46A9-A2C8-C3F339592C27
      URL 對照見外部 `ETL流程說明_v3.0.md`。

輸出：<output>（預設 data/accidents_raw/），檔名刻意存成 `etl_accidents.py` 的正則吃得到的格式：
      107年度A1交通事故資料.csv / 108年度A2交通事故資料(108年1月-6月).csv ...

原始檔為「全部事故」（非僅自行車），較大，故走下載、不進 git。
下游：etl_accidents.py → data/cleaned/*.csv

執行：
    cd backend
    python -m scripts.download_accidents_raw
"""
import argparse
import logging
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("download_accidents_raw")

DATASET = "67781E29-8AAD-46A9-A2C8-C3F339592C27"
URL_TMPL = ("https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
            f"{DATASET}/resource/{{res}}/download")
DEFAULT_OUTPUT = "data/accidents_raw"

# 檔名（需符合 etl_accidents.py 的正則 (\d+)年度(A[12])類?交通事故資料(?:\(.+\))?）→ resource id
FILES = {
    "107年度A1交通事故資料.csv": "B63FA948-6474-42DB-B191-D84977B0C9CC",
    "107年度A2交通事故資料.csv": "FCD897F6-4CD1-4D31-8CE7-92639D1112C8",
    "108年度A1交通事故資料.csv": "6CF6661A-FA44-41DC-AF25-7BA9FF0F9652",
    "108年度A2交通事故資料(108年1月-6月).csv": "0F6EEADB-DF91-4B8B-A3EF-54173C6533C0",
    "108年度A2交通事故資料(108年7月-12月).csv": "701C543A-6D89-496D-9AB3-CAE2881788C5",
    "109年度A1交通事故資料.csv": "179FF667-2832-43D2-A4E4-26D5B031A186",
    "109年度A2交通事故資料(109年1月-6月).csv": "7CE87B70-68D5-4EAA-9F99-E3FF6E99CEA1",
    "109年度A2交通事故資料(109年7月-12月).csv": "649FB516-F037-4D9C-9FF7-9181D9AB22F5",
}


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "bike-risk-route/1.0"})
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (信任政府開放資料官方 URL)
        data = resp.read()
    dest.write_bytes(data)
    logger.info("  ✓ %s (%.1f MB)", dest.name, len(data) / 1e6)


def main() -> None:
    parser = argparse.ArgumentParser(description="下載政府 A1/A2 事故原始 CSV")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help=f"輸出目錄 (預設 {DEFAULT_OUTPUT})")
    parser.add_argument("--force", action="store_true", help="已存在也重新下載")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== Download Accidents Raw ===")
    logger.info("Output: %s（%d 檔）", out_dir, len(FILES))

    ok = 0
    for fname, res in FILES.items():
        dest = out_dir / fname
        if dest.exists() and not args.force:
            logger.info("  - %s 已存在，略過（--force 可重下）", fname)
            ok += 1
            continue
        try:
            download(URL_TMPL.format(res=res), dest)
            ok += 1
        except Exception as e:  # noqa: BLE001
            logger.error("  ✗ %s 下載失敗：%s", fname, e)

    logger.info("完成 %d/%d。下一步：python -m scripts.etl_accidents", ok, len(FILES))
    if ok < len(FILES):
        sys.exit(1)


if __name__ == "__main__":
    main()
