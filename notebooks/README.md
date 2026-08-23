# notebooks/

探索 / 展示 / 除錯用的 Jupyter notebook。**不取代正式 pipeline**（正式邏輯在
`backend/app/services`、`backend/scripts`）；notebook 只 **import 它們、不複製一份**。

對應 backlog `005 JupyterLab`。

## 執行環境

notebook 依賴後端套件 `app`，必須用**後端 venv** 跑（`app` 已 `pip install -e .`）：

```bash
cd backend
pip install -e ".[notebook]"     # 一次性：裝 jupyterlab / matplotlib 等
.venv/bin/jupyter lab --notebook-dir ../notebooks
```

- kernel 選 **Python 3**（即後端 venv 的預設 kernel，帶 `app` 與所有依賴）。
- 「有沒有依賴」看 **kernel**（後端 venv），不看 `.ipynb` 檔放哪個資料夾。
- 中文圖表：本機需有 CJK 字型（例 `Noto Sans CJK TC`）；給別台跑時，軸標建議用英文、
  中文解說寫在 Markdown cell。

## 資料層級（scale）

| 層 | 資料 | 說明 |
|----|------|------|
| L1 | 手工 toy | 不依賴 `backend/data`，教概念 |
| L2 | raw 道路切一小塊 bbox | 驗證概念能接到真實資料 |
| L3 | processed 產物（graph / roads_gdf / risk_scores）| 需先跑完 pipeline（見 `docs/deployment.md`）|

L2 / L3 的輸入檔**不進 git**，由 `docs/deployment.md` 的流程取得（下載腳本 / 重建 pipeline）。

## output 策略

- **教學 / 報告型**（如 `topology_repair_demo`）：**保留 outputs**，讓 GitHub 直接 render 圖表當文件。
- **純探索型**：commit 前清 output（`nbstripout` 或 Kernel → Restart & Clear Output）。
- 另存的大檔（PNG / html）一律 gitignore。

## notebook 清單

### `topology_repair_demo.ipynb`
- **purpose**：視覺化路網「拓撲修復」為什麼需要、怎麼運作（對應 `ARCHITECTURE.md §3.1`）。
- **needs**：Part A 無（toy）；Part B 需 `backend/data/raw/gis_osm_roads_free_1.gpkg`
  （未內建，先跑 `backend/scripts/download_roads_geofabrik.py`）。
- **scale**：L1 toy + L2 bbox。
- **runtime**：< 1 分鐘。
- **output**：保留（含圖）。
- 結果：Part A `2→1 分量`；Part B（台北車站 600m bbox）naive 最大連通比 `15.4% → build_graph 92.9%`。
