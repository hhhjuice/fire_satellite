"""Coordinate correction via spiral search on local land cover data."""
import asyncio
import logging
from typing import Optional

from app.api.schemas import CoordinateCorrection
from app.config import get_settings
from app.services.landcover import get_landcover
from app.utils.geo import haversine, meters_to_degrees_lat, meters_to_degrees_lon

logger = logging.getLogger(__name__)

# Land cover codes that are combustible (worth correcting toward)
COMBUSTIBLE_CODES = {10, 20, 30, 40, 90, 95, 100}

# Land cover codes that strongly indicate false position
NON_COMBUSTIBLE_CODES = {50, 60, 70, 80}


def _generate_spiral_offsets(radius_m: float, step_m: float, lat: float) -> list[tuple[float, float]]:
    """Generate (dlat, dlon) offsets in a spiral pattern from center."""
    offsets: list[tuple[float, float]] = []
    dlat_step = meters_to_degrees_lat(step_m)
    dlon_step = meters_to_degrees_lon(step_m, lat)
    max_steps = int(radius_m / step_m)

    for ring in range(1, max_steps + 1):
        for i in range(-ring, ring + 1):
            offsets.append((ring * dlat_step, i * dlon_step))
        for i in range(ring - 1, -ring - 1, -1):
            offsets.append((i * dlat_step, ring * dlon_step))
        for i in range(ring - 1, -ring - 1, -1):
            offsets.append((-ring * dlat_step, i * dlon_step))
        for i in range(-ring + 1, ring):
            offsets.append((i * dlat_step, -ring * dlon_step))

    return offsets


async def correct_coordinates(
    lat: float,
    lon: float,
    current_landcover_code: Optional[int] = None,
) -> CoordinateCorrection:
    """Attempt to correct fire point coordinates by searching nearby.

    If the current position has non-combustible land cover, searches in a
    spiral pattern for the nearest combustible surface.
    """
    settings = get_settings()

    if current_landcover_code is None or current_landcover_code in COMBUSTIBLE_CODES:
        return CoordinateCorrection(
            original_lat=lat,
            original_lon=lon,
            corrected_lat=lat,
            corrected_lon=lon,
            offset_m=0.0,
            correction_applied=False,
            reason="当前地物类型适合火灾发生，无需修正坐标" if current_landcover_code in COMBUSTIBLE_CODES else "地物类型未知，保持原始坐标",
        )

    offsets = _generate_spiral_offsets(settings.correction_radius_m, settings.correction_step_m, lat)

    best_lat, best_lon = lat, lon
    best_lr = 0.0
    best_lc_name = "未知"
    found = False

    max_samples = 50
    sample_offsets = offsets[:max_samples]

    for dlat, dlon in sample_offsets:
        candidate_lat = lat + dlat
        candidate_lon = lon + dlon

        lc = await get_landcover(candidate_lat, candidate_lon)
        if lc is not None and lc.class_code in COMBUSTIBLE_CODES:
            if lc.likelihood_ratio > best_lr:
                best_lat = candidate_lat
                best_lon = candidate_lon
                best_lr = lc.likelihood_ratio
                best_lc_name = lc.class_name
                found = True
                break

    if found:
        offset_m = haversine(lat, lon, best_lat, best_lon)
        return CoordinateCorrection(
            original_lat=lat,
            original_lon=lon,
            corrected_lat=round(best_lat, 6),
            corrected_lon=round(best_lon, 6),
            offset_m=round(offset_m, 1),
            correction_applied=True,
            reason=f"原始位置为非可燃地物，修正至最近可燃区域({best_lc_name})，偏移{offset_m:.0f}m",
        )

    return CoordinateCorrection(
        original_lat=lat,
        original_lon=lon,
        corrected_lat=lat,
        corrected_lon=lon,
        offset_m=0.0,
        correction_applied=False,
        reason=f"搜索半径{settings.correction_radius_m}m内未找到可燃地物，保持原始坐标",
    )
