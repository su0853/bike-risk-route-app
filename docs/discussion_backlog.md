# Discussion Backlog

本文件用來記錄尚未完全定案的問題、方法論討論、產品假設與後續可交給實作工具處理的任務。

這裡不追求立刻寫成完整規格，而是保留「為什麼這件事值得處理」與「目前有哪些選項」。

---

## 001. Geocoder 多候選地點選擇問題

### 背景

前端地址查詢已改為呼叫後端 `/api/geocode`，由後端代理外部 geocoder。

先前 Android 直接呼叫 Nominatim 時曾發生 HTTP 403；目前透過後端 proxy 並加上 `User-Agent` 後，這個阻擋問題已基本解決。

### 目前狀態

目前流程：

```text
frontend/services/geocoder.ts
  -> GET /api/geocode?q=...
  -> backend/app/routers/geocode.py
  -> Nominatim Search API
```

後端目前可回傳多筆候選結果，但前端 `geocodeAddress()` 只取第一筆。

### 問題

當使用者輸入的地點名稱有多個可能結果時，系統直接取第一筆可能會選錯地點。

常見例子：

- 中山站
- 市政府
- 台北車站
- 民生路
- 中正路

如果起點或終點被解析錯，後續路線規劃仍可能正常完成，但結果其實不是使用者想去的地方。

### 方案 A：保留 Nominatim，提供多候選選擇

當 geocoder 回傳多筆結果時，前端顯示候選清單，讓使用者選擇正確位置。

優點：

- 不需要更換供應商。
- 目前後端介面可以沿用。
- 使用者可以主動確認地點。

缺點：

- 前端 UI 需要多一步。
- Nominatim 搜尋品質仍可能不如商業服務。
- 仍需遵守 Nominatim rate limit、attribution 與快取政策。

### 方案 B：改用 Google Geocoding / Places API

後端 `/api/geocode` 改為呼叫 Google Geocoding 或 Places API，前端介面維持不變。

優點：

- 對地標、商家、日常地址搜尋可能較符合使用者習慣。
- 可搭配 autocomplete 與 place details。
- 避免依賴 Nominatim 公開服務限制。

缺點：

- 需要 Google API key、計費設定與配額控管。
- 實際效果尚未測試，不能只憑直覺判斷。
- Places API 的資料流程會比單純 geocoding 複雜。

### 初步判斷

短期可先做多候選選擇 UI，因為目前 `/api/geocode` 已能回傳多筆結果。

中期可整理一組常見查詢案例，比較 Nominatim 與 Google 的命中品質、座標準確度、回傳速度與成本。

### 待處理

- 將 `geocodeAddress()` 改成可回傳候選陣列。
- 新增起點與終點候選選擇 UI。
- 使用 `display_name` 顯示候選地點。
- 使用者選定後再組成 `NavigateRequest`。
- 保留 `/api/geocode` 介面，避免前端綁死特定 geocoder 供應商。

---

## 002. 風險分數正規化與 QGIS 視覺化

### 背景

目前風險分數流程：

```text
事故嚴重程度與時間衰減
  -> 對應到 osm_id
  -> 依路段累加事故權重
  -> 除以 length_km 得到 raw risk density
  -> 使用 P99 截斷並正規化到 [0, 1]
```

目前正規化方式：

```python
clip_value = percentile(非零路段風險密度, 99.0)
normalized_risk = min(raw_risk / clip_value, 1.0)
```

### 方法理解

P99 截斷不是刪除資料，也不是表示 P99 以上資料沒有參考價值。

它的作用是封頂：P99 以上的路段仍保留為最高風險 `1.0`，但不再讓極端值繼續拉大整體比例尺。

若直接用最大值作為分母，少數極端高風險路段可能讓大多數路段的分數被壓得太低，導致中高風險區段難以區分。

### 目前假設

這套方法目前屬於 heuristic，仍包含多個尚未實證校準的假設：

- A1 / A2 / death / injury 權重是否合理。
- 時間衰減半衰期是否合理。
- 使用 `length_km` 作為分母是否會過度放大短路段。
- P99 是否是合適的截斷點。
- `normalized_risk` 線性放入路徑成本是否合理。
- 使用者安全偏好 `lambda_coef` 是否足以代表真實偏好。

### 視覺化方向

建議輸出一份 QGIS 可讀取的 GeoPackage，用於檢查風險權重分布是否合理。

建議欄位：

```text
osm_id
name
fclass
length_m
length_km
accident_count
weight_sum
raw_risk_density
normalized_risk
is_clipped_p99
```

QGIS 圖層檢查重點：

