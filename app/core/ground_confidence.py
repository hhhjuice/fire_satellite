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
    FirmsMatchLevel,
    FirmsResult,
    GroundConfidenceBreakdown,
    IndustrialProximity,
    IndustrialResult,
    Verdict,
)
from app.config import get_settings
from app.core.confidence import _verdict_from_thresholds
from app.utils.math import logit, sigmoid

logger = logging.getLogger(__name__)


def compute_ground_confidence(
    satellite_confidence: float,
    firms: Optional[FirmsResult] = None,
    industrial: Optional[IndustrialResult] = None,
) -> tuple[float, GroundConfidenceBreakdown]:
    """Compute final confidence by applying ground-stage corrections.

    LR values (FIRMS) and logit deltas (industrial) are looked up from
    config based on the semantic enum level, so the caller only needs to
    specify match_level / proximity — not raw numeric values.

    Args:
        satellite_confidence: Output of the satellite validation stage (0–100).
        firms: FIRMS historical fire data match result.
        industrial: Industrial facility proximity detection result.

    Returns:
        Tuple of (final_confidence, breakdown).
    """
    settings = get_settings()
    logit_score = logit(satellite_confidence / 100.0)

    firms_lr_map = {
        FirmsMatchLevel.EXACT_MATCH: settings.firms_lr_exact_match,
        FirmsMatchLevel.NEARBY_SAME_SEASON: settings.firms_lr_nearby_same_season,
        FirmsMatchLevel.REGIONAL: settings.firms_lr_regional,
        FirmsMatchLevel.NO_SEASON_RECORD: settings.firms_lr_no_season_record,
        FirmsMatchLevel.NO_HISTORY: settings.firms_lr_no_history,
        FirmsMatchLevel.CONFIRMED_NONE: settings.firms_lr_confirmed_none,
    }
    industrial_delta_map = {
        IndustrialProximity.WITHIN_500M: settings.industrial_delta_within_500m,
        IndustrialProximity.WITHIN_2KM: settings.industrial_delta_within_2km,
        IndustrialProximity.WITHIN_5KM: settings.industrial_delta_within_5km,
        IndustrialProximity.NONE: settings.industrial_delta_none,
    }

    firms_contribution = 0.0
    if firms is not None:
        lr = firms_lr_map[firms.match_level]
        firms_contribution = math.log(lr)
        logger.debug("FIRMS contribution: %.4f (LR=%.2f, level=%s)",
                     firms_contribution, lr, firms.match_level)
    logit_score += firms_contribution

    # Gas flares are genuine combustion sources — skip the industrial penalty.
    industrial_contribution = 0.0
    if industrial is not None and not industrial.is_gas_flare:
        industrial_contribution = industrial_delta_map[industrial.proximity]
        logger.debug("Industrial contribution: %.4f (proximity=%s)",
                     industrial_contribution, industrial.proximity)
    logit_score += industrial_contribution

    final_confidence = round(sigmoid(logit_score) * 100, 1)

    breakdown = GroundConfidenceBreakdown(
        satellite_confidence=round(satellite_confidence, 1),
        firms_contribution=round(firms_contribution, 4),
        industrial_contribution=round(industrial_contribution, 4),
        final_confidence=final_confidence,
    )

    return final_confidence, breakdown


def determine_final_verdict(confidence: float) -> Verdict:
    """Determine final verdict using ground-stage thresholds (75/50).

    Stricter than satellite-only thresholds (70/50): the combined
    satellite+ground evidence justifies a higher bar for TRUE_FIRE.
    """
    settings = get_settings()
    return _verdict_from_thresholds(
        confidence, settings.threshold_true_fire_final, settings.threshold_false_positive_final
    )
