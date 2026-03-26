"""Confidence fusion engine for satellite system.

Formula:
    logit(P_final) = logit(P_0) + ln(LR_landcover) + β_env × env_score - total_penalty

No historical component — that's ground-only.
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
from app.utils.math import logit, sigmoid

logger = logging.getLogger(__name__)


def _verdict_from_thresholds(confidence: float, true_fire: float, false_positive: float) -> Verdict:
    if confidence >= true_fire:
        return Verdict.TRUE_FIRE
    elif confidence < false_positive:
        return Verdict.FALSE_POSITIVE
    return Verdict.UNCERTAIN


def compute_confidence(
    landcover: Optional[LandCoverResult] = None,
    false_positive: Optional[FalsePositiveResult] = None,
    environmental: Optional[EnvironmentalResult] = None,
    initial_confidence: Optional[float] = None,
) -> tuple[float, ConfidenceBreakdown]:
    """Compute satellite confidence score using Bayesian logit fusion.

    Args:
        landcover: Land cover analysis result (provides likelihood ratio)
        false_positive: False positive detection result (provides penalty)
        environmental: Environmental factors (provides score in [-0.5, 0.5])
        initial_confidence: Override initial confidence (default from settings)

    Returns:
        Tuple of (final_confidence, breakdown)
    """
    settings = get_settings()

    p0 = initial_confidence if initial_confidence is not None else settings.initial_confidence
    logit_score = logit(p0)

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

    # False positive penalty
    fp_penalty = 0.0
    if false_positive is not None:
        fp_penalty = false_positive.total_penalty
    logit_score -= fp_penalty

    final_confidence = round(sigmoid(logit_score) * 100, 1)

    breakdown = ConfidenceBreakdown(
        initial_confidence=round(p0 * 100, 1),
        landcover_contribution=round(landcover_contribution, 4),
        environmental_contribution=round(environmental_contribution, 4),
        false_positive_penalty=round(fp_penalty, 4),
        final_confidence=final_confidence,
    )

    return final_confidence, breakdown


def determine_verdict(confidence: float) -> Verdict:
    """Determine fire point verdict based on final confidence score."""
    settings = get_settings()
    return _verdict_from_thresholds(
        confidence, settings.threshold_true_fire, settings.threshold_false_positive
    )
