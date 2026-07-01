# 自行車安全導航系統 — 系統架構文件

## 目錄

1. [系統概覽](#1-系統概覽)
2. [整體資料流程](#2-整體資料流程)
3. [離線資料預處理](#3-離線資料預處理)
   - 3.1 路網圖建構
   - 3.2 事故風險分數計算
4. [後端服務架構](#4-後端服務架構)
   - 4.1 啟動載入
   - 4.2 路線規劃引擎
   - 4.3 Google Routes 整合
   - 4.4 路線風險評估
5. [API 設計](#5-api-設計)
6. [前端架構](#6-前端架構)
7. [關鍵設計決策](#7-關鍵設計決策)
8. [可調整參數](#8-可調整參數)

---

## 1. 系統概覽

本系統為台北地區自行車安全導航應用，核心功能為：

- 依據歷史交通事故資料，計算每條道路的風險分數
- 結合 Google Routes API 候選路線與本地 Dijkstra 安全路線，回傳多條帶有風險標註的路線
- React Native (Expo) 前端在地圖上以不同顏色顯示各路線及其風險等級

```
使用者輸入起終點
      │
      ▼
  前端 Geocoding（Nominatim）
      │ lat/lon
      ▼
POST /api/navigate
      │
      ├─── asyncio.gather ─────────────────────────────────┐
      │                                                     │
      ▼                                                     ▼
find_safest_route()                          fetch_cycling_routes()
Dijkstra + 風險加權圖                         Google Routes API v2
      │                                                     │
      └──────────────── evaluate_all_routes() ─────────────┘
                               │
                               ▼
                    NavigateResponse（3 條路線）
                               │
                               ▼
                        前端地圖顯示
```

---

## 2. 整體資料流程

```
[原始資料]
  gis_osm_roads_free_1.gpkg        Accidents_Snapped_Final.gpkg
  (Geofabrik Taiwan, 246 MB)        (QGIS 20m Snap, 13 MB)
          │                                    │
          ▼                                    ▼
  scripts/build_graph.py          scripts/process_accidents.py
          │                                    │
          ▼                                    ▼
  taipei_graph.pkl                   risk_scores.json
  (NetworkX MultiGraph)              (osm_id → [0, 1])
  roads_gdf.pkl
  (GeoDataFrame)
          │                                    │
          └───────────────┬───────────────────┘
                          │  FastAPI lifespan 載入至 app.state
                          ▼
                    /api/navigate
```

---

## 3. 離線資料預處理

### 3.1 路網圖建構（`scripts/build_graph.py`）

**輸入**：`gis_osm_roads_free_1.gpkg`（Geofabrik Taiwan，EPSG:3857）

**排除的道路類型**（`EXCLUDED_FCLASSES`）：
`motorway`, `motorway_link`, `trunk`, `trunk_link`, `steps`, `busway`, `bridleway`

#### 核心問題：路口拓撲修復

Geofabrik 以 OSM Way 為單位儲存道路，每條 Way 是一段完整 LineString（可橫跨多個路口）。直接用端點建圖會導致嚴重的連通性問題——路口交叉點落在 LineString 的中間座標，而非端點，兩條路因此無法共享節點。

**未修復前**：連通率僅約 11%（圖形幾乎全數斷裂）

#### 路口座標分割演算法

```
步驟 1：建立座標索引
  對所有道路的每個座標點（含中間點），以 1m 精度四捨五入
  建立 coord_1m → 道路集合 的索引

步驟 2：找路口座標
  intersection_set = { coord | 出現在 2 條以上道路的座標 }

步驟 3：在路口切割道路
  每條道路：找到所有屬於 intersection_set 的中間點索引
  → 在這些索引切割 LineString 為多個小段

步驟 4：建立 MultiGraph
  每段：(n_start, n_end) 為節點，保留 osm_id、fclass、length_m、geometry
```

**修復後**：連通率達 97%（1,312,781 節點，1,703,330 邊）

**輸出**：
- `taipei_graph.pkl`：NetworkX MultiGraph
- `roads_gdf.pkl`：篩選後的 GeoDataFrame（用於事故 Snap）

---

### 3.2 事故風險分數計算（`scripts/process_accidents.py`）

**輸入**：`Accidents_Snapped_Final.gpkg`（已在 QGIS 完成 Snap，60,953 筆，2018–2020）

#### 風險權重公式

```
嚴重程度分數：
  severity = death_count × RISK_A1_WEIGHT + injury_count × RISK_A2_WEIGHT
  預設：A1 = 3.0，A2 = 2.0（待 VSL 成本研究後更新）

時間衰減：
  decay_λ = ln(2) / RISK_DECAY_HALF_LIFE_YEARS  （預設 3 年，≈ 0.231/年）
  time_decay = exp(−decay_λ × years_ago)

複合權重：
  weight_i = severity_i × time_decay_i
```

#### 事故對應至道路

使用 `geopandas.sjoin_nearest()` 將事故點對應至最近道路路段：

- 容差：`SNAP_TOLERANCE_M = 20m`（QGIS 驗證：94.80% 成功率）
- 對應鍵：`osm_id`（Geofabrik OSM Way ID，與路網圖邊屬性一致）
- 同距離多重匹配：保留第一筆

#### 正規化

```
路段風險密度 = Σ weight_i / length_km

P99 截斷 + [0, 1] 縮放：
  clip_value = percentile(非零值, 99.0)
  normalized_risk = min(risk_density / clip_value, 1.0)
```

**輸出**：`risk_scores.json`
```json
{
  "12345678": 0.0,
  "87654321": 0.342,
  ...
}
```
鍵為 `osm_id` 字串，值為 [0, 1]（0 = 無紀錄事故）。

---

## 4. 後端服務架構

### 4.1 啟動載入（`app/main.py`）

FastAPI `lifespan` 在啟動時將三份資料載入 `app.state`：

| 屬性 | 來源 | 用途 |
|------|------|------|
| `app.state.graph` | `taipei_graph.pkl` | Dijkstra 路線規劃 |
| `app.state.roads_gdf` | `roads_gdf.pkl` | Google 路線空間 Join |
| `app.state.risk_scores` | `risk_scores.json` | 風險分數查詢 |

同時建立 KDTree（`scipy.spatial.cKDTree`）：

```python
# build_node_tree()
coords = np.array([[d["x"], d["y"]] for _, d in G.nodes(data=True)])
_node_tree = cKDTree(coords)  # EPSG:3857 座標
```

用途：將 WGS84 座標快速對應至最近圖節點（O(log n)）。

---

### 4.2 路線規劃引擎（`app/services/path_planner.py`）

#### 風險加權邊

```python
risk_weight = length_m × (1 + λ × normalized_risk)
```

- `λ`（lambda_coef）：安全偏好強度，預設 0.5，前端可調整至 5.0
- `normalized_risk = 0`：純距離最短路線
- `λ` 越大：路線越積極繞開高風險路段（距離可能增加）

#### Dijkstra 路線

```python
G_w = apply_risk_weights(G, risk_scores, lambda_coef)
node_path = nx.shortest_path(G_w, source, target, weight="risk_weight")
```

#### 路線統計與幾何

遍歷 `node_path` 的每條邊：

1. **長度加權風險**：`total_risk = Σ(risk × length) / Σlength`
2. **幾何合併**：取每條邊的 `geometry` 屬性（EPSG:3857 LineString）
3. **方向修正**：當 Dijkstra 從 v 往 u 走，但幾何儲存方向是 u→v 時，反轉座標
4. **座標轉換**：EPSG:3857 → WGS84（EPSG:4326）

#### 風險等級分類

| 分數 | 等級 |
|------|------|
| < 0.2 | `low`（綠） |
| 0.2 ~ 0.5 | `medium`（黃） |
| ≥ 0.5 | `high`（紅） |

---

### 4.3 Google Routes 整合（`app/services/google_routes.py`）

呼叫 Google Routes API v2：

```
POST https://routes.googleapis.com/directions/v2:computeRoutes
Header: X-Goog-FieldMask: routes.legs.polyline,routes.distanceMeters,routes.duration
Body:
  travelMode: BICYCLE
  computeAlternativeRoutes: true
```

- API Key 未設定時：靜默跳過，僅回傳本地安全路線
- 逾時（15 秒）或 API 錯誤：回傳空列表，不影響安全路線

---

### 4.4 路線風險評估（`app/services/route_evaluator.py`）

將 Google 回傳的 encoded polyline 轉換為風險標註路線：

```
1. polyline.decode(encoded_polyline) → [(lat, lon), ...]
2. 轉換為 GeoDataFrame（WGS84 → EPSG:3857）
3. gpd.sjoin_nearest(points_gdf, roads_gdf, max_distance=20m)
4. 去重相鄰重複 osm_id
5. 計算長度加權風險平均
```

最終由 `evaluate_all_routes()` 合併安全路線與 Google 路線，按 `total_risk_score` 升序排列。

---

## 5. API 設計

### `GET /api/health`

```json
{
  "status": "ok",
  "graph_loaded": true,
  "risk_scores_loaded": true,
  "node_count": 1312781,
  "edge_count": 1703330,
  "risk_score_count": 766454
}
```

---

### `POST /api/navigate`

**請求**：

```json
{
  "start": { "lat": 25.0174, "lon": 121.5398 },
  "end":   { "lat": 25.0330, "lon": 121.5654 },
  "lambda_coef": 0.5
}
```

| 欄位 | 說明 | 限制 |
|------|------|------|
| `start` / `end` | WGS84 座標 | 台灣範圍內（lat 21.5–25.5，lon 119–122.5） |
| `lambda_coef` | 安全偏好強度 | 0.0 ~ 5.0（預設 0.5） |

**回應**：

```json
{
  "status": "ok",
  "routes": [
    {
      "route_type": "safety_optimized",
      "geometry": {
        "type": "LineString",
        "coordinates": [[121.539, 25.017], ...]
      },
      "total_distance_m": 3882.3,
      "total_risk_score": 0.0019,
      "risk_category": "low",
      "waypoints": [[25.017, 121.539], ...]
    },
    {
      "route_type": "google_0",
      ...
    },
    {
      "route_type": "google_1",
      ...
    }
  ]
}
```

| 欄位 | 說明 |
|------|------|
| `route_type` | `safety_optimized` \| `google_0` \| `google_1` |
| `geometry.coordinates` | GeoJSON 標準順序 `[lon, lat]` |
| `waypoints` | React Native Maps 用，`[lat, lon]` 順序 |
| `total_risk_score` | 長度加權平均風險分數，0–1 |
| `risk_category` | `low` / `medium` / `high` |

---

## 6. 前端架構

```
frontend/
├── app/
│   ├── _layout.tsx          Expo Router 根佈局（Stack）
│   ├── index.tsx            搜尋畫面（地址輸入 + λ 滑桿）
│   ├── map.tsx              地圖畫面（react-native-maps，native 用）
│   └── map.web.tsx          地圖畫面（Leaflet，web 用）
├── components/
│   ├── SearchForm.tsx        起終點輸入 + λ 滑桿 + 送出按鈕
│   ├── RouteCard.tsx         單條路線卡片（距離 + RiskBadge）
│   ├── RouteList.tsx         底部橫向捲動路線列表
│   └── RiskBadge.tsx         風險等級標籤（綠/黃/紅）
├── hooks/
│   ├── useNavigate.ts        管理 API fetch 狀態（loading/error/routes）
│   └── useMapRegion.ts       地圖縮放範圍計算
├── services/
│   ├── api.ts               fetchRoutes()、fetchHealth()
│   └── geocoder.ts          Nominatim 地址 → lat/lon
└── types/
    └── navigation.ts         RouteResult、NavigateRequest/Response 型別
```

#### 平台分離策略

`react-native-maps` 為 native-only 模組，不支援 web。透過 Metro Bundler 的平台後綴機制處理：

- Native（iOS/Android）：`map.tsx` → `react-native-maps`
- Web：`map.web.tsx` → `Leaflet`（動態 import）

`metro.config.js` 額外 stub 掉 web 平台的 `react-native-maps` 引用，防止 native-only 模組被打包進 web bundle：

```js
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (platform === 'web' && moduleName === 'react-native-maps') {
    return { type: 'empty' };
  }
  ...
};
```

#### 路線顏色規範

| route_type | 顏色 |
|-----------|------|
| `safety_optimized` | 綠色 `#22c55e` |
| `google_0` | 藍色 `#3b82f6` |
| `google_1` | 橘色 `#f97316` |

---

## 7. 關鍵設計決策

### 為何不用 osmnx？

osmnx 直接從 OSM Overpass API 下載路網，需要網路連線。本專案使用本地 Geofabrik GPKG，全程離線處理，且與事故資料的 `osm_id` 完全對應（兩者均來自 OpenStreetMap 同一資料集），無需重新 Snap。

### 為何使用 osm_id 作為風險對應鍵？

事故資料在 QGIS 中 Snap 至 Geofabrik 道路，取得的是 Geofabrik 的 `osm_id`（即 OSM Way ID）。路網圖的每條邊也保留了原始 `osm_id`。兩邊共用同一鍵，無須額外的空間對應，查詢複雜度 O(1)。

### 為何使用 MultiGraph 而非 Graph？

OSM 資料中同兩節點間可能存在多條平行路段（如雙向道分開儲存、橋梁等）。`nx.MultiGraph` 允許平行邊，更忠實呈現實際路網結構。

### EPSG:3857 的使用

全程在投影座標系（EPSG:3857，公尺單位）下進行距離計算與空間操作，最後僅在輸出 API 回應時轉換為 WGS84。台灣緯度下 EPSG:3857 的距離誤差約 7–10%，Phase 1 直接使用，Phase 2 可加入修正係數（約 1.09）。

---

## 8. 可調整參數

以下參數均在 `backend/.env` 設定，無需修改程式碼：

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `RISK_A1_WEIGHT` | `3.0` | A1 死亡事故嚴重程度係數（待 VSL 研究更新） |
| `RISK_A2_WEIGHT` | `2.0` | A2 受傷事故嚴重程度係數 |
| `RISK_DECAY_HALF_LIFE_YEARS` | `3.0` | 時間衰減半衰期（年）|
| `RISK_CLIP_PERCENTILE` | `99.0` | 正規化截斷百分位數 |
| `SNAP_TOLERANCE_M` | `20.0` | 事故對應道路的最大距離（公尺）|
| `LAMBDA_DEFAULT` | `0.5` | 安全路線預設安全偏好強度 |
| `MAX_GOOGLE_ALTERNATIVES` | `2` | Google Routes 最多替代路線數 |

`lambda_coef` 亦可由前端使用者透過滑桿即時調整（範圍 0–5）。
