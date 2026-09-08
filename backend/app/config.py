from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    GOOGLE_ROUTES_API_KEY: str = ""

    # OpenTopography（下載 AW3D30 DEM 用；免費申請 https://opentopography.org）
    OPENTOPOGRAPHY_API_KEY: str = ""

    # PostGIS（002 DB-centric）：runtime 一律從 DB 載 roads_gdf / risk_scores（graph 仍讀 pkl cache）。
    # 連線用元件組出；密碼單一值放 backend/.env 的 POSTGRES_PASSWORD。
    # host 預設 localhost（本機 venv）；Docker 由 compose 設 POSTGRES_HOST=postgis。
    # 若設了 DATABASE_URL（完整字串）則直接用它、覆蓋以下元件。
    POSTGRES_USER: str = "bikerisk"
    POSTGRES_PASSWORD: str = "bikerisk_dev"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "bikerisk"
    DATABASE_URL: str = ""

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        # user/password URL-encode，避免密碼含 @ : / ? # 等保留字元破壞 DSN
        user = quote_plus(self.POSTGRES_USER)
        pw = quote_plus(self.POSTGRES_PASSWORD)
        return (
            f"postgresql+psycopg://{user}:{pw}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # 資料路徑
    ROADS_GPKG_PATH: str = "data/raw/gis_osm_roads_free_1.gpkg"
    ACCIDENTS_GPKG_PATH: str = "data/raw/accidents_epsg3857.gpkg"
    GRAPH_FILE_PATH: str = "data/processed/taiwan_graph.pkl"
    ROADS_GDF_PATH: str = "data/processed/roads_gdf.pkl"
    RISK_SCORES_PATH: str = "data/processed/risk_scores.json"

    # DEM（AW3D30 30m GeoTIFF；坡度權重用）。缺檔時 pipeline 略過高程、路由退回無坡度。
    DEM_PATH: str = "data/raw/dem_taiwan.tif"
    # download_dem 預設下載範圍（台灣本島 + 邊界緩衝；不含金馬）
    DEM_BBOX_SOUTH: float = 21.85
    DEM_BBOX_NORTH: float = 25.35
    DEM_BBOX_WEST: float = 119.90
    DEM_BBOX_EAST: float = 122.05

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
    MAX_GOOGLE_ALTERNATIVES: int = 2   # Google 路線總數上限（含主路線）；2 → google_0/1

    # 坡度成本（§006-1）。成本 = length × (1 + λ_risk×risk + λ_slope×penalty(grade))。
    # penalty(grade) = max(0, 上坡比例) + SLOPE_DOWNHILL_FACTOR × max(0, 下坡比例)。
    # grade 為方向坡度 (Δz/length)；10% 上坡 → penalty≈0.1。λ_slope=0 等同關閉坡度。
    LAMBDA_SLOPE: float = 3.0
    SLOPE_DOWNHILL_FACTOR: float = 0.0   # 下坡懲罰係數（0=忽略下坡；>0 可懲罰陡下坡煞車風險）

    # 坐標系統
    CRS_METRIC: int = 3857
    CRS_WGS84: int = 4326


settings = Settings()
