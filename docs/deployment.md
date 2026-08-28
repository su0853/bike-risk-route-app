# Deployment / 環境重建指南

本文件說明如何在新環境從明確來源重建並啟動「可跑的 main」。
涵蓋後端（本機 venv 或 Docker）、資料重建、前端；正式 HTTPS 部署屬後續。

Git 只同步原始碼，不含大型資料檔、`.env`、API key。下列步驟補齊這些。

---

## 資料流概觀

```
政府 A1/A2 CSV ─download_accidents_raw.py→ data/accidents_raw/ ─etl_accidents.py→ data/cleaned/  (repo 已 bundle，預設可跳過這兩步)
data/cleaned/ ─prepare_accidents_gpkg.py→ data/raw/accidents_epsg3857.gpkg ─┐
Geofabrik gpkg.zip ─download_roads_geofabrik.py→ data/raw/gis_osm_roads_free_1.gpkg ─┤
                                                                                     ├─ build_graph.py → taiwan_graph.pkl + roads_gdf.pkl
                                                                                     └─ process_accidents.py → risk_scores.json
後端啟動時載入 processed artifacts（pkl / json）
```

---

## 1. 後端

後端可**擇一**：本機 venv（1.1–1.4）或 **Docker（1.5，交接到未知環境時推薦）**。

### 1.1 環境

- Python 3.11–3.13

```bash
cd backend
python -m venv .venv
# Bash:        source .venv/bin/activate
# PowerShell:  .venv\Scripts\Activate.ps1
pip install -e .               # 開發另加: pip install -e ".[dev]"
```

### 1.2 環境變數

```bash
cp .env.example .env
# 編輯 .env，至少填入 GOOGLE_ROUTES_API_KEY（後端呼叫 Google Routes API 用）
```

其餘資料路徑有預設值，通常不需修改。API key 分兩把、各自限制：後端 `GOOGLE_ROUTES_API_KEY`
（Routes API，放 `backend/.env`，靠保密）；前端 `GOOGLE_MAPS_ANDROID_KEY`（Maps SDK for Android，
build 時注入 AndroidManifest，靠 package + SHA-1 限制而非保密）。前端地圖 key 分平台與執行環境：Android 需此 key；iOS 用 Apple Maps 免 key；Expo Go 內測試用 Expo 內建地圖、不會用到你的 key（Cloud 因此無 Maps SDK 用量），你的 key 只在 dev build / APK 生效。

### 1.3 重建資料（可重現）

事故的 cleaned CSV **已隨 repo bundle 在 `backend/data/cleaned/`**（自行車事故，107–109，見該目錄
`SOURCE.md`），預設可直接用；道路由腳本從 Geofabrik URL 下載。

在 `backend/` 依序執行：

```bash
# a. 事故 cleaned CSV → EPSG:3857 GPKG（用 bundle 的 data/cleaned）
python -m scripts.prepare_accidents_gpkg

# b. 下載道路 → 單圖層 GPKG（~266MB 下載）
python -m scripts.download_roads_geofabrik

# c. 建立路網圖（含路口拓撲修復）→ taiwan_graph.pkl + roads_gdf.pkl
python -m scripts.build_graph

# d. 計算路段風險 → risk_scores.json
python -m scripts.process_accidents
```

**從政府源頭重建 cleaned（選用；要更新年度或稽核 ETL 流程時）**：

```bash
python -m scripts.download_accidents_raw   # 政府 A1/A2 原始 CSV → data/accidents_raw/
python -m scripts.etl_accidents            # 清洗（民國年、死傷拆分、自行車篩選）→ data/cleaned/
```

要用**自己的資料**：`python -m scripts.prepare_accidents_gpkg --cleaned-dir <你的目錄>`。

參考產出規模（實測）：事故 60,953 筆、道路 815,690 條、graph 1.35M 節點 / 1.75M 邊、
snap 成功率 ~94.85%。

**資料檔大小與磁碟需求**（實測）：

