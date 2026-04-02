"""Tests for ground-stage confidence fusion engine."""
import pytest

from app.api.schemas import (
    FirmsMatchLevel,
    FirmsResult,
    IndustrialProximity,
    IndustrialResult,
    Verdict,
)
from app.core.ground_confidence import compute_ground_confidence, determine_final_verdict

# ---------------------------------------------------------------------------
# compute_ground_confidence
# ---------------------------------------------------------------------------

def test_no_ground_data_preserves_satellite_confidence() -> None:
    final, breakdown = compute_ground_confidence(70.0)
    assert final == pytest.approx(70.0, abs=0.1)
    assert breakdown.firms_contribution == 0.0
    assert breakdown.industrial_contribution == 0.0
    assert breakdown.satellite_confidence == pytest.approx(70.0, abs=0.1)


def test_firms_exact_match_increases_confidence() -> None:
    firms = FirmsResult(match_level=FirmsMatchLevel.EXACT_MATCH)
    conf_base, _ = compute_ground_confidence(70.0)
    conf_firms, breakdown = compute_ground_confidence(70.0, firms=firms)
    assert conf_firms > conf_base
    assert breakdown.firms_contribution > 0


def test_firms_no_history_decreases_confidence() -> None:
    firms = FirmsResult(match_level=FirmsMatchLevel.NO_HISTORY)
    conf_base, _ = compute_ground_confidence(70.0)
    conf_firms, breakdown = compute_ground_confidence(70.0, firms=firms)
    assert conf_firms < conf_base
    assert breakdown.firms_contribution < 0


def test_industrial_penalty_decreases_confidence() -> None:
    industrial = IndustrialResult(proximity=IndustrialProximity.WITHIN_500M)
    conf_base, _ = compute_ground_confidence(70.0)
    conf_ind, breakdown = compute_ground_confidence(70.0, industrial=industrial)
    assert conf_ind < conf_base
    assert breakdown.industrial_contribution == pytest.approx(-2.5)


def test_gas_flare_skips_industrial_penalty() -> None:
    industrial = IndustrialResult(proximity=IndustrialProximity.WITHIN_500M, is_gas_flare=True)
    conf_base, _ = compute_ground_confidence(70.0)
    conf_flare, breakdown = compute_ground_confidence(70.0, industrial=industrial)
    assert conf_flare == pytest.approx(conf_base, abs=0.1)
    assert breakdown.industrial_contribution == 0.0


def test_firms_and_industrial_contributions_are_additive() -> None:
    firms = FirmsResult(match_level=FirmsMatchLevel.EXACT_MATCH)
    industrial = IndustrialResult(proximity=IndustrialProximity.WITHIN_500M)
    conf_firms_only, _ = compute_ground_confidence(70.0, firms=firms)
    conf_ind_only, _ = compute_ground_confidence(70.0, industrial=industrial)
    conf_both, _ = compute_ground_confidence(70.0, firms=firms, industrial=industrial)
    assert conf_ind_only < conf_both < conf_firms_only


# ---------------------------------------------------------------------------
# determine_final_verdict  — thresholds are 75 / 50
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (75.0, Verdict.TRUE_FIRE),
        (100.0, Verdict.TRUE_FIRE),
        (74.9, Verdict.UNCERTAIN),
        (50.0, Verdict.UNCERTAIN),
        (49.9, Verdict.FALSE_POSITIVE),
        (0.0, Verdict.FALSE_POSITIVE),
    ],
)
def test_determine_final_verdict_thresholds(confidence: float, expected: Verdict) -> None:
    assert determine_final_verdict(confidence) == expected


def test_final_verdict_true_fire_requires_75() -> None:
    """Both satellite and ground stages use 75 as TRUE_FIRE threshold."""
    assert determine_final_verdict(70.0) == Verdict.UNCERTAIN
    assert determine_final_verdict(75.0) == Verdict.TRUE_FIRE


# ---------------------------------------------------------------------------
# End-to-end scenario checks
# ---------------------------------------------------------------------------

def test_scenario_strong_true_fire() -> None:
    """Grassland satellite output (~92%) + FIRMS exact match → TRUE_FIRE."""
    firms = FirmsResult(match_level=FirmsMatchLevel.EXACT_MATCH)
    industrial = IndustrialResult(proximity=IndustrialProximity.NONE)
    final, _ = compute_ground_confidence(92.0, firms=firms, industrial=industrial)
    assert determine_final_verdict(final) == Verdict.TRUE_FIRE
    assert final >= 75.0


def test_scenario_industrial_false_positive() -> None:
    """Urban satellite output (~15%) + no FIRMS + plant <500m → FALSE_POSITIVE."""
    firms = FirmsResult(match_level=FirmsMatchLevel.CONFIRMED_NONE)
    industrial = IndustrialResult(proximity=IndustrialProximity.WITHIN_500M)
    final, _ = compute_ground_confidence(15.0, firms=firms, industrial=industrial)
    assert determine_final_verdict(final) == Verdict.FALSE_POSITIVE
    assert final < 50.0


def test_scenario_uncertain_no_ground_data() -> None:
    """Moderate satellite output + weak ground signal → stays UNCERTAIN."""
    firms = FirmsResult(match_level=FirmsMatchLevel.NO_HISTORY)
    industrial = IndustrialResult(proximity=IndustrialProximity.NONE)
    final, _ = compute_ground_confidence(69.0, firms=firms, industrial=industrial)
    assert determine_final_verdict(final) in {Verdict.UNCERTAIN, Verdict.FALSE_POSITIVE}
