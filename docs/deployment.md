# Deployment / 環境重建指南

本文件說明如何在新環境從明確來源重建並啟動「可跑的 main」。
涵蓋後端（本機 venv 或 Docker）、資料重建、前端；正式 HTTPS 部署屬後續。

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

後端可**擇一**：本機 venv（1.1–1.4）或 **Docker（1.5，交接到未知環境時推薦）**。

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

**資料檔大小與磁碟需求**（實測）：

| 檔案 | 大小 | runtime 必需 |
|------|------|:---:|
| `data/raw/gis_osm_roads_free_1.gpkg` | ~248 MB | 建圖用 |
| `data/raw/accidents_epsg3857.gpkg` | ~11 MB | 算風險用 |
| `data/processed/taiwan_graph.pkl` | ~368 MB | ✅ |
| `data/processed/roads_gdf.pkl` | ~162 MB | ✅ |
| `data/processed/risk_scores.json` | ~15 MB | ✅ |
| `data/processed/*.gpkg`（QGIS 匯出）| ~1.4 GB | ❌（僅視覺化）|

- 後端啟動只需 processed 三個核心檔（~545 MB）；raw（~260 MB）僅重建時需要。
- QGIS 匯出（`risk_scores.gpkg` / `taiwan_graph.gpkg` / `osmnx_*.gpkg`，~1.4 GB）**非 runtime 必需**，可另存或刪除。
- 完整重建（含下載 266 MB 道路 zip）建議預留 **~4 GB** 空閒磁碟。

**Fast-path（方案 B，未來選項）**：若不想完整重建，之後可提供 processed 三個核心檔（~545 MB）
的下載（GitHub Releases / 雲端），clone 後放到 `data/processed/` 直接啟動。目前尚未提供，
以完整重建為主。

### 1.4 啟動 API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- `--host 0.0.0.0`：讓實機／其他裝置能連（`localhost` 只綁本機）。
- 健康檢查：`curl http://localhost:8000/api/health`
- 主要端點：`GET /api/geocode`、`POST /api/navigate`

### 1.5 用 Docker 跑後端（替代 1.1–1.4）

前提：安裝 Docker + Docker Compose。指令都在 **repo 根目錄**執行。優點：不必在 host 裝
Python / GIS 依賴，跨 OS / 晶片（Intel / Apple Silicon / arm64）皆可重現。

```bash
# 1. 建立 image（GIS wheels 自帶 GDAL，無需系統套件）
docker compose build backend

# 2. 環境變數：一樣需要 backend/.env（見 1.2）；compose 以 env_file 注入
cp backend/.env.example backend/.env   # 編輯填入 GOOGLE_ROUTES_API_KEY

# 3. 重建資料（一次性；對應 1.3）。外部 cleaned CSV 目錄用 CLEANED_CSV_DIR 掛入（唯讀）
CLEANED_CSV_DIR=/path/to/data/cleaned \
  docker compose run --rm backend \
  python -m scripts.prepare_accidents_gpkg --cleaned-dir /input/cleaned --output data/raw/accidents_epsg3857.gpkg
docker compose run --rm backend python -m scripts.download_roads_geofabrik   # 容器內連網下載 ~266MB
docker compose run --rm backend python -m scripts.build_graph
docker compose run --rm backend python -m scripts.process_accidents

# 4. 啟動 API（publish 8000）
docker compose up backend
curl http://localhost:8000/api/health
```

設計要點：

- image 只含程式碼 + Python 依賴；**大資料與 secret 不進 image**。
- `./backend/data` 以 volume 掛載 → raw / processed 產物保存在 host、與本機路徑一致、可保留重用。
- `CLEANED_CSV_DIR` 是 **compose 的插補變數**（外部 cleaned CSV 路徑），與 app 的 `backend/.env` 是兩件事。
- 002 PostGIS 之後會在同一個 `docker-compose.yml` 加 `postgis` service（backend service 不變）。

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

**連線模型**：前端↔後端是 **HTTP REST（一問一答）**，非 WebSocket；backend 位址用**固定 URL**（build 時設），非區網廣播 / 自動探索。Tailscale 是**私有覆蓋網路**（給每台裝置穩定 `100.x` 位址、跨網路可達），**不是廣播** —— 它讓固定 URL 在任何網路都連得到，取代脆弱的「同區網 LAN IP」。區網廣播 / mDNS 跨不了子網、常被 AP isolation 擋，故不採用。turn-by-turn 若日後需即時定位串流，才會再評估 WebSocket。

### 2.3 Node 版本與依賴

```bash
cd frontend
nvm use          # 讀 .nvmrc（Node 22）；Expo 54 需 Node >= 20.19.4（見 package.json engines）
npm ci           # 依 package-lock.json frozen install（比 npm install 更可重現）
```

### 2.4 啟動 / 打包

```bash
npx expo start            # 開發（Expo Go / development build）
# 實機建議 development build 或打包 APK；build 前務必先設好 .env
```

> native build（APK）＝ **本機、Android-first、先不考慮 EAS**；Nav SDK 方向與框架選型見 backlog 003。

---

## 3. 常見問題

| 症狀 | 可能原因 | 處理 |
|------|---------|------|
| `Network request failed` | `.env` 在 build 之後才設 / 用了 `localhost` / 後端沒綁 `0.0.0.0` | build 前設好 `EXPO_PUBLIC_API_BASE_URL`，用開發機可連位址，後端 `--host 0.0.0.0` |
| 地圖米白（無 tiles） | Maps SDK for Android 未啟用 / billing 未掛 / key 授權問題 | 見 backlog 003 與「Google Cloud 配置建議」 |
| 後端啟動報缺資料檔 | processed artifacts 不存在 | 執行第 1.3 節（或 1.5 Docker）的資料重建 |
| `prepare_accidents_gpkg` 找不到 CSV | `--cleaned-dir` 指錯 | 指向外部 ETL 的 `cleaned/` 目錄；Docker 下設 `CLEANED_CSV_DIR` 並用 `--cleaned-dir /input/cleaned` |
| `docker compose` 報 `env file ... not found` | 尚未建立 `backend/.env` | 先 `cp backend/.env.example backend/.env` |
| Docker build 很慢 / context 很大 | `backend/.dockerignore` 缺失或未排除 `data/`、`.venv/` | 確認 `backend/.dockerignore` 存在（排除這些，約 2.7GB）|
