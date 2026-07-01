from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    GOOGLE_ROUTES_API_KEY: str = ""

    # 資料路徑
    ROADS_GPKG_PATH: str = "data/raw/gis_osm_roads_free_1.gpkg"
    ACCIDENTS_GPKG_PATH: str = "data/raw/accidents_epsg3857.gpkg"
    GRAPH_FILE_PATH: str = "data/processed/taiwan_graph.pkl"
    ROADS_GDF_PATH: str = "data/processed/roads_gdf.pkl"
    RISK_SCORES_PATH: str = "data/processed/risk_scores.json"

    # 路由圖下載範圍 (osmnx bbox: north, south, east, west)
    # 預設台北市/台北縣範圍；可擴展至全台
    ROUTING_BBOX_NORTH: float = 25.22
    ROUTING_BBOX_SOUTH: float = 24.95
    ROUTING_BBOX_EAST: float = 121.68
    ROUTING_BBOX_WEST: float = 121.42

    # 道路篩選 — 排除不適合自行車的道路類型
    EXCLUDED_FCLASSES: list[str] = [
        "motorway", "motorway_link", "trunk", "trunk_link",
        "steps", "busway", "bridleway",
    ]

    # 風險權重（依事故類型分別設定，待 VSL 成本研究後更新）
    # A1 = 24小時內死亡；A2 = 受傷 或 24小時後死亡（仍可能含死亡）
    RISK_A1_DEATH_WEIGHT: float = 3.0    # A1 死亡（當場或 24h 內）
    RISK_A1_INJURY_WEIGHT: float = 1.5   # A1 事故中的受傷者
    RISK_A2_DEATH_WEIGHT: float = 2.0    # A2 死亡（24h 後不治）
    RISK_A2_INJURY_WEIGHT: float = 1.0   # A2 受傷基準
    RISK_DECAY_HALF_LIFE_YEARS: float = 3.0
    RISK_CLIP_PERCENTILE: float = 99.0

    # Snap 公差 (QGIS 研究驗證: 20m → 99.51% 成功率)
    SNAP_TOLERANCE_M: float = 20.0

    # 路線參數
    LAMBDA_DEFAULT: float = 0.5
    MAX_GOOGLE_ALTERNATIVES: int = 2

    # 坐標系統
    CRS_METRIC: int = 3857
    CRS_WGS84: int = 4326


settings = Settings()