| 檔案 | 大小 | runtime 必需 |
|------|------|:---:|
| `data/raw/gis_osm_roads_free_1.gpkg` | ~248 MB | 建圖用 |
| `data/raw/accidents_epsg3857.gpkg` | ~11 MB | 算風險用 |
| `data/processed/taiwan_graph.pkl` | ~368 MB | 是（啟動載入）|
| `data/processed/roads_gdf.pkl` | ~162 MB | 是（啟動載入）|
| `data/processed/risk_scores.json` | ~15 MB | 是（啟動載入）|
| `data/processed/*.gpkg`（QGIS 匯出）| ~1.4 GB | 否（僅視覺化）|

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

# 3. 重建資料（一次性；對應 1.3）。cleaned 已 bundle 在 ./backend/data/cleaned，
#    隨 volume 掛到 /app/data/cleaned，所以預設不需 CLEANED_CSV_DIR
docker compose run --rm backend python -m scripts.prepare_accidents_gpkg
docker compose run --rm backend python -m scripts.download_roads_geofabrik   # 容器內連網下載 ~266MB
docker compose run --rm backend python -m scripts.build_graph
docker compose run --rm backend python -m scripts.process_accidents

# 4. 啟動 API（publish 8000）
docker compose up backend
curl http://localhost:8000/api/health
```

若要用**自己的外部 cleaned 目錄**，用 `CLEANED_CSV_DIR` 掛入（唯讀）再指定 `--cleaned-dir /input/cleaned`：

```bash
# Bash
CLEANED_CSV_DIR=/path/to/cleaned docker compose run --rm backend \
  python -m scripts.prepare_accidents_gpkg --cleaned-dir /input/cleaned
```

```powershell
# PowerShell
$env:CLEANED_CSV_DIR = "C:\path\to\cleaned"
docker compose run --rm backend python -m scripts.prepare_accidents_gpkg --cleaned-dir /input/cleaned
```

（PowerShell 健康檢查用 `curl.exe`，因 PS 的 `curl` 是 `Invoke-WebRequest` 別名。）

設計要點：

- image 只含程式碼 + Python 依賴；**大資料與 secret 不進 image**。
- `./backend/data` 以 volume 掛載 → raw / processed 產物保存在 host、與本機路徑一致、可保留重用。
- `CLEANED_CSV_DIR` 是 **compose 的插補變數**（外部 cleaned CSV 路徑），與 app 的 `backend/.env` 是兩件事。
- 002 PostGIS 之後會在同一個 `docker-compose.yml` 加 `postgis` service（backend service 不變）。

---

## 2. 前端（Expo / main）

### 2.1 環境變數（必須在 build / 啟動前設好）

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

> Windows 的 nvm-windows 不會讀 `.nvmrc`，請改用 `nvm install 22` + `nvm use 22`。

### 2.4 啟動 / 打包

```bash
npx expo start            # 開發（Expo Go / development build）
# 實機建議 development build 或打包 APK；build 前務必先設好 .env
```

> native build（APK）＝ **本機、Android-first、先不考慮 EAS**；turn-by-turn（Navigation SDK）尚未整合，屬後續。

### 2.5 Tailscale 開發：裝置連 Metro（dev-only）

用 Expo Go / development build 在實機開發時有**兩條連線**，兩個變數各管一條：

| 連線 | 變數 | 說明 |
|------|------|------|
| 裝置 → Metro dev server | `REACT_NATIVE_PACKAGER_HOSTNAME` | 讓 Metro 對外宣告 tailnet IP，手機才連得到 Metro 抓 JS bundle / 熱更新。**dev-only，打包 APK 後不需要** |
| app → 後端 API | `EXPO_PUBLIC_API_BASE_URL` | app 取路線 / 地址的後端位址（見 2.2）|

Tailscale 下 `expo start` 預設宣告 LAN IP，手機連不到，需指定 tailnet IP：

```bash
# Bash
REACT_NATIVE_PACKAGER_HOSTNAME=100.x.y.z npx expo start
```

```powershell
# PowerShell（已驗證可用）
$env:REACT_NATIVE_PACKAGER_HOSTNAME="100.x.y.z"; npx expo start
```

驗證：`expo start` 印出的位址是 `exp://100.x.y.z:8081`（tailnet IP）而非 `192.168.x.x`，手機即可連上。

