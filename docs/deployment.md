# Deployment / 環境重建指南

本文件說明如何在新環境從明確來源重建並啟動「可跑的 main」。
範圍為第一波（最小可重現路徑）；Docker、正式 HTTPS 部署等屬後續。

Git 只同步原始碼，不含大型資料檔、`.env`、API key。下列步驟補齊這些。

---

## 資料流概觀

```
政府 A1/A2 事故 CSV ──(外部 ETL)──> cleaned CSV ──┐
                                                  ├─> prepare_accidents_gpkg.py ─> accidents_epsg3857.gpkg ─┐
Geofabrik taiwan gpkg.zip ──(URL 下載)────────────────> download_roads_geofabrik.py ─> gis_osm_roads_free_1.gpkg ─┤
                                                                                                                  ├─> build_graph.py ─> taiwan_graph.pkl + roads_gdf.pkl
                                                                                                                  └─> process_accidents.py ─> risk_scores.json
                                                                                       後端啟動時載入以上 processed artifacts
```

---

## 1. 後端

### 1.1 環境

- Python 3.11–3.13

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .               # 開發另加: pip install -e ".[dev]"
```

### 1.2 環境變數

```bash
cp .env.example .env
# 編輯 .env，至少填入 GOOGLE_ROUTES_API_KEY（後端呼叫 Google Routes API 用）
```

其餘資料路徑有預設值，通常不需修改。API key 配置另見
[../docs/decision_log.md](./decision_log.md) 與 backlog 的「Google Cloud 配置建議」。

### 1.3 重建資料（可重現）

需要兩個上游來源：

- **事故**：政府 A1/A2 CSV 經外部 ETL 專案（例：`~/projects/data/`，見其 `ETL流程說明_v3.0.md` +
  `scripts/etl_all.py`）產生分年度 `*_A1A2_bike_cleaned.csv`。
- **道路**：Geofabrik 台灣 free gpkg（腳本自動由 URL 下載）。

在 `backend/` 依序執行：

```bash
# a. 事故 cleaned CSV → EPSG:3857 GPKG
python -m scripts.prepare_accidents_gpkg \
    --cleaned-dir /home/su2270853/projects/data/cleaned \
    --output data/raw/accidents_epsg3857.gpkg

# b. 下載道路 → 單圖層 GPKG（~266MB 下載）
python -m scripts.download_roads_geofabrik

# c. 建立路網圖（含路口拓撲修復）→ taiwan_graph.pkl + roads_gdf.pkl
python -m scripts.build_graph

# d. 計算路段風險 → risk_scores.json
python -m scripts.process_accidents
```

參考產出規模（實測）：事故 60,953 筆、道路 815,690 條、graph 1.35M 節點 / 1.75M 邊、
snap 成功率 ~94.85%。

### 1.4 啟動 API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- `--host 0.0.0.0`：讓實機／其他裝置能連（`localhost` 只綁本機）。
- 健康檢查：`curl http://localhost:8000/api/health`
- 主要端點：`GET /api/geocode`、`POST /api/navigate`

---

## 2. 前端（Expo / main）

### 2.1 環境變數（⚠️ 必須在 build/啟動前設好）

```bash
cd frontend
cp .env.example .env
# 編輯 .env
```

`EXPO_PUBLIC_*` 在 Metro build 時就烤進 bundle，**build 之後才改不會生效**。

### 2.2 後端連線模式

| 模式 | `EXPO_PUBLIC_API_BASE_URL` | 適用 |
|------|----------------------------|------|
| LAN | `http://192.168.x.x:8000` | 手機與後端同一區網 |
| Tailscale | `http://100.x.y.z:8000` 或 MagicDNS `http://<host>.<tailnet>.ts.net:8000` | 跨網段 / 遠端 build 機連回後端 |
| Android Emulator | `http://10.0.2.2:8000` | 模擬器對應 host loopback |

實機測試切記：後端要以 `0.0.0.0` 監聽，且防火牆放行 8000 埠。

### 2.3 啟動 / 打包

```bash
npm install
npx expo start            # 開發（Expo Go / development build）
# 實機建議 development build 或打包 APK；build 前務必先設好 .env
```

---

## 3. 常見問題

| 症狀 | 可能原因 | 處理 |
|------|---------|------|
| `Network request failed` | `.env` 在 build 之後才設 / 用了 `localhost` / 後端沒綁 `0.0.0.0` | build 前設好 `EXPO_PUBLIC_API_BASE_URL`，用開發機可連位址，後端 `--host 0.0.0.0` |
| 地圖米白（無 tiles） | Maps SDK for Android 未啟用 / billing 未掛 / key 授權問題 | 見 backlog 003 與「Google Cloud 配置建議」 |
| 後端啟動報缺資料檔 | processed artifacts 不存在 | 執行第 1.3 節的資料重建腳本 |
| `prepare_accidents_gpkg` 找不到 CSV | `--cleaned-dir` 指錯 | 指向外部 ETL 的 `cleaned/` 目錄 |
