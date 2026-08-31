# Bike Risk Route App

Bike Risk Route App 是一個台灣自行車安全路線規劃 prototype。系統結合 OpenStreetMap 路網、歷史交通事故資料、Google Routes API 候選路線，以及本地風險加權 Dijkstra 路線，回傳多條可比較的路線並在前端地圖顯示風險資訊。

本專案目前定位為 **self-deploy research / prototype**：使用者自行準備資料、設定 API key、啟動後端與前端；目前不提供公開託管服務。

---

## Features

- 地址搜尋與多候選選擇：前端透過後端 `/api/geocode` proxy 查詢 Nominatim，避免行動端直接呼叫造成 403 或候選誤選。
- 目前位置起點：前端可用 `expo-location` 取得使用者 GPS 座標。
- 風險加權安全路線：後端以歷史事故資料計算道路風險，並用 Dijkstra 產生本地安全路線。
- Google Routes alternatives：後端呼叫 Google Routes API 取得自行車候選路線，再評估其風險。
- 前端地圖顯示：Expo / React Native 顯示路線、風險等級、距離與時間。
- 可重現後端資料管線：本機 Python 或 Docker 重建道路圖與風險分數。

---

## Project Status

目前 main 分支重點：

```text
可重現資料重建 -> 後端 API -> Expo 前端地圖顯示
```

尚未完成 / 待驗證：

- turn-by-turn navigation：Google / Mapbox Navigation SDK 仍在 prototype 驗證階段。
- 風險模型校準：目前係數與 P99 normalization 為 heuristic，仍需以 QGIS / notebook / 實際案例校準。
- DB 端路由：runtime 已以 PostGIS 為資料來源（roads/accidents primary + 衍生表）；把路由（Dijkstra）搬進 DB（pgRouting）為後續研究方向（prototype 已驗證可行）。

---

## Architecture Overview

```text
使用者輸入起終點
      |
      v
Frontend (Expo / React Native)
      |  GET /api/geocode
      |  POST /api/navigate
      v
Backend (FastAPI)
      |-- Local risk-weighted Dijkstra route
      |-- Google Routes API alternatives
      |-- Route risk evaluation
      v
Route response（geometry, risk score, distance, duration）
      |
      v
Frontend map display
```

