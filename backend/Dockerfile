# syntax=docker/dockerfile:1
FROM python:3.12-slim

# GIS 依賴（geopandas/shapely/pyproj/pyogrio/scipy）皆為 manylinux wheel，
# 自帶 GDAL/GEOS/PROJ，無需 apt 安裝系統 GDAL 或 build tools → 保持 slim。

WORKDIR /app

# 先裝依賴 + app 套件（editable）。data/ 由 .dockerignore 排除、runtime 掛載，不進 image。
COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
RUN pip install --no-cache-dir -e .

EXPOSE 8000

# 預設啟動 API；一次性資料重建用 override，例如：
#   docker compose run --rm backend python -m scripts.build_graph
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
