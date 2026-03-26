"""Ground-stage confidence fusion engine.

Formula:
    logit(P_final) = logit(P_sat / 100) + ln(LR_firms) + Δ_industrial
    P_final = sigmoid(logit(P_final)) × 100

Thresholds (final authoritative verdicts):
    ≥ 75 → TRUE_FIRE
    < 50 → FALSE_POSITIVE
    else → UNCERTAIN

This module contains only the math.  Data fetching (FIRMS queries,
industrial-facility lookups) is the responsibility of the ground system.
"""
import logging
import math
from typing import Optional

from app.api.schemas import (
    FirmsResult,
    GroundConfidenceBreakdown,
    IndustrialResult,
    Verdict,
)
from app.config import get_settings

logger = logging.getLogger(__name__)


def _logit(p: float) -> float:
    """Log-odds of probability p. Clamps to avoid ±infinity."""
    p = max(1e-9, min(1 - 1e-9, p))
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    """Sigmoid function. Clamps input to avoid overflow."""
    x = max(-20.0, min(20.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def compute_ground_confidence(
    satellite_confidence: float,
    firms: Optional[FirmsResult] = None,
    industrial: Optional[IndustrialResult] = None,
) -> tuple[float, GroundConfidenceBreakdown]:
    """Compute final confidence by applying ground-stage corrections.

    Args:
        satellite_confidence: Output of the satellite validation stage (0–100).
        firms: FIRMS historical fire data match result.
        industrial: Industrial facility proximity detection result.

    Returns:
        Tuple of (final_confidence, breakdown).
    """
    logit_score = _logit(satellite_confidence / 100.0)

    # FIRMS historical data contribution: ln(LR_firms)
    firms_contribution = 0.0
    if firms is not None:
        firms_contribution = math.log(firms.likelihood_ratio)
        logger.debug("FIRMS contribution: %.4f (LR=%.2f, level=%s)",
                     firms_contribution, firms.likelihood_ratio, firms.match_level)
    logit_score += firms_contribution

    # Industrial facility correction: Δ_industrial
    # Gas flares are genuine combustion sources — skip the penalty.
    industrial_contribution = 0.0
    if industrial is not None and not industrial.is_gas_flare:
        industrial_contribution = industrial.delta_logit
        logger.debug("Industrial contribution: %.4f (proximity=%s)",
                     industrial_contribution, industrial.proximity)
    logit_score += industrial_contribution

    final_confidence = round(_sigmoid(logit_score) * 100, 1)

    breakdown = GroundConfidenceBreakdown(
        satellite_confidence=round(satellite_confidence, 1),
        firms_contribution=round(firms_contribution, 4),
        industrial_contribution=round(industrial_contribution, 4),
        final_confidence=final_confidence,
    )

    return final_confidence, breakdown


def determine_final_verdict(confidence: float) -> Verdict:
    """Determine final verdict using ground-stage thresholds (75/50).

    These thresholds are stricter than the satellite-only thresholds (70/50):
    the combined satellite+ground evidence justifies a higher bar for TRUE_FIRE.
    """
    settings = get_settings()
    if confidence >= settings.threshold_true_fire_final:
        return Verdict.TRUE_FIRE
    elif confidence < settings.threshold_false_positive_final:
        return Verdict.FALSE_POSITIVE
    else:
        return Verdict.UNCERTAIN