後端所需的道路圖與風險分數由**可重現的管線**產生（Geofabrik 道路 + 政府事故資料 → PostGIS 的 `roads` / `accidents` / `road_risk` + `taiwan_graph.pkl` 圖快取）；實際指令見 [Quick Start](#quick-start)，內部機制（拓撲修復、KDTree、風險計算）見 [`ARCHITECTURE.md`](./ARCHITECTURE.md)。

---

## Quick Start

詳細步驟見 [`docs/deployment.md`](./docs/deployment.md)。以下為最短流程。

### 1. Backend with Docker（PostGIS-backed）

後端以 **PostGIS 為資料來源**：roads / accidents 存 DB，API 啟動時從 DB 載；路網圖以 `taiwan_graph.pkl` 快取（NetworkX 不進 DB）。

```bash
cp backend/.env.example backend/.env
# 編輯 backend/.env，設定 GOOGLE_ROUTES_API_KEY

docker compose build backend
docker compose up -d postgis          # 啟動資料庫

# 種入 DB primary（原始檔 → DB 的 roads / accidents）
# cleaned CSV 已 bundle 在 backend/data/cleaned，預設免 CLEANED_CSV_DIR
docker compose run --rm backend python -m scripts.prepare_accidents_gpkg
docker compose run --rm backend python -m scripts.download_roads_geofabrik
docker compose run --rm backend python -m scripts.load_to_postgis --tables roads,accidents

# 由 DB 衍生（拓撲修復 → taiwan_graph.pkl 快取 + road_risk / graph_* / view）
docker compose run --rm backend python -m scripts.rebuild_from_db

docker compose up backend             # API：圖讀 pkl、roads/risk 讀 DB
```

> 之後在 DB 編輯 roads / accidents → 重跑 `rebuild_from_db`（自動偵測變動、只重建需要的部分：只改事故約 17s、改道路約 78s）→ 重啟 backend。

Health check：

```bash
curl http://localhost:8000/api/health
```

### 2. Frontend

```bash
cd frontend
nvm use
npm ci
cp .env.example .env
# 編輯 .env：
#   EXPO_PUBLIC_API_BASE_URL=http://<backend-host>:8000
#   GOOGLE_MAPS_ANDROID_KEY=<your Android Maps SDK key>

npx expo start
```

實機測試不能用 `localhost` 作為 backend URL，請用 LAN IP、Tailscale IP / MagicDNS，或 Android emulator 的 `10.0.2.2`。詳見 [`docs/deployment.md`](./docs/deployment.md)。

---

## Configuration

Backend：

- `GOOGLE_ROUTES_API_KEY`：後端呼叫 Google Routes API。
- data paths：`backend/.env.example` 已提供預設路徑，通常不需修改。

Frontend：

- `EXPO_PUBLIC_API_BASE_URL`：前端呼叫後端 API 的固定 URL，需在 build / `expo start` 前設定。
- `GOOGLE_MAPS_ANDROID_KEY`：Android 地圖用（Google Maps SDK for Android），prebuild / build 時注入 AndroidManifest。

地圖 key 的平台與執行環境差異（react-native-maps 未指定 provider，用平台預設）：

- Android（dev build / APK）：用 Google Maps SDK for Android，需 `GOOGLE_MAPS_ANDROID_KEY`。
- iOS：用平台預設 Apple Maps，**不需 Google key**（未設 `PROVIDER_GOOGLE`；改用 Google 才需 iOS Maps key）。
- Expo Go：地圖用 Expo 內建的 Google Maps，**不會用到你的 key**（故 Cloud 不會出現 Maps SDK 用量）；你的 key 只在 dev build / 打包 APK 時生效。

Google key 原則：

- 後端 Routes key 放 `backend/.env`，不進前端。
- 前端 Maps Android key 會進 APK，安全性靠 package name + SHA-1 + API restrictions，而非保密。
- Navigation SDK key / route token 等議題屬後續 prototype 驗證。

---

## Data

大型資料與產物不放入 git（道路 gpkg、pkl、政府原始 CSV 等）。例外：自行車事故 cleaned CSV（`backend/data/cleaned/`，約 6.7MB，政府開放資料）已 bundle，讓 clone 後可直接重建；來源見該目錄 `SOURCE.md`。

Runtime 需要（DB-centric）：

- **PostGIS**：`roads` / `accidents`（primary，可在 DB 直接編輯）+ `road_risk` 等衍生表。
- `backend/data/processed/taiwan_graph.pkl`：路網圖快取（NetworkX 不進 DB）。

兩者皆由 `scripts/rebuild_from_db`（讀 DB primary → 建圖 pkl + 刷新衍生表）產生。
QGIS 疊圖直接連 PostGIS（見 [`docs/deployment.md`](./docs/deployment.md) §5）。
`roads_gdf.pkl` / `risk_scores.json` 為舊檔案管線產物，DB-centric runtime 已不使用。

---

## Documentation

- [`docs/deployment.md`](./docs/deployment.md)：環境重建、Docker、資料管線、前端啟動。
- [`ARCHITECTURE.md`](./ARCHITECTURE.md)：系統架構、資料流、API、前後端模組。
- [`docs/risk_score_methodology.md`](./docs/risk_score_methodology.md)：風險分數計算方法、公式、限制。
- [`docs/data_dictionary.md`](./docs/data_dictionary.md)：各資料檔的欄位、型別、意義與座標系。
- [`notebooks/`](./notebooks/)：探索 / 驗證用的 Jupyter notebook（視覺化拓撲修復等 pipeline 內部過程）；非必要，需要檢視時再操作，說明見 [`notebooks/README.md`](./notebooks/README.md)。

---

## Repository Layout

```text
backend/
  app/                 FastAPI app, routers, services
  scripts/             資料準備 / 匯出腳本
  data/                raw / processed 不進 git；cleaned CSV 已 bundle

frontend/
  app/                 Expo Router screens
  components/          UI 元件
  services/            API / geocoder client
  hooks/               前端狀態 hooks
  types/               共用型別

docs/
  deployment.md
  risk_score_methodology.md

notebooks/             探索 / 驗證用 Jupyter notebook（.ipynb 進 git）

ARCHITECTURE.md
docker-compose.yml
```

---

## Limitations

- Risk scoring is heuristic and not yet calibrated against validated safety outcomes.
- EPSG:3857 is used for metric spatial operations in the current phase; practical but with known distance distortion.
- Google Routes alternatives and local Dijkstra routes may differ in road network assumptions.
- Turn-by-turn navigation is not part of main yet; Navigation SDK integration is a separate prototype topic.
- This is a self-deploy prototype, not a hosted public service.
