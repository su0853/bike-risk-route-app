# Discussion Backlog

本文件用來記錄尚未完全定案的問題、方法論討論、產品假設與後續可交給實作工具處理的任務。

這裡不追求立刻寫成完整規格，而是保留「為什麼這件事值得處理」與「目前有哪些選項」。

---

## 001. Geocoder 多候選地點選擇問題 ✅ 已完成

### 背景

前端地址查詢已改為呼叫後端 `/api/geocode`，由後端代理外部 geocoder，解決 Android 直接呼叫 Nominatim 時的 HTTP 403 問題。

### 已完成的項目

- `frontend/services/geocoder.ts`：新增 `geocodeAddressCandidates()` 回傳候選陣列；保留 `geocodeAddress()` 取第一筆相容舊流程
- `frontend/components/SearchForm.tsx`：實作多候選選擇 UI（`FieldState` interface 管理每個欄位的輸入、候選清單、已選定狀態）
- 起點與終點各自有獨立候選清單，兩端都選定後才顯示「搜尋路線」按鈕
- `frontend/app/index.tsx`：接收已選定的 `GeocoderResult`，直接組 `NavigateRequest`，不在主畫面重複 geocode
- `backend/app/routers/geocode.py`：已存在，回傳最多 5 筆候選，介面不需修改

### 後續待考慮（非緊急）

- 中期整理常見查詢案例，比較 Nominatim 與 Google Geocoding / Places API 的命中品質與成本
- 若使用者回饋 Nominatim 搜尋品質不足，再評估換供應商（後端介面 `/api/geocode` 可切換，前端不需改動）

---

## 002. 風險分數正規化與 QGIS 視覺化 ✅ 已完成

### 背景

風險計算流程：事故嚴重程度 × 時間衰減 → 對應 `osm_id` → 依路段累加 → 除以 `length_km` → P99 截斷 → 正規化到 [0, 1]

### 已完成的項目

- 新增 `backend/scripts/export_risk_layer.py`
- 輸出 `backend/data/processed/risk_scores.gpkg`，含 P95 / P99 / P99.5 三個圖層
- 輸出欄位：`osm_id, name, fclass, length_m, length_km, accident_count, weight_sum, raw_risk_density, normalized_risk, is_clipped`
- 執行結果：766,454 路段，其中 35,347 筆（4.6%）有事故，snap rate 94.79%，輸出 734 MB

### 後續待考慮（視 QGIS 觀察結果）

- 目前 A1/A2/death/injury 四個權重（3.0/1.5/2.0/1.0）為 heuristic，待參考 VSL 成本文獻後更新
- 時間衰減半衰期 3 年是否合理，可觀察 QGIS 圖層後評估
- 短路段因除以 `length_km` 可能異常偏高，若 QGIS 觀察明顯需調整
- P95 / P99 / P99.5 三個截斷的視覺差異，選出最合理截斷點後寫回 `config.py`

---

## 003. 導航功能：Google Navigation for React Native

### 003a. 「使用目前位置」起點功能 ✅ 已完成

- `frontend/components/SearchForm.tsx` 起點欄位旁新增「定位」按鈕
- 點按後：`requestForegroundPermissionsAsync()` → `getCurrentPositionAsync()` → 填入起點座標
- 顯示文字「目前位置」（不做 reverse geocoding），直接用座標送出
- 已在 iOS 與 Android 實體裝置上測試，兩端定位流程正常

---

### 003b. Google Navigation SDK — Prototype 驗證 🔄 進行中

#### 目標

驗證 `@googlemaps/react-native-navigation-sdk` 是否能在本專案 Expo / React Native 環境中正常運作，以及是否能沿安全路線 waypoints 導航。

#### 已完成步驟

**1. Expo Prebuild（切換至 bare workflow）**

Navigation SDK 需要修改原生 Android/iOS 設定，無法在 Expo managed workflow 中直接安裝。

```bash
cd frontend
npx expo prebuild --clean
```

- 產生 `frontend/android/` 與 `frontend/ios/` 目錄
- 這些目錄已加入 git（移除 `.gitignore` 中的排除規則）
- 對應分支：`feat/navigation-sdk`（與 `main` 分開，main 維持 managed workflow）

**2. 安裝 Navigation SDK**