- `normalized_risk` 是否集中在合理事故熱區。
- `is_clipped_p99` 是否過度集中或數量過多。
- 是否有很短路段因除以長度而異常偏高。
- 無事故路段是否合理呈現為 0。
- 不同 P95 / P99 / P99.5 截斷是否造成明顯差異。

### 待處理

- 新增匯出風險圖層腳本，例如 `backend/scripts/export_risk_layer.py`。
- 輸出 `backend/data/processed/risk_scores.gpkg` 或類似檔案。
- 同時保留 raw risk density 與 normalized risk。
- 比較 P95、P99、P99.5 的視覺結果。
- 用幾組實際路線測試不同 `lambda_coef` 下是否合理避開高風險路段。

---

## 003. 導航功能：Google Navigation for React Native

### 背景

目前專案已能完成：

```text
輸入起終點
  -> geocoder 取得座標
  -> 後端計算安全路線與 Google 候選路線
  -> 前端地圖顯示多條路線
```

原始產品目標是「導航」，目前已經完成路線規劃與地圖呈現，下一步可以評估加入 turn-by-turn navigation。

### 候選方案

使用 Google Navigation for React Native：

```text
@googlemaps/react-native-navigation-sdk
```

Google 官方文件顯示此套件可在 React Native app 中整合 Google Navigation component，目標平台包含 Android 與 iOS。

### 目前專案相容性初步觀察

目前前端使用：

```text
React Native 0.81.5
Expo 54
newArchEnabled: true
```

Google Navigation for React Native 目前要求 React Native 0.79+ 且啟用 new architecture，因此專案版本方向上可評估。

但仍需確認 Expo managed workflow 是否能順利整合，或是否需要 prebuild / dev client / native project 設定。

### 前置需求

要做導航功能，至少需要：

- 取得使用者當前位置。
- 請求定位權限。
- 持續追蹤位置更新。
- 將目前位置作為導航起點，或讓使用者選擇「我的位置」作為起點。
- 將後端選定路線或目的地交給 Navigation SDK。
- 處理導航開始、停止、抵達、偏離路線等狀態。

目前專案已有 `expo-location` 依賴與權限文字設定，但仍需確認前端是否已實作實際定位流程。

### 需要釐清的問題

- Navigation SDK 是否能使用後端已算好的自訂安全路線，還是只能依目的地由 Google 自行規劃導航路線。
- 如果 Google Navigation 重新規劃路線，是否會覆蓋本專案的安全路線邏輯。
- 是否能把安全路線拆成 waypoint 交給 Navigation SDK，使導航盡量沿著安全路線走。
- 使用 waypoint 導航時是否會增加 API 成本或造成體驗問題。
- iOS / Android 設定是否都能在目前 Expo 專案中完成。
- 是否需要 eject / prebuild。
- API key 需要啟用哪些服務與限制。
- Navigation SDK 的 Beta 狀態是否能接受。

### 風險

- Google Navigation React Native 套件仍是 Beta，1.0 前可能有 breaking changes。
- Google 官方說這類跨平台 Navigation plugin 不是 Google Maps Platform Core Service，不適用標準 SLA / support policy。
- Navigation SDK 可能與現有 `react-native-maps` / Google Maps SDK 依賴產生版本衝突。
- 導航功能會牽涉定位權限、電量、背景狀態、偏航重算與平台差異，複雜度高於單純畫路線。

### 建議執行順序

短期先完成最小可行驗證：

1. 實作「取得目前位置」功能。
2. 在搜尋頁支援「使用目前位置作為起點」。
3. 建立一個獨立 navigation prototype screen，不直接替換現有 `map.tsx`。
4. 測試 Google Navigation SDK 是否能在目前 Expo / React Native 版本中啟動。
5. 測試能否用目的地啟動導航。
6. 再研究是否能透過 waypoints 貼近本專案的安全路線。

### 初步判斷

可以把 Google Navigation for React Native 作為下一個主要實作方向。

但它應先被視為 prototype / spike，而不是直接重構現有地圖頁。等確認 SDK 能正常啟動、定位權限流程可用、且導航路線能與本專案安全路線策略銜接後，再決定是否正式整合。

### 待處理

- 檢查目前 `expo-location` 是否已能取得當前位置。
- 新增「使用目前位置」起點功能。
- 建立 Navigation SDK 技術驗證分支或 prototype 頁面。
- 確認 Android / iOS API key 與 Navigation SDK 啟用狀態。
- 確認 Expo prebuild / dev client 需求。
- 測試目的地導航。
- 測試 waypoint 導航能否貼近安全路線。
