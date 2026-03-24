"""Satellite fire validation system configuration.

No network URLs — satellite operates offline with local GIS data.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Confidence thresholds
    threshold_true_fire: float = 0.75
    threshold_false_positive: float = 0.35
    initial_confidence: float = 0.5

    # Confidence weights
    beta_env: float = 0.2

    # Brightness / FRP bonus (satellite-specific)
    brightness_bonus_threshold: float = 340.0  # Kelvin
    brightness_bonus: float = 0.3
    frp_bonus_threshold: float = 20.0  # MW
    frp_bonus: float = 0.3

    # Land cover likelihood ratios (ESA WorldCover class -> LR)
    # 10=Tree, 20=Shrubland, 30=Grassland, 40=Cropland, 50=Built-up,
    # 60=Bare/sparse, 70=Snow/Ice, 80=Water, 90=Herbaceous wetland,
    # 95=Mangroves, 100=Moss/Lichen
    landcover_lr: dict[int, float] = {
        10: 2.5, 20: 2.8, 30: 3.0, 40: 1.8, 50: 0.2,
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

    # Data directories (local GeoTIFF)
    data_dir: Path = Path("data")
    worldcover_dir: Path = Path("data/worldcover")

    # Coordinate correction
    correction_radius_m: float = 500.0
    correction_step_m: float = 50.0

    model_config = {"env_prefix": "SAT_", "env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