```bash
npm install @googlemaps/react-native-navigation-sdk@0.16.3
```

版本選擇原因：0.16.3 是目前最新穩定版，支援 React Native 0.79+、New Architecture（TurboModules + Fabric）

**3. Android build 設定調整**

`frontend/android/gradle.properties`：
```
android.enableJetifier=true
newArchEnabled=true        # Navigation SDK 需要 New Architecture
```

`frontend/android/app/build.gradle`：
```groovy
compileOptions {
    coreLibraryDesugaringEnabled true
    sourceCompatibility JavaVersion.VERSION_11
    targetCompatibility JavaVersion.VERSION_11
}
dependencies {
    // Navigation SDK 7.6.1 需要 NIO flavor
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs_nio:2.1.4")
    ...
}
```

`desugar_jdk_libs` → `desugar_jdk_libs_nio` 是必要的（Navigation SDK 7.6.1 依賴 `java.nio.*`）

**4. Prototype Screen**

`frontend/app/nav_prototype.tsx`：使用 `useNavigationController` hook（SDK 正確 API，非直接呼叫 NavModule）

測試流程：
1. `navigationController.showTermsAndConditionsDialog()` → 使用者接受條款
2. `navigationController.init()` → 初始化 SDK session
3. `navigationController.setDestination({ position: { lat, lng } })` → 設定目的地
4. `navigationController.startGuidance()` → 啟動導航

從 `index.tsx` 首頁有「[Dev] Navigation SDK Prototype」按鈕可進入。

**5. Build 流程**

因 Linux 伺服器為 aarch64 架構，Android SDK 的 cmake 是 x86-64 ELF，無法在此執行 build。

改為：
1. 在 Linux 伺服器 push 到 `feat/navigation-sdk` 分支
2. 在 Windows 機器（含 Android Studio）clone/pull
3. 執行 `.\gradlew.bat assembleDebug`
4. APK 輸出：`android\app\build\outputs\apk\debug\app-debug.apk`

#### 目前狀態

APK build 進行中（Windows 端）。已修正 `desugar_jdk_libs_nio` 問題後重新 push。

#### 待驗證的問題

1. APK 能否成功 build（目前最新 build 含 NIO 修正，尚未確認結果）
2. `NavigationView` 元件能否在 Android 實機上渲染
3. `showTermsAndConditionsDialog()` 流程是否正常
4. SDK 能否以目的地座標啟動導航
5. 能否用 waypoint 陣列沿本專案安全路線導航（最關鍵的整合問題）

#### iOS 未開始

iOS 方向的 API key 設定、`Info.plist` 權限、CocoaPods 設定均尚未處理。建議 Android 驗證通過後再處理 iOS。

#### 後續決策點

- 若 SDK 能正常運作 + 支援 waypoint 導航 → 評估整合至 `map.tsx`，替換或補充現有路線顯示
- 若 SDK 無法使用自訂 waypoints（只能依目的地自行規劃）→ 考慮改用 deep link 呼叫 Google Maps App 導航，或放棄 turn-by-turn 保留靜態路線顯示

---

## 004. PostGIS — Docker Compose + Schema 設定

### 背景

目前後端的路網圖（NetworkX graph）與風險分數（dict）完全依賴 pkl/json 快取，存在以下限制：

- 資料只存在 server RAM 或本地檔案，QGIS 無法直接連接做空間視覺化
- 無法執行跨資料集的 SQL 空間查詢（例如：某行政區內風險最高的 10 條路段）
- 未來若多個服務需要存取路網或風險資料，pkl 不適合作為共享儲存
- 事故原始資料目前只存在 `.gpkg`，沒有統一的資料庫管理

### 預計架構

```
PostGIS (Docker)                    後端 FastAPI (RAM)
──────────────────                  ─────────────────────
roads           ←──── 啟動時讀取 ──→ roads_gdf (GeoDataFrame)
road_risk       ←──── 啟動時讀取 ──→ risk_scores (dict)
graph_edges     ←──── QGIS 視覺化
graph_nodes     ←──── QGIS 視覺化
accidents       ←──── 原始事故點

                                    taiwan_graph (NetworkX) ← pkl 快取
                                    KDTree (RAM)
                                    ↓
                                    Dijkstra → 路線
```

