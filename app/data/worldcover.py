"""ESA WorldCover tile path resolver — local GeoTIFF files.

Generates LOCAL file paths (not S3 URLs) for the satellite onboard system.
Tiles are stored in the configured worldcover_dir as:
    ESA_WorldCover_10m_2021_v200_{grid_code}_Map.tif
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

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


def get_tile_path_by_code(grid_code: str) -> Path:
    """Return local file path for a known WorldCover tile code."""
    settings = get_settings()
    return settings.worldcover_dir / f"ESA_WorldCover_10m_2021_v200_{grid_code}_Map.tif"


def load_worldcover_manifest() -> dict[str, Any]:
    """Load the configured WorldCover deployment manifest if present."""
    settings = get_settings()
    if not settings.worldcover_manifest_path.exists():
        return {}
    with settings.worldcover_manifest_path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def check_worldcover_readiness() -> dict[str, Any]:
    """Check local WorldCover readiness for the limited deployed tile set."""
    settings = get_settings()
    details: dict[str, Any] = {
        "worldcover_dir": str(settings.worldcover_dir),
        "manifest": str(settings.worldcover_manifest_path),
        "required_tiles": [],
        "missing_tiles": [],
    }
    try:
        manifest = load_worldcover_manifest()
    except Exception as exc:
        details["error"] = "manifest_unreadable"
        details["exception"] = type(exc).__name__
        return {"ready": False, "details": details}

    required_tiles = list(manifest.get("tiles", []))
    details["required_tiles"] = required_tiles

    if not settings.worldcover_dir.is_dir():
        details["error"] = "worldcover_dir_missing"
        return {"ready": False, "details": details}

    if not required_tiles:
        details["error"] = "manifest_missing_or_empty"
        return {"ready": False, "details": details}

    missing = [code for code in required_tiles if not get_tile_path_by_code(code).exists()]
    details["missing_tiles"] = missing
    if missing:
        details["error"] = "required_tiles_missing"
        return {"ready": False, "details": details}

    sample_tile = get_tile_path_by_code(required_tiles[0])
    try:
        import rasterio

        with rasterio.open(sample_tile):
            pass
    except Exception as exc:
        details["error"] = "sample_tile_unreadable"
        details["exception"] = type(exc).__name__
        return {"ready": False, "details": details}

    details["sample_tile"] = str(sample_tile)
    return {"ready": True, "details": details}
