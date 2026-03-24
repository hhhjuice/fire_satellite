"""Land cover analysis using LOCAL GeoTIFF files (no network).

Reads ESA WorldCover 10m tiles stored locally on the satellite.
No GDAL_HTTP env vars — pure local file I/O via rasterio.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import rasterio
from rasterio.errors import RasterioIOError
from rasterio.windows import Window

from app.api.schemas import LandCoverResult
from app.config import get_settings
from app.data.worldcover import get_tile_path

logger = logging.getLogger(__name__)


def _read_pixel(file_path: str, lat: float, lon: float) -> Optional[int]:
    """Read a single pixel value from a local GeoTIFF file."""
    try:
        with rasterio.open(file_path) as ds:
            row, col = ds.index(lon, lat)
            window = Window(col, row, 1, 1)
            data = ds.read(1, window=window)
            return int(data[0, 0])
    except (RasterioIOError, IndexError, Exception) as exc:
        logger.warning(
            "Failed to read land cover at (%.4f, %.4f) from %s: %s",
            lat, lon, file_path, exc,
        )
        return None


async def get_landcover(lat: float, lon: float) -> Optional[LandCoverResult]:
    """Get land cover classification for coordinates from local GeoTIFF."""
    settings = get_settings()
    tile_path = get_tile_path(lat, lon)

    if not tile_path.exists():
        logger.warning("WorldCover tile not found: %s", tile_path)
        return None

    class_code = await asyncio.to_thread(_read_pixel, str(tile_path), lat, lon)

    if class_code is None:
        return None

    likelihood_ratio = settings.landcover_lr.get(class_code, 1.0)
    class_name = settings.landcover_names.get(class_code, f"未知地物({class_code})")

    return LandCoverResult(
        class_code=class_code,
        class_name=class_name,
        likelihood_ratio=likelihood_ratio,
        description=f"ESA WorldCover 2021: {class_name} (编码{class_code}), 火灾似然比={likelihood_ratio}",
    )