啟動策略（pkl 快取 + PostGIS 雙保險）：
1. 若 `taiwan_graph.pkl` 存在 → 直接讀（~10 秒）
2. 若不存在 → 從 PostGIS 讀 roads + risk → 重建 graph → 存 pkl（~30 秒）
3. 資料更新時：刪除 pkl → 下次啟動重建

### 待規劃

**Docker Compose 設定**

```yaml
# docker-compose.yml（草稿）
services:
  postgis:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: bike_risk
      POSTGRES_USER: bike
      POSTGRES_PASSWORD: (從 .env 讀取)
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./backend/sql/init.sql:/docker-entrypoint-initdb.d/init.sql
volumes:
  pgdata:
```

**Schema 草稿**

```sql
-- 事故原始資料
CREATE TABLE accidents (
    id SERIAL PRIMARY KEY,
    accident_date DATE,
    case_type VARCHAR(2),    -- A1 / A2
    death_count INT,
    injury_count INT,
    geom GEOMETRY(Point, 3857)
);
CREATE INDEX ON accidents USING GIST (geom);

-- 篩選後的道路（graph_builder.py 輸出）
CREATE TABLE roads (
    osm_id BIGINT PRIMARY KEY,
    fclass VARCHAR(50),
    name TEXT,
    oneway BOOLEAN,
    length_m FLOAT,
    geom GEOMETRY(LineString, 3857)
);
CREATE INDEX ON roads USING GIST (geom);

-- 風險分數（risk_engine.py 輸出）
CREATE TABLE road_risk (
    osm_id BIGINT REFERENCES roads(osm_id),
    accident_count INT,
    weight_sum FLOAT,
    raw_risk_density FLOAT,
    normalized_risk FLOAT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 圖的節點（graph_builder.py 輸出，供 QGIS 拓撲驗證）
CREATE TABLE graph_nodes (
    node_id BIGINT PRIMARY KEY,
    geom GEOMETRY(Point, 3857)
);

-- 圖的邊（graph_builder.py 切割後，供 QGIS 拓撲驗證）
CREATE TABLE graph_edges (
    edge_id SERIAL PRIMARY KEY,
    source_node BIGINT REFERENCES graph_nodes(node_id),
    target_node BIGINT REFERENCES graph_nodes(node_id),
    osm_id BIGINT,
    fclass VARCHAR(50),
    length_m FLOAT,
    geom GEOMETRY(LineString, 3857)
);
CREATE INDEX ON graph_edges USING GIST (geom);
```

**QGIS 視覺化 view（事故點貼附到道路上）**

```sql
CREATE VIEW accidents_snapped AS
SELECT
    a.id,
    a.accident_date,
    a.case_type,
    a.death_count,
    a.injury_count,
    ST_ClosestPoint(r.geom, a.geom) AS snapped_geom
FROM accidents a
JOIN LATERAL (
    SELECT geom FROM roads
    ORDER BY geom <-> a.geom LIMIT 1
) r ON TRUE;
```

### 待處理

- 決定 Docker Compose 是否放在 repo 根目錄或 `backend/` 目錄下
- 確認 `backend/.env` 中 PostGIS 連線字串的格式
- 新增 `backend/scripts/load_to_postgis.py`：讀取既有 pkl/json → 寫入 PostGIS
- 更新 `app/dependencies.py`：加入 PostGIS 連線池（asyncpg 或 SQLAlchemy async）
- `build_graph.py` 與 `risk_engine.py` 決定是否同時寫 pkl 與 PostGIS，或僅寫 PostGIS
- 確認 QGIS 直接連線 PostGIS 的方式（Layer → Add PostGIS Layers）

---

## 005. 地圖顯示優化（待規劃）

目前 `map.tsx` 已能顯示多條路線（安全路線 + Google 候選路線），但尚未處理：

- 地圖初始縮放與邊界（目前固定在台北，不自動 fit 到路線範圍）
- 路線選擇後的地圖互動（選中路線加粗、其他路線淡化）
- 起點 / 終點標記（目前無 marker）
- 底部路線卡片捲動與路線切換的同步

這些屬於 UX 打磨，等主要功能（PostGIS、Navigation SDK 驗證）完成後再規劃。
