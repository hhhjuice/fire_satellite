"""Tests for satellite confidence engine."""
import pytest

from app.api.schemas import (
    EnvironmentalResult,
    Verdict,
)
from app.core.confidence import compute_confidence, determine_verdict


def test_compute_confidence_defaults_to_baseline_uncertain() -> None:
    confidence, breakdown = compute_confidence()
    assert confidence == pytest.approx(0.5, abs=1e-4)
    assert breakdown.final_confidence == pytest.approx(0.5, abs=1e-4)
    assert determine_verdict(confidence) == Verdict.UNCERTAIN


def test_compute_confidence_grassland_increases_confidence(grassland_result) -> None:
    confidence, _ = compute_confidence(landcover=grassland_result)
    assert confidence > 0.7
    assert determine_verdict(confidence) in {Verdict.TRUE_FIRE, Verdict.UNCERTAIN}


def test_compute_confidence_water_strongly_decreases_confidence(water_result) -> None:
    confidence, _ = compute_confidence(landcover=water_result)
    assert confidence < 0.1
    assert determine_verdict(confidence) == Verdict.FALSE_POSITIVE


def test_false_positive_penalty_decreases_confidence(grassland_result, water_flag_result) -> None:
    base_confidence, _ = compute_confidence(landcover=grassland_result)
    penalized_confidence, _ = compute_confidence(
        landcover=grassland_result,
        false_positive=water_flag_result,
    )
    assert penalized_confidence < base_confidence


def test_brightness_bonus_increases_confidence(grassland_result) -> None:
    """High brightness temperature adds bonus to logit score."""
    base_confidence, base_bd = compute_confidence(landcover=grassland_result)
    bright_confidence, bright_bd = compute_confidence(
        landcover=grassland_result,
        brightness=350.0,
    )
    assert bright_confidence > base_confidence
    assert bright_bd.brightness_bonus > 0


def test_frp_bonus_increases_confidence(grassland_result) -> None:
    """High FRP adds bonus to logit score."""
    base_confidence, _ = compute_confidence(landcover=grassland_result)
    frp_confidence, frp_bd = compute_confidence(
        landcover=grassland_result,
        frp=25.0,
    )
    assert frp_confidence > base_confidence
    assert frp_bd.frp_bonus > 0


def test_low_brightness_no_bonus(grassland_result) -> None:
    """Brightness below threshold gives no bonus."""
    _, bd = compute_confidence(landcover=grassland_result, brightness=300.0)
    assert bd.brightness_bonus == 0.0


def test_low_frp_no_bonus(grassland_result) -> None:
    """FRP below threshold gives no bonus."""
    _, bd = compute_confidence(landcover=grassland_result, frp=10.0)
    assert bd.frp_bonus == 0.0


def test_environmental_score_influences_confidence() -> None:
    low_env = EnvironmentalResult(
        is_daytime=False,
        solar_zenith_angle=110.0,
        fire_season_factor=0.7,
        env_score=-0.5,
        detail="",
    )
    high_env = EnvironmentalResult(
        is_daytime=True,
        solar_zenith_angle=20.0,
        fire_season_factor=1.3,
        env_score=0.5,
        detail="",
    )

    c_low, _ = compute_confidence(environmental=low_env)
    c_high, _ = compute_confidence(environmental=high_env)
    assert c_high > c_low


def test_initial_confidence_override() -> None:
    """Custom initial confidence should change the baseline."""
    high_conf, _ = compute_confidence(initial_confidence=0.8)
    low_conf, _ = compute_confidence(initial_confidence=0.2)
    assert high_conf > low_conf


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.75, Verdict.TRUE_FIRE),
        (0.90, Verdict.TRUE_FIRE),
        (0.3499, Verdict.FALSE_POSITIVE),
        (0.20, Verdict.FALSE_POSITIVE),
        (0.35, Verdict.UNCERTAIN),
        (0.50, Verdict.UNCERTAIN),
        (0.74, Verdict.UNCERTAIN),
    ],
)
def test_determine_verdict_thresholds(confidence: float, expected: Verdict) -> None:
    assert determine_verdict(confidence) == expected
