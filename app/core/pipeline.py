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
    FirePointInput,
    SatelliteAnalysisSnapshot,
    SatelliteValidationResult,
    ValidateResponse,
    Verdict,
)
from app.config import get_settings
from app.core.confidence import compute_confidence, determine_verdict
from app.core.coordinator import correct_coordinates
from app.services.environmental import get_environmental_factors
from app.services.false_positive import detect_false_positives
from app.services.landcover import get_landcover
from app.utils.reason_generator import generate_reasons, generate_summary

logger = logging.getLogger(__name__)


async def _analyze_location(
    lat: float,
    lon: float,
    point: FirePointInput,
    initial_confidence: Optional[float],
) -> SatelliteAnalysisSnapshot:
    """Run location-dependent satellite analysis at a concrete coordinate."""
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
        logger.warning(
            "Land cover service failed near lat=%.2f lon=%.2f: %s",
            lat,
            lon,
            landcover_result,
            exc_info=_exc_info(landcover_result),
        )
        landcover_result = None
    if isinstance(environmental_result, BaseException):
        logger.warning(
            "Environmental service failed near lat=%.2f lon=%.2f: %s",
            lat,
            lon,
            environmental_result,
            exc_info=_exc_info(environmental_result),
        )
        environmental_result = None

    landcover_code = landcover_result.class_code if landcover_result else None
    try:
        fp_result = await detect_false_positives(
            lat,
            lon,
            landcover_code=landcover_code,
            acquisition_time=point.acquisition_time,
        )
    except Exception as exc:
        logger.warning(
            "False positive detection failed near lat=%.2f lon=%.2f: %s",
            lat,
            lon,
            exc,
            exc_info=_exc_info(exc),
        )
        fp_result = None

    final_confidence, confidence_breakdown = compute_confidence(
        landcover=landcover_result,
        false_positive=fp_result,
        environmental=environmental_result,
        initial_confidence=initial_confidence,
    )
    verdict = determine_verdict(final_confidence)

    return SatelliteAnalysisSnapshot(
        latitude=lat,
        longitude=lon,
        verdict=verdict,
        final_confidence=final_confidence,
        landcover=landcover_result,
        false_positive=fp_result,
        environmental=environmental_result,
        confidence_breakdown=confidence_breakdown,
    )


def _exc_info(exc: BaseException) -> tuple[type[BaseException], BaseException, object]:
    return (type(exc), exc, exc.__traceback__)


async def validate_single_point(point: FirePointInput) -> SatelliteValidationResult:
    """Validate a single fire point through the satellite analysis pipeline.

    Execution order:
    1. Analyze the original coordinate.
    2. If correction is applied, analyze the corrected coordinate.
    3. Use corrected-coordinate analysis as the final verdict while retaining the original snapshot.
    """
    start_time = time.monotonic()
    lat, lon = point.latitude, point.longitude

    # Use satellite sensor confidence as initial if available.
    initial_conf = point.confidence / 100.0 if point.confidence is not None else None

    original_analysis = await _analyze_location(lat, lon, point, initial_conf)

    try:
        correction_result = await correct_coordinates(
            lat,
            lon,
            current_landcover_code=(
                original_analysis.landcover.class_code
                if original_analysis.landcover is not None
                else None
            ),
        )
    except Exception as exc:
        logger.warning(
            "Coordinate correction failed near lat=%.2f lon=%.2f: %s",
            lat,
            lon,
            exc,
            exc_info=_exc_info(exc),
        )
        correction_result = None

    final_analysis = original_analysis
    original_snapshot = None
    if correction_result is not None and correction_result.correction_applied:
        final_analysis = await _analyze_location(
            correction_result.corrected_lat,
            correction_result.corrected_lon,
            point,
            initial_conf,
        )
        original_snapshot = original_analysis

    reasons = generate_reasons(
        verdict=final_analysis.verdict,
        confidence=final_analysis.final_confidence,
        landcover=final_analysis.landcover,
        false_positive=final_analysis.false_positive,
        environmental=final_analysis.environmental,
        coordinate_correction=correction_result,
    )

    summary = generate_summary(
        verdict=final_analysis.verdict,
        confidence=final_analysis.final_confidence,
        landcover=final_analysis.landcover,
        false_positive=final_analysis.false_positive,
    )

    settings = get_settings()
    fire_area_m2: Optional[float] = None
    if point.fire_pixel is not None:
        fire_area_m2 = point.fire_pixel * (settings.pixel_resolution_m ** 2)

    elapsed_ms = (time.monotonic() - start_time) * 1000

    return SatelliteValidationResult(
        input_point=point,
        verdict=final_analysis.verdict,
        final_confidence=final_analysis.final_confidence,
        fire_area_m2=fire_area_m2,
        reasons=reasons,
        summary=summary,
        coordinate_correction=correction_result,
        landcover=final_analysis.landcover,
        false_positive=final_analysis.false_positive,
        environmental=final_analysis.environmental,
        confidence_breakdown=final_analysis.confidence_breakdown,
        original_analysis=original_snapshot,
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
            point = points[i]
            logger.error(
                "Point %d validation failed near lat=%.2f lon=%.2f: %s",
                i,
                point.latitude,
                point.longitude,
                result,
                exc_info=_exc_info(result),
            )
            valid_results.append(
                SatelliteValidationResult(
                    input_point=points[i],
                    verdict=Verdict.UNCERTAIN,
                    final_confidence=50.0,
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
