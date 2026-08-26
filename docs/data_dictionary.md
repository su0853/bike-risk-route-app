# 資料欄位說明（Data Dictionary）

本文件說明管線中各資料檔的**欄位、型別、意義與座標系**，作為 PostGIS schema（見 backlog 002）
與資料檢視的依據。管線整體流程見 [`ARCHITECTURE.md`](../ARCHITECTURE.md)，欄位篩選邏輯見
`backend/app/services/graph_builder.py`、`risk_engine.py`。

## 座標系慣例

- **內部運算一律 EPSG:3857**（公尺，適合距離/最近點計算）。
- **API I/O 用 EPSG:4326**（WGS84 經緯度）。
- 事故清洗 CSV 保留 4326 的 `lon/lat`；轉成 gpkg 時投影為 3857 的 `Point`。

## 檔案總覽

| 檔案 | 產生者 | 內容 | 座標系 |
|------|--------|------|--------|
| `data/raw/gis_osm_roads_free_1.gpkg` | `download_roads_geofabrik.py`（Geofabrik 下載） | 原始道路 | 3857 |
| `data/processed/roads_gdf.pkl` | `build_graph.py` → `load_and_filter_roads` | 篩選後道路（供 sjoin / 建圖） | 3857 |
| `data/processed/taiwan_graph.pkl` | `build_graph.py` → `build_graph` | 路網圖（NetworkX） | 3857 |
| `data/cleaned/*.csv` | `etl_accidents.py` | 清洗後自行車事故 | 4326（lon/lat 欄） |
| `data/raw/accidents_epsg3857.gpkg` | `prepare_accidents_gpkg.py` | 事故點（供 snap） | 3857 |
| `data/processed/risk_scores.json` | `process_accidents.py` → `build_risk_scores` | 路段風險分數 | —（key 為 osm_id） |

> **對齊鍵**：`osm_id` 是 roads / risk_scores / graph 邊三者的共同鍵。事故對應（snap）後也以
> osm_id 累加到路段。

---

## 1. Geofabrik 原始道路 `gis_osm_roads_free_1.gpkg`

Geofabrik 的 OSM 道路萃取，EPSG:3857，約 815,690 條 LineString。

| 欄位 | 型別 | 意義 |
|------|------|------|
| `osm_id` | str | OSM way id（下游對齊鍵） |
| `code` | int | Geofabrik 內部道路分類代碼（如 5114） |
| `fclass` | str | 功能道路分類（見下） |
| `name` | str | 道路名稱（可為空） |
| `ref` | str | 道路編號（如省道 "4"，可為空） |
| `oneway` | str | 單行：`B`=雙向、`F`=順數位化方向單行、`T`=逆向單行 |
| `maxspeed` | int | 速限（km/h）；`0`=未知 |
| `layer` | int | 垂直層級（橋/隧道堆疊用；`0`=預設） |
| `bridge` | str | 是否橋樑：`T`/`F` |
| `tunnel` | str | 是否隧道：`T`/`F` |
| `geometry` | LineString | 幾何（EPSG:3857） |

**`fclass` 常見值**：`motorway(_link)`、`trunk(_link)`、`primary(_link)`、`secondary(_link)`、
`tertiary(_link)`、`residential`、`service`、`living_street`、`pedestrian`、`footway`、`cycleway`、
`path`、`track`、`track_grade1..5`、`steps`、`unclassified`。

**建圖時排除**（`settings.EXCLUDED_FCLASSES`，不適合自行車）：
`motorway`、`motorway_link`、`trunk`、`trunk_link`、`steps`、`busway`、`bridleway`。

---

## 2. 篩選後道路 `roads_gdf.pkl`

`load_and_filter_roads`（`graph_builder.py`）排除上列 fclass、爆炸 MultiLineString、投影到 3857 後，
只保留下列欄位：

| 欄位 | 型別 | 意義 |
|------|------|------|
| `osm_id` | str | 對齊鍵 |
| `fclass` | str | 功能分類 |
| `name` | str | 名稱 |
| `oneway` | str | 單行（`B`/`F`/`T`） |
| `length_m` | float | 路段長度（公尺，3857 下計算） |
| `length_km` | float | `length_m / 1000`；風險密度的分母 |
| `geometry` | LineString | 幾何（EPSG:3857） |