> **也可寫進 `frontend/.env`（已驗證可用）**：加 `REACT_NATIVE_PACKAGER_HOSTNAME=100.x.y.z`。
> Expo CLI 會把 .env 載入 process 環境，純 `npx expo start`（不加 `$env:`）即可讓 Metro 宣告 tailnet IP —— 跨平台最省事，Windows 也免打 `$env:`。

---

## 3. 常見問題

| 症狀 | 可能原因 | 處理 |
|------|---------|------|
| `Network request failed` | `.env` 在 build 之後才設 / 用了 `localhost` / 後端沒綁 `0.0.0.0` | build 前設好 `EXPO_PUBLIC_API_BASE_URL`，用開發機可連位址，後端 `--host 0.0.0.0` |
| 地圖米白（無 tiles） | Maps SDK for Android 未啟用 / billing 未掛 / key 授權問題 | 確認 Cloud 專案已啟用 Maps SDK for Android + billing；Nav SDK 另需向 Google 申請專案開通 |
| 後端啟動報缺資料檔 | processed artifacts 不存在 | 執行第 1.3 節（或 1.5 Docker）的資料重建 |
| `prepare_accidents_gpkg` 找不到 CSV | 預設讀 bundled `data/cleaned`，若被清空或自備資料路徑錯 | 確認 `backend/data/cleaned/*.csv` 存在；自備資料用 `--cleaned-dir`（Docker 設 `CLEANED_CSV_DIR`）|
| `docker compose` 報 `env file ... not found` | 尚未建立 `backend/.env` | 先 `cp backend/.env.example backend/.env` |
| Docker build 很慢 / context 很大 | `backend/.dockerignore` 缺失或未排除 `data/`、`.venv/` | 確認 `backend/.dockerignore` 存在（排除這些，約 2.7GB）|
| 手機連不上 Metro（Unable to connect to development server）| Tailscale 下 Metro 宣告 LAN IP，手機連不到 | 設 `REACT_NATIVE_PACKAGER_HOSTNAME` 為 tailnet IP（見 2.5）|
| 實機 Metro 正常但 `/api/*` 逾時（Windows + Docker）| Windows 防火牆 `Docker Desktop Backend` 的 inbound Block 規則擋掉容器 published port | 停用該 Block 規則 + 放行 8000（見第 4 節）|

---

## 4. Windows + Docker + Tailscale 註記

實機經 Tailscale 測試時，Metro（`node.exe`）通常已被防火牆放行，但 **Docker 發布的後端 port 8000 可能被擋**，症狀是「Metro 正常、`/api/*` 逾時」。

原因：Windows Defender Firewall 有一條 `Docker Desktop Backend` 的 inbound **Block** 規則。Windows 防火牆 **Block 優先於 Allow**，所以只加一條 8000 的 Allow 規則無效，必須先停用該 Block 規則。

> **以系統管理員身分執行 PowerShell**（修改防火牆規則需要提權，否則指令會失敗或找不到規則）。
> 開始選單搜尋 PowerShell → 右鍵「以系統管理員身分執行」；或 Win+X →「終端機（系統管理員）」。

執行：

```powershell
# 1. 停用 Docker Desktop Backend 的 inbound Block 規則
Get-NetFirewallRule -DisplayName "Docker Desktop Backend" |
  Where-Object { $_.Action -eq "Block" -and $_.Direction -eq "Inbound" } |
  Set-NetFirewallRule -Enabled False

# 2. 明確放行 8000 inbound
New-NetFirewallRule -DisplayName "Bike backend 8000 (dev)" -Direction Inbound `
  -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any
```

驗證：手機瀏覽器或另一台 tailnet 裝置開 `http://<tailnet-ip>:8000/api/health`，回 `{"status":"ok",...}` 即通。

注意：Docker Desktop 重啟 / 更新後可能把 Block 規則加回來，逾時重現就再停用一次。

其他 Windows 差異彙整：

- venv 啟動：`.venv\Scripts\Activate.ps1`（見 1.1）。
- Node 版本：nvm-windows 用 `nvm install 22` + `nvm use 22`（不讀 `.nvmrc`，見 2.3）。
- 行內環境變數：PowerShell 用 `$env:VAR="..."; cmd`，非 bash 的 `VAR=... cmd`。
- 健康檢查：PowerShell 用 `curl.exe`（`curl` 是 `Invoke-WebRequest` 別名）。

