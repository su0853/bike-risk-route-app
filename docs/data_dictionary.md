# 資料欄位說明（Data Dictionary）

本文件說明管線中各資料檔的**欄位、型別、意義與座標系**，作為 PostGIS schema
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
| `data/raw/dem_taiwan.tif` | `download_dem.py`（OpenTopography） | DEM 高程柵格（坡度用，選用） | 4326 |

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
> （已實測到 `StringDtype` 相容性錯誤）。這是導入 PostGIS 的動機之一——用資料庫存這些
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
| 屬性 `z` | float | 高程（公尺，DEM 取樣）。**選用**：只有跑過 `download_dem` + rebuild 才有；否則不存在。 |

**邊（edge）**

| 屬性 | 型別 | 意義 |
|------|------|------|
| `osm_id` | str | 來源道路 id（一條原始道路被切割後，多段共用同一 osm_id） |
| `fclass` | str | 功能分類 |
| `length_m` | float | 該段長度（公尺） |
| `oneway` | str | 單行（`B`/`F`/`T`） |
| `grade_abs` | float｜None | 無方向坡度 `|Δz|/length_m`（供 QGIS/統計）。**選用**：無 DEM 時為 None。路由成本用的是**方向**坡度，於查詢時由兩端 `z` 現算，不存邊上。 |
| `geometry` | LineString | 該段幾何（EPSG:3857） |

> MultiGraph：兩節點間可有多條平行邊。KDTree 以節點的 `x,y` 建立，供最近節點查詢。

**高程 / 坡度資料來源（選用）**：`z` 由 `scripts.download_dem` 下載的 DEM GeoTIFF（預設 OpenTopography **AW3D30 30m**，EPSG:4326）取樣而來，`elevation.attach_elevation` 於 rebuild 時把節點座標轉 4326 後對 DEM band 取值。缺 DEM 時整步略過、路由退回無坡度（`LAMBDA_SLOPE` 不生效）。要換更準的 DEM（如國土測繪 20m）只需替換 `DEM_PATH` 指向的檔案。

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
> （`aggregate_edge_risk`）。PostGIS 的 `road_risk` 表**同時存 raw + normalized**，
> 補上這點。

---

## 7. DEM 高程柵格 `data/raw/dem_taiwan.tif`（選用，坡度權重用）

由 `scripts/download_dem.py` 從 **OpenTopography** 下載的 **ALOS AW3D30 30m** DEM（GeoTIFF）。
這是**柵格（raster）**而非表格，沒有「欄位」，其「規格」= 柵格屬性。缺此檔時管線略過高程、
路由退回無坡度（見 [`ARCHITECTURE`](../ARCHITECTURE.md) 與坡度成本設定 `LAMBDA_SLOPE`）。

**柵格規格**（量測值 2026-09；bbox 為 config `DEM_BBOX_*`，台灣本島，不含金馬）：

| 項目 | 值 | 說明 |
|------|-----|------|
| 格式 | GeoTIFF（單一檔，57 MB） | |
| CRS | **EPSG:4326**（經緯度） | 與內部 3857 不同 → 取樣時節點座標先轉 4326（見 §3） |
| 波段 | 1 | 高程值 |
| 資料型別 | `int16` | 整數公尺，不含小數 |
| 尺寸 | 7740 × 12600（≈ 97.5M px） | |
| 像素大小 | 0.000278°（≈ **30.9 m**） | AW3D30 名目 30m |
| 範圍 bounds | W119.90 S21.85 E122.05 N25.35 | 一個矩形，含台灣周邊大片海域 |
| 值域 | **−88 ~ 3937 m** | 高值近玉山（3952m）；負值為海岸雜訊 |
| nodata | None（未設） | 海面以 `0` 表示，非 nodata |

**特性與注意事項**：
- **海面 = 0，而非 nodata**：因為 nodata 未設，矩形 bbox 內的大片海域值都是 `0`。所以整張
  raster 的中位數是 0（矩形大半是海），但路網節點取樣到的 `z` 中位數是 36 m（道路都在陸地）。
  兩者差異來自「含不含海」，並非資料錯誤。
- **負值是海岸雜訊**：有 0.089% 的像素 < 0（低到 −88m），台灣無陸地低於海平面，屬 AW3D30 在
  海岸/水體的少數誤差。路網節點只掃到最低約 −65m（道路不會落在最糟的像素上），佔比極小、不影響路由。
- **30m 解析度的含意**：對很短的路段（graph edge 常被拓撲修復切得很短），30m DEM 取兩端高差算坡度
  容易放大雜訊（短距離的小高差 → 大百分比）。長度加權平均坡度因而偏高（約 4.5%），部分源自此雜訊；
  屬坡度成本的後續校準項目（沿線多點取樣、短邊長度門檻）。

**如何被使用**：`app/services/elevation.py::attach_elevation` 讀此檔，為每個 graph 節點取 `z`、
每條邊算 `grade_abs`（見 §3 的節點/邊屬性）。**換更準的 DEM**（如國土測繪 20m）只要把檔案放到
同一路徑（`DEM_PATH`），其餘程式不動。