> **可攜性注意**：`roads_gdf.pkl` 以 pickle + pandas dtype 序列化，**跨 pandas 版本可能無法反序列化**
> （已實測到 `StringDtype` 相容性錯誤）。這是 backlog 002 導入 PostGIS 的動機之一——用資料庫存這些
> 表格資料，取代脆弱的 pkl。

---

## 3. 路網圖 `taiwan_graph.pkl`（NetworkX MultiGraph）

`build_graph`（`graph_builder.py`）以「路口座標分割」修復拓撲後的圖（見 `ARCHITECTURE.md §3.1`）。

**節點（node）**

| 項目 | 值 | 意義 |
|------|-----|------|
| node id | `(rounded_x, rounded_y)` int tuple | 座標以 1m 精度捨入後的整數對；路口共享同一 id |
| 屬性 `x` | float | 原始 EPSG:3857 x 座標 |
| 屬性 `y` | float | 原始 EPSG:3857 y 座標 |

**邊（edge）**

| 屬性 | 型別 | 意義 |
|------|------|------|
| `osm_id` | str | 來源道路 id（一條原始道路被切割後，多段共用同一 osm_id） |
| `fclass` | str | 功能分類 |
| `length_m` | float | 該段長度（公尺） |
| `oneway` | str | 單行（`B`/`F`/`T`） |
| `geometry` | LineString | 該段幾何（EPSG:3857） |

> MultiGraph：兩節點間可有多條平行邊。KDTree 以節點的 `x,y` 建立，供最近節點查詢。

---

## 4. 清洗後事故 `data/cleaned/*.csv`

`etl_accidents.py` 由政府 A1/A2 原始 CSV 清洗（民國年轉換、死傷拆分、自行車篩選）而成。
檔名依年份（107/108/109 = 民國年）。

| 欄位 | 型別 | 意義 |
|------|------|------|
| `case_type` | str | `A1`=24 小時內死亡；`A2`=受傷或 24 小時後死亡 |
| `datetime` | str | 事故時間（已轉西元） |
| `location` | str | 事故地點描述（中文地址） |
| `death_count` | int | 死亡人數 |
| `injury_count` | int | 受傷人數 |
| `lon` | float | 經度（WGS84 / 4326） |
| `lat` | float | 緯度（WGS84 / 4326） |
| `hour` | int | 小時（0–23） |
| `time_period` | str | 時段（深夜/上午/下午…，ETL 衍生欄） |
| `risk_score` | int | ETL 階段的粗略分數（**下游不使用**；見下說明） |

> 下游 `prepare_accidents_gpkg.py` 只取 `case_type / datetime / location / death_count / injury_count`
> ＋由 `lon/lat` 生成的點幾何；`hour / time_period / risk_score` 為 ETL 副產物、**不進 gpkg、不影響風險計算**。
> 實際風險權重由 `risk_engine.compute_accident_weights` 依死傷數與 A1/A2 重新計算。

---

## 5. 事故點 `accidents_epsg3857.gpkg`

`prepare_accidents_gpkg.py` 合併各年 cleaned CSV、由 `lon/lat` 建點並投影到 3857。約 60,953 筆。

| 欄位 | 型別 | 意義 |
|------|------|------|
| `case_type` | str | `A1` / `A2` |
| `accident_datetime` | datetime | 事故時間 |
| `death_count` | int | 死亡人數 |
| `injury_count` | int | 受傷人數 |
| `location` | str | 地點描述 |
| `geometry` | Point | 事故點（EPSG:3857） |

---

## 6. 風險分數 `risk_scores.json`

`build_risk_scores`（`risk_engine.py`）的輸出。結構為 `{osm_id(str): normalized_risk(float)}`，
約 788,320 筆（涵蓋所有道路；無事故者為 `0.0`）。

| 項目 | 值 | 意義 |
|------|-----|------|
| key | str（osm_id） | 對齊道路 |
| value | float `[0, 1]` | **normalized** 風險（P99 截斷後縮放）；`0`=無事故 |

計算：事故權重（依死傷 × A1/A2 + 時間衰減）→ 依 osm_id 累加 → 除以 `length_km` 得 **raw density** →
P99 截斷正規化到 `[0,1]`。公式細節見 [`docs/risk_score_methodology.md`](risk_score_methodology.md)。

> **只存 normalized**：raw density **未持久化**。需要 raw（如風險分佈探索、校準）時得重算
> （`aggregate_edge_risk`）。backlog 002 的 `road_risk` 表規劃**同時存 raw + normalized**，
> 即為補上這點。