---

## 5. PostGIS（選用）— 資料檢視 / QGIS

定位：PostGIS 作為**真相來源 / 查詢 / QGIS 圖層**；**API runtime 目前不依賴它**（backlog 002 Wave 1）。
平常跑 API 不需要起它，只有要用 QGIS 疊圖或做 SQL 查詢時才起。先完成 §1.3 產生
`roads_gdf`/`taiwan_graph`/`risk_scores`/`accidents` 等產物，再匯入 DB。欄位定義見
[`data_dictionary.md`](data_dictionary.md)。

### 5.1 起資料庫

```bash
docker compose up -d postgis     # healthy 後即可連
```

- image 用 `imresamu/postgis:16-3.4`（多架構，含 **arm64**；官方 `postgis/postgis` 目前僅 amd64）。
- 資料存命名 volume `pgdata`（不進 repo）。連線：host `localhost`、port `5432`、db `bikerisk`、
  user `bikerisk`、密碼見 `POSTGRES_PASSWORD`（開發預設 `bikerisk_dev`，正式部署請換）。

### 5.2 匯入資料

需要 `[db]` 依賴（sqlalchemy / geoalchemy2 / psycopg）。**host 端執行**（後端 venv）：

```bash
cd backend
pip install -e ".[db]"                                       # 一次性
python -m scripts.load_to_postgis                            # 全部表
python -m scripts.load_to_postgis --tables roads,accidents,road_risk   # 只灌部分
```

- host 端預設連 `localhost:5432`。冪等（`if_exists="replace"`，可重跑）。
- 載入約 1.5 分：`roads`/`road_risk` 788k、`accidents` 61k、`graph_nodes` 1.35M、`graph_edges` 1.75M，
  另建 `roads_with_risk` view。
- **不讀 `roads_gdf.pkl`**：它跨 pandas 版本無法反序列化，script 改用 `load_and_filter_roads` 現算。

> 容器內執行（`docker compose run --rm backend python -m scripts.load_to_postgis`，DB host 自動為 `postgis`）
> 需先讓 backend image 含 `[db]`：把 `backend/Dockerfile` 的 `pip install -e .` 改成 `pip install -e ".[db]"` 重建。

### 5.3 QGIS 連線

Data Source Manager → PostgreSQL → New：host `localhost`、port `5432`、db `bikerisk`、填 user/密碼。
加圖層 `roads` / `accidents` / `graph_edges`；風險著色用 view `roads_with_risk` 的 `normalized_risk`。

> **著色提醒**：約 95% 道路 `normalized_risk = 0`，直接用 Natural Breaks (Jenks) 會讓前幾組全是
> `0.000–0.000`。先對圖層加過濾 **`normalized_risk > 0`** 再分級，才看得到層次。這是資料本身的零膨脹，
> 屬風險校準（backlog 004）範圍。

### 5.4 實務註記

- **arm64**：官方 `postgis/postgis` 僅 amd64，起容器會 `exec format error`；本 compose 已改用多架構的
  `imresamu/postgis`。
- **預設擴充**：image 開機會啟用 `postgis_tiger_geocoder` + `postgis_topology`，多出 `tiger` / `tiger_data` /
  `topology` schema（美國地址地理編碼 / 拓撲，本專案不用）。**它們是空的、無害，放著不動即可。**
  只有在想要乾淨 schema 清單時才需要（選用，且每次全新 `docker compose up` 會再出現）：
  ```sql
  DROP EXTENSION IF EXISTS postgis_tiger_geocoder CASCADE;   -- 移除 tiger / tiger_data
  DROP EXTENSION IF EXISTS postgis_topology CASCADE;         -- 移除 topology；保留 postgis
  ```
- **停止 / 清除**：`docker compose stop postgis`（資料留在 `pgdata`）；`docker compose down -v` 會**刪除 volume**（資料清空）。
- Windows：連線 host 同為 `localhost`；venv 啟動與行內環境變數差異見 §1、§4。
