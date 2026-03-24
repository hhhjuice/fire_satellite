"""Environmental factor analysis — pure math, no network I/O."""
import logging
from datetime import datetime, timezone
from typing import Optional

from app.api.schemas import EnvironmentalResult
from app.utils.geo import solar_zenith_angle, is_daytime, get_fire_season_factor

logger = logging.getLogger(__name__)


async def get_environmental_factors(
    lat: float,
    lon: float,
    acquisition_time: Optional[datetime] = None,
) -> EnvironmentalResult:
    """Analyze environmental factors affecting fire likelihood.

    Factors considered:
    1. Day/night: fires detected at night are more likely real
    2. Solar zenith angle: low angles increase false positive risk
    3. Fire season: seasonal adjustment based on hemisphere

    The env_score is a combined factor in range [-0.5, 0.5].
    """
    if acquisition_time is None:
        acquisition_time = datetime.now(timezone.utc)

    zenith = solar_zenith_angle(lat, lon, acquisition_time)
    daytime = is_daytime(lat, lon, acquisition_time)
    season_factor = get_fire_season_factor(lat, acquisition_time.month)

    # Night detection bonus
    if not daytime:
        time_score = 0.2
    elif zenith > 70:
        time_score = -0.15
    else:
        time_score = 0.0

    # Season score
    if season_factor >= 1.3:
        season_score = 0.15
    elif season_factor <= 0.7:
        season_score = -0.1
    else:
        season_score = 0.0

    env_score = max(-0.5, min(0.5, time_score + season_score))

    time_desc = "夜间" if not daytime else "白天"
    if season_factor >= 1.3:
        season_desc = "火灾高发季"
    elif season_factor >= 1.0:
        season_desc = "过渡季节"
    else:
        season_desc = "非火灾季节"

    detail = (
        f"观测时间: {time_desc} (太阳天顶角{zenith:.1f}°), "
        f"季节: {season_desc} (因子{season_factor}), "
        f"环境评分: {env_score:+.2f}"
    )

    return EnvironmentalResult(
        is_daytime=daytime,
        solar_zenith_angle=round(zenith, 2),
        fire_season_factor=season_factor,
        env_score=round(env_score, 4),
        detail=detail,
    )
