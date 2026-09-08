"""
高程附掛（§006-1）：從 DEM GeoTIFF 為 graph 節點取樣高程 z，並算每條邊的坡度。

- 節點座標為 EPSG:3857（build_graph 產生的 x/y）；DEM（OpenTopography AW3D30）為 EPSG:4326。
  → 先把節點座標轉 4326，再對整張 band 做向量化索引取樣（快，避免逐點 sample）。
- 節點屬性：z（公尺，float；nodata/界外則不設）。
- 邊屬性：grade_abs = |z_v - z_u| / length_m（無方向,供 QGIS/統計；路由成本的方向坡度於查詢時現算）。

DEM 缺檔或未裝 rasterio 時：呼叫端應略過此步；路由會退回無坡度（LAMBDA_SLOPE 不生效）。
"""
import logging
from pathlib import Path

import networkx as nx
import numpy as np
from pyproj import Transformer

logger = logging.getLogger(__name__)

_to_wgs84 = Transformer.from_crs(3857, 4326, always_xy=True)


def dem_available(dem_path: str) -> bool:
    return Path(dem_path).exists()


def attach_elevation(G: nx.MultiGraph, dem_path: str) -> dict:
    """就地為 G 節點加 z、為邊加 grade_abs。回傳統計 dict。"""
    try:
        import rasterio
    except ImportError:
        logger.warning("未裝 rasterio（pip install -e '.[dem]'）→ 略過高程附掛")
        return {"attached": False, "reason": "rasterio-missing"}

    if not dem_available(dem_path):
        logger.warning("DEM 不存在：%s → 略過高程附掛（路由退回無坡度）", dem_path)
        return {"attached": False, "reason": "dem-missing"}

    node_ids = list(G.nodes())
    xs = np.fromiter((G.nodes[n]["x"] for n in node_ids), dtype=float, count=len(node_ids))
    ys = np.fromiter((G.nodes[n]["y"] for n in node_ids), dtype=float, count=len(node_ids))
    lons, lats = _to_wgs84.transform(xs, ys)

    with rasterio.open(dem_path) as ds:
        band = ds.read(1)
        nodata = ds.nodata
        H, W = band.shape
        inv = ~ds.transform  # (col, row) = inv * (lon, lat)
        cols = inv.a * lons + inv.b * lats + inv.c
        rows = inv.d * lons + inv.e * lats + inv.f
        cols = np.floor(cols).astype(np.int64)
        rows = np.floor(rows).astype(np.int64)

    in_bounds = (rows >= 0) & (rows < H) & (cols >= 0) & (cols < W)
    z = np.full(len(node_ids), np.nan, dtype=float)
    r_ok, c_ok = rows[in_bounds], cols[in_bounds]
    vals = band[r_ok, c_ok].astype(float)
    if nodata is not None:
        vals[vals == nodata] = np.nan
    # AW3D30 海面常為 0；不視為 nodata（0m 高程合理），保留
    z_in = z[in_bounds]
    z_in[:] = vals
    z[in_bounds] = z_in

    n_valid = int(np.isfinite(z).sum())
    for n, zi in zip(node_ids, z):
        if np.isfinite(zi):
            G.nodes[n]["z"] = float(zi)

    # 邊坡度（無方向）
    n_edges_graded = 0
    for u, v, k, d in G.edges(data=True, keys=True):
        zu = G.nodes[u].get("z")
        zv = G.nodes[v].get("z")
        length = float(d.get("length_m", 0.0))
        if zu is not None and zv is not None and length > 0:
            d["grade_abs"] = abs(zv - zu) / length
            n_edges_graded += 1
        else:
            d["grade_abs"] = None

    finite_z = z[np.isfinite(z)]
    stats = {
        "attached": True,
        "nodes_total": len(node_ids),
        "nodes_with_z": n_valid,
        "edges_graded": n_edges_graded,
        "z_min": float(finite_z.min()) if finite_z.size else None,
        "z_max": float(finite_z.max()) if finite_z.size else None,
        "z_mean": float(finite_z.mean()) if finite_z.size else None,
    }
    logger.info(
        "高程附掛：%d/%d 節點有 z（z %.0f~%.0fm，平均 %.0f），%d 邊有坡度",
        stats["nodes_with_z"], stats["nodes_total"],
        stats["z_min"] or 0, stats["z_max"] or 0, stats["z_mean"] or 0,
        stats["edges_graded"],
    )
    return stats
