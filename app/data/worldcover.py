"""ESA WorldCover tile path resolver — local GeoTIFF files.

Generates LOCAL file paths (not S3 URLs) for the satellite onboard system.
Tiles are stored in the configured worldcover_dir as:
    ESA_WorldCover_10m_2021_v200_{grid_code}_Map.tif
"""
from __future__ import annotations

import math
from pathlib import Path

from app.config import get_settings


def get_tile_grid_code(lat: float, lon: float) -> str:
    """Compute the 3-degree grid code for ESA WorldCover tiles."""
    tile_lat = math.floor(lat / 3) * 3
    tile_lon = math.floor(lon / 3) * 3

    lat_prefix = "N" if tile_lat >= 0 else "S"
    lon_prefix = "E" if tile_lon >= 0 else "W"

    return f"{lat_prefix}{abs(tile_lat):02d}{lon_prefix}{abs(tile_lon):03d}"


def get_tile_path(lat: float, lon: float) -> Path:
    """Return local file path for the WorldCover tile covering (lat, lon)."""
    settings = get_settings()
    grid_code = get_tile_grid_code(lat, lon)
    return settings.worldcover_dir / f"ESA_WorldCover_10m_2021_v200_{grid_code}_Map.tif"
