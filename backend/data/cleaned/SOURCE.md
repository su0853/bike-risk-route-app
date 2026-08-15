# 事故 cleaned 資料來源

本目錄的 `*_A1A2_bike_cleaned.csv` 為**只含自行車事故**的清洗結果，隨 repo bundle 作為預設輸入。

## 來源

- 內政部警政署「道路交通事故資料」A1 / A2（107–109 年）
- 政府資料開放平臺 dataset `67781E29-8AAD-46A9-A2C8-C3F339592C27`
- 原始下載 URL 對照見 `scripts/download_accidents_raw.py`

依政府資料開放平臺之開放資料使用規範利用；請保留來源標示。

## 如何重建 / 更新

```bash
cd backend
python -m scripts.download_accidents_raw   # 下載政府原始 CSV → data/accidents_raw/
python -m scripts.etl_accidents            # 清洗（自行車篩選、欄位正規化）→ 本目錄
```

清洗邏輯：民國年轉西元、死傷拆分、車種篩選（自行車 / 腳踏）、衍生 hour / time_period。
欄位 `risk_score`（A1=3/A2=2）為 ETL 簡易標籤；後端 `risk_engine` 會另行重算正規化風險。

要用自己的資料：把符合欄位格式的 cleaned CSV 放到別處，執行
`prepare_accidents_gpkg.py --cleaned-dir <你的目錄>`（Docker 下設 `CLEANED_CSV_DIR`）。
