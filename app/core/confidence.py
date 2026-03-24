"""Confidence fusion engine for satellite system.

Formula:
    logit(P_final) = logit(P_0) + ln(LR_landcover) + β_env × env_score
                     + brightness_bonus + frp_bonus - total_penalty

No historical component — that's ground-only.
Adds brightness_bonus (+0.3 if >340K) and frp_bonus (+0.3 if >20MW).
"""
import logging
import math
from typing import Optional

from app.api.schemas import (
    ConfidenceBreakdown,
    EnvironmentalResult,
    FalsePositiveResult,
    LandCoverResult,
    Verdict,
)
from app.config import get_settings

logger = logging.getLogger(__name__)


def _logit(p: float) -> float:
    """Compute logit (log-odds) of probability p. Clamps to avoid infinity."""
    p = max(1e-9, min(1 - 1e-9, p))
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    """Compute sigmoid function. Clamps input to avoid overflow."""
    x = max(-20.0, min(20.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def compute_confidence(
    landcover: Optional[LandCoverResult] = None,
    false_positive: Optional[FalsePositiveResult] = None,
    environmental: Optional[EnvironmentalResult] = None,
    initial_confidence: Optional[float] = None,
    brightness: Optional[float] = None,
    frp: Optional[float] = None,
) -> tuple[float, ConfidenceBreakdown]:
    """Compute satellite confidence score using Bayesian logit fusion.

    Args:
        landcover: Land cover analysis result (provides likelihood ratio)
        false_positive: False positive detection result (provides penalty)
        environmental: Environmental factors (provides score in [-0.5, 0.5])
        initial_confidence: Override initial confidence (default from settings)
        brightness: Brightness temperature in Kelvin (satellite sensor data)
        frp: Fire radiative power in MW (satellite sensor data)

    Returns:
        Tuple of (final_confidence, breakdown)
    """
    settings = get_settings()

    p0 = initial_confidence if initial_confidence is not None else settings.initial_confidence
    logit_score = _logit(p0)

    # Land cover contribution
    landcover_contribution = 0.0
    if landcover is not None:
        lr = landcover.likelihood_ratio
        if lr > 0:
            landcover_contribution = math.log(lr)
    logit_score += landcover_contribution

    # Environmental contribution
    environmental_contribution = 0.0
    if environmental is not None:
        environmental_contribution = settings.beta_env * environmental.env_score
    logit_score += environmental_contribution

    # Brightness bonus (satellite-specific)
    brightness_bonus_val = 0.0
    if brightness is not None and brightness > settings.brightness_bonus_threshold:
        brightness_bonus_val = settings.brightness_bonus
    logit_score += brightness_bonus_val

    # FRP bonus (satellite-specific)
    frp_bonus_val = 0.0
    if frp is not None and frp > settings.frp_bonus_threshold:
        frp_bonus_val = settings.frp_bonus
    logit_score += frp_bonus_val

    # False positive penalty
    fp_penalty = 0.0
    if false_positive is not None:
        fp_penalty = false_positive.total_penalty
    logit_score -= fp_penalty

    final_confidence = _sigmoid(logit_score)
    final_confidence = round(final_confidence, 4)

    breakdown = ConfidenceBreakdown(
        initial_confidence=p0,
        landcover_contribution=round(landcover_contribution, 4),
        environmental_contribution=round(environmental_contribution, 4),
        brightness_bonus=round(brightness_bonus_val, 4),
        frp_bonus=round(frp_bonus_val, 4),
        false_positive_penalty=round(fp_penalty, 4),
        final_confidence=final_confidence,
    )

    return final_confidence, breakdown


def determine_verdict(confidence: float) -> Verdict:
    """Determine fire point verdict based on final confidence score."""
    settings = get_settings()

    if confidence >= settings.threshold_true_fire:
        return Verdict.TRUE_FIRE
    elif confidence < settings.threshold_false_positive:
        return Verdict.FALSE_POSITIVE
    else:
        return Verdict.UNCERTAIN
