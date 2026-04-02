"""Satellite fire validation system configuration.

No network URLs — satellite operates offline with local GIS data.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Confidence thresholds (external scale 0-100)
    threshold_true_fire: float = 75.0
    threshold_false_positive: float = 50.0
    initial_confidence: float = 0.5  # internal P₀ default [0,1]

    # Confidence weights
    beta_env: float = 0.5

    # Land cover likelihood ratios (ESA WorldCover class -> LR)
    # 10=Tree, 20=Shrubland, 30=Grassland, 40=Cropland, 50=Built-up,
    # 60=Bare/sparse, 70=Snow/Ice, 80=Water, 90=Herbaceous wetland,
    # 95=Mangroves, 100=Moss/Lichen
    landcover_lr: dict[int, float] = {
        10: 3.0, 20: 3.5, 30: 4.0, 40: 2.0, 50: 0.2,
        60: 0.05, 70: 0.01, 80: 0.01, 90: 1.5, 95: 1.2, 100: 1.0,
    }

    # Land cover class names (Chinese)
    landcover_names: dict[int, str] = {
        10: "林地", 20: "灌木地", 30: "草地", 40: "农田",
        50: "建筑用地", 60: "裸地/稀疏植被", 70: "冰雪",
        80: "水体", 90: "草本湿地", 95: "红树林", 100: "苔藓/地衣",
    }

    # False positive penalty values (4 detectors — no industrial on satellite)
    fp_penalty_water: float = 3.0
    fp_penalty_urban: float = 1.5
    fp_penalty_sun_glint: float = 1.0
    fp_penalty_coastal: float = 1.2

    # Ground validation thresholds (final verdicts — used by ground system, 75/50)
    threshold_true_fire_final: float = 75.0
    threshold_false_positive_final: float = 50.0

    # FIRMS historical fire data likelihood ratios (ground stage)
    firms_lr_exact_match: float = 4.0          # Within 1km in recent 5 days
    firms_lr_nearby: float = 2.5               # Within 5km in recent 5 days
    firms_lr_regional: float = 1.5             # Within 10km in recent 5 days
    firms_lr_no_history: float = 0.5           # No record within 10km

    # Industrial facility logit corrections (ground stage, negative = penalty)
    industrial_delta_within_500m: float = -2.5
    industrial_delta_within_2km: float = -1.5
    industrial_delta_within_5km: float = -0.8
    industrial_delta_none: float = 0.3         # No facility within 10km

    # Data directories (local GeoTIFF)
    data_dir: Path = Path("data")
    worldcover_dir: Path = Path("data/worldcover")

    # Camera pixel resolution (meters per pixel, for fire area calculation)
    pixel_resolution_m: float = 50.0

    # Coordinate correction
    correction_radius_m: float = 500.0
    correction_step_m: float = 50.0

    model_config = {"env_prefix": "SAT_", "env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
