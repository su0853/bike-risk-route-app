# Decision Log

本文件記錄已完成、已採納或已封存的設計決策。  
目的不是取代 backlog，而是保留「當時為什麼這樣做」的脈絡。

---

## 001. Geocoder 改為後端 Proxy，並支援多候選選擇

### 背景

早期前端直接呼叫 Nominatim。iOS 測試時未明顯出錯，但 Android 曾發生 HTTP 403。

推測原因是 Android / React Native 直接呼叫 Nominatim 時，缺少穩定可識別的 `User-Agent` 或 `Referer`，觸發 Nominatim 公開服務限制。

### 決策

前端不再直接呼叫 Nominatim，改為呼叫後端：

```text
frontend/services/geocoder.ts
  -> GET /api/geocode?q=...
  -> backend/app/routers/geocode.py
  -> Nominatim Search API
```

後端 proxy 統一加上：

```text
User-Agent
Accept-Language
```

同時因為 Nominatim 對同一查詢可能回傳多筆候選結果，前端改為顯示候選清單，由使用者選擇正確地點。

### 已完成項目

- `frontend/services/geocoder.ts` 新增 `geocodeAddressCandidates()` 回傳候選陣列。
- 保留 `geocodeAddress()` 取第一筆，作為相容舊流程的 helper。
- `frontend/components/SearchForm.tsx` 實作多候選選擇 UI。
- 起點與終點各自管理輸入、候選清單、已選定狀態。
- 兩端都選定後才啟用「搜尋路線」。
- `frontend/app/index.tsx` 接收已選定的 `GeocoderResult`，直接組成 `NavigateRequest`。
- `backend/app/routers/geocode.py` 回傳最多 5 筆候選。

### 後續

目前仍使用 Nominatim proxy。若搜尋品質不足，再評估 Google Geocoding / Places API。因前端只依賴 `/api/geocode`，後端供應商可替換而不需要大改前端。

---

## 002. 起點支援「目前位置」

### 背景

導航與路線規劃常見使用情境是從使用者目前位置出發，因此搜尋頁需要支援「使用目前位置作為起點」。

### 決策

在 `SearchForm` 的起點欄位旁加入「定位」按鈕。

流程：

```text
requestForegroundPermissionsAsync()
  -> getCurrentPositionAsync()
  -> 建立 GeocoderResult
  -> selected = 目前位置
```

目前不做 reverse geocoding，顯示文字固定為「目前位置」，直接使用 GPS 座標送出。

### 已完成項目

- `frontend/components/SearchForm.tsx` 使用 `expo-location`。
- 起點欄位旁新增「定位」按鈕。
- 權限拒絕時顯示提示。
- 定位失敗時顯示提示。
- 定位成功後起點欄位設為已選定狀態。

---

## 003. 風險圖層匯出至 QGIS

### 背景

風險模型包含多個 heuristic 假設：

- A1/A2/death/injury 權重。
- 時間衰減半衰期。
- 以 `length_km` 作為分母的風險密度。
- P99 截斷正規化。

這些假設不能只靠公式判斷，需要輸出到 QGIS 視覺化檢查。

### 決策

新增匯出腳本，將道路風險中間值輸出為 GeoPackage。

### 已完成項目

- 新增 `backend/scripts/export_risk_layer.py`。
- 輸出 `backend/data/processed/risk_scores.gpkg`。
- 包含三個圖層：
  - `risk_p95`
  - `risk_p99`
  - `risk_p995`
- 輸出欄位：

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
is_clipped
```

### 已知結果

一次執行紀錄：

- 路段數：766,454
- 有事故路段：35,347，約 4.6%
- snap rate：約 94.79%
- GeoPackage 輸出大小：約 734 MB

### 後續

匯出工具已完成，但模型校準仍屬 open issue。後續觀察與調整記錄在 [`discussion_backlog.md`](./discussion_backlog.md) 的「風險模型校準」。
