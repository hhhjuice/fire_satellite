"""False positive detection — 4 detectors (no industrial, no network).

Satellite-only detectors:
1. Water body (landcover code 80)
2. Urban heat island (landcover code 50)
3. Sun glint (solar zenith 60-85°)
4. Coastal reflection (landcover codes 90, 95)
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from app.api.schemas import FalsePositiveFlag, FalsePositiveResult
from app.config import get_settings
from app.utils.geo import solar_zenith_angle

logger = logging.getLogger(__name__)


def detect_water_body(landcover_code: Optional[int]) -> FalsePositiveFlag:
    settings = get_settings()
    triggered = landcover_code == 80
    return FalsePositiveFlag(
        detector="water_body",
        triggered=triggered,
        penalty=settings.fp_penalty_water if triggered else 0.0,
        detail="火点位于水体区域，极可能为假阳性" if triggered else "非水体区域",
    )


def detect_urban_heat(landcover_code: Optional[int]) -> FalsePositiveFlag:
    settings = get_settings()
    triggered = landcover_code == 50
    return FalsePositiveFlag(
        detector="urban_heat",
        triggered=triggered,
        penalty=settings.fp_penalty_urban if triggered else 0.0,
        detail="火点位于建筑用地，可能为城市热岛效应" if triggered else "非建筑用地",
    )


def detect_sun_glint(lat: float, lon: float, dt: Optional[datetime] = None) -> FalsePositiveFlag:
    settings = get_settings()
    if dt is None:
        dt = datetime.now(timezone.utc)

    zenith = solar_zenith_angle(lat, lon, dt)
    triggered = 60.0 <= zenith <= 85.0

    return FalsePositiveFlag(
        detector="sun_glint",
        triggered=triggered,
        penalty=settings.fp_penalty_sun_glint if triggered else 0.0,
        detail=f"太阳天顶角{zenith:.1f}°，{'可能产生太阳耀斑' if triggered else '太阳角度正常'}",
    )


def detect_coastal_reflection(landcover_code: Optional[int]) -> FalsePositiveFlag:
    settings = get_settings()
    coastal_codes = {90, 95}
    triggered = landcover_code in coastal_codes

    return FalsePositiveFlag(
        detector="coastal_reflection",
        triggered=triggered,
        penalty=settings.fp_penalty_coastal if triggered else 0.0,
        detail="火点位于湿地/红树林区域，可能为海岸反射" if triggered else "非海岸/湿地区域",
    )


async def detect_false_positives(
    lat: float,
    lon: float,
    landcover_code: Optional[int] = None,
    acquisition_time: Optional[datetime] = None,
) -> FalsePositiveResult:
    """Run all 4 satellite false positive detectors (no industrial — needs OSM)."""
    flags = [
        detect_water_body(landcover_code),
        detect_urban_heat(landcover_code),
        detect_sun_glint(lat, lon, acquisition_time),
        detect_coastal_reflection(landcover_code),
    ]

    total_penalty = sum(flag.penalty for flag in flags)
    any_triggered = any(flag.triggered for flag in flags)

    return FalsePositiveResult(
        flags=flags,
        total_penalty=total_penalty,
        is_likely_false_positive=any_triggered,
    )
