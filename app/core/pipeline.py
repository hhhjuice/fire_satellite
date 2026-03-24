"""Async pipeline orchestrator for satellite fire point validation.

Runs all analysis services in parallel for maximum throughput,
then fuses results into a final SatelliteValidationResult.

No TIF processing, no historical fire queries (ground-only), no geocoding.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.api.schemas import (
    CoordinateCorrection,
    EnvironmentalResult,
    FalsePositiveResult,
    FirePointInput,
    LandCoverResult,
    SatelliteValidationResult,
    ValidateResponse,
    Verdict,
)
from app.core.confidence import compute_confidence, determine_verdict
from app.core.coordinator import correct_coordinates
from app.services.environmental import get_environmental_factors
from app.services.false_positive import detect_false_positives
from app.services.landcover import get_landcover
from app.utils.reason_generator import generate_reasons, generate_summary

logger = logging.getLogger(__name__)


async def validate_single_point(point: FirePointInput) -> SatelliteValidationResult:
    """Validate a single fire point through the satellite analysis pipeline.

    Execution order:
    1. Parallel phase: land cover + environmental (both independent)
    2. Sequential phase: false positive (needs landcover code), coordinate correction (needs landcover code)
    3. Fusion phase: confidence computation (with brightness/FRP bonus) + verdict + reasons
    """
    start_time = time.monotonic()
    lat, lon = point.latitude, point.longitude

    # --- Phase 1: Parallel independent services ---
    landcover_task = asyncio.create_task(get_landcover(lat, lon))
    environmental_task = asyncio.create_task(
        get_environmental_factors(lat, lon, point.acquisition_time)
    )

    landcover_result, environmental_result = await asyncio.gather(
        landcover_task,
        environmental_task,
        return_exceptions=True,
    )

    if isinstance(landcover_result, BaseException):
        logger.warning("Land cover service failed: %s", landcover_result)
        landcover_result = None
    if isinstance(environmental_result, BaseException):
        logger.warning("Environmental service failed: %s", environmental_result)
        environmental_result = None

    landcover_code = landcover_result.class_code if landcover_result else None

    # --- Phase 2: Parallel services depending on Phase 1 ---
    fp_task = asyncio.create_task(
        detect_false_positives(
            lat,
            lon,
            landcover_code=landcover_code,
            acquisition_time=point.acquisition_time,
        )
    )
    correction_task = asyncio.create_task(
        correct_coordinates(lat, lon, current_landcover_code=landcover_code)
    )

    fp_result, correction_result = await asyncio.gather(
        fp_task,
        correction_task,
        return_exceptions=True,
    )

    if isinstance(fp_result, BaseException):
        logger.warning("False positive detection failed: %s", fp_result)
        fp_result = None
    if isinstance(correction_result, BaseException):
        logger.warning("Coordinate correction failed: %s", correction_result)
        correction_result = None

    # --- Phase 3: Fusion ---
    # Use satellite sensor confidence as initial if available
    initial_conf = point.confidence / 100.0 if point.confidence is not None else None

    final_confidence, confidence_breakdown = compute_confidence(
        landcover=landcover_result,
        false_positive=fp_result,
        environmental=environmental_result,
        initial_confidence=initial_conf,
        brightness=point.brightness,
        frp=point.frp,
    )

    verdict = determine_verdict(final_confidence)

    reasons = generate_reasons(
        verdict=verdict,
        confidence=final_confidence,
        landcover=landcover_result,
        false_positive=fp_result,
        environmental=environmental_result,
        coordinate_correction=correction_result,
        brightness=point.brightness,
        frp=point.frp,
    )

    summary = generate_summary(
        verdict=verdict,
        confidence=final_confidence,
        landcover=landcover_result,
        false_positive=fp_result,
    )

    elapsed_ms = (time.monotonic() - start_time) * 1000

    return SatelliteValidationResult(
        input_point=point,
        verdict=verdict,
        final_confidence=final_confidence,
        reasons=reasons,
        summary=summary,
        coordinate_correction=correction_result,
        landcover=landcover_result,
        false_positive=fp_result,
        environmental=environmental_result,
        confidence_breakdown=confidence_breakdown,
        processing_time_ms=round(elapsed_ms, 1),
    )


async def validate_batch(points: list[FirePointInput]) -> ValidateResponse:
    """Validate a batch of fire points.

    Processes all points concurrently using asyncio.gather.
    """
    start_time = time.monotonic()

    tasks = [validate_single_point(point) for point in points]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_results: list[SatelliteValidationResult] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.error("Point %d validation failed: %s", i, result)
            valid_results.append(
                SatelliteValidationResult(
                    input_point=points[i],
                    verdict=Verdict.UNCERTAIN,
                    final_confidence=0.5,
                    reasons=["验证过程发生错误，无法完成分析"],
                    summary="验证失败，返回默认结果",
                    coordinate_correction=None,
                    landcover=None,
                    false_positive=None,
                    environmental=None,
                    confidence_breakdown=None,
                    processing_time_ms=0.0,
                )
            )
        else:
            valid_results.append(result)

    elapsed_ms = (time.monotonic() - start_time) * 1000

    return ValidateResponse(
        results=valid_results,
        total_points=len(valid_results),
        true_fire_count=sum(
            1 for r in valid_results if r.verdict == Verdict.TRUE_FIRE
        ),
        false_positive_count=sum(
            1 for r in valid_results if r.verdict == Verdict.FALSE_POSITIVE
        ),
        uncertain_count=sum(
            1 for r in valid_results if r.verdict == Verdict.UNCERTAIN
        ),
        total_processing_time_ms=round(elapsed_ms, 1),
    )
