"""Tests for satellite validation pipeline orchestration."""
from datetime import datetime, timezone
import sys
import types

import pytest

from app.api.schemas import (
    CoordinateCorrection,
    EnvironmentalResult,
    FalsePositiveFlag,
    FalsePositiveResult,
    FirePointInput,
    LandCoverResult,
    Verdict,
)

if "rasterio" not in sys.modules:
    rasterio_stub = types.ModuleType("rasterio")
    rasterio_errors_stub = types.ModuleType("rasterio.errors")
    rasterio_windows_stub = types.ModuleType("rasterio.windows")

    class RasterioIOError(Exception):
        pass

    class Window:
        def __init__(self, *args, **kwargs):
            pass

    rasterio_stub.open = lambda *args, **kwargs: None
    rasterio_errors_stub.RasterioIOError = RasterioIOError
    rasterio_windows_stub.Window = Window
    sys.modules["rasterio"] = rasterio_stub
    sys.modules["rasterio.errors"] = rasterio_errors_stub
    sys.modules["rasterio.windows"] = rasterio_windows_stub

from app.core import pipeline


@pytest.mark.asyncio
async def test_coordinate_correction_recomputes_final_analysis(monkeypatch) -> None:
    """Corrected coordinates should drive final verdict while preserving original analysis."""
    water = LandCoverResult(class_code=80, class_name="水体", likelihood_ratio=0.01)
    grass = LandCoverResult(class_code=30, class_name="草地", likelihood_ratio=3.0)

    async def fake_get_landcover(lat: float, lon: float):
        return grass if lat == pytest.approx(1.001) else water

    async def fake_environmental(lat: float, lon: float, acquisition_time):
        return EnvironmentalResult(
            is_daytime=True,
            solar_zenith_angle=40.0,
            fire_season_factor=1.0,
            env_score=0.0,
            detail="环境因素中性",
        )

    async def fake_false_positive(lat: float, lon: float, landcover_code, acquisition_time):
        if landcover_code == 80:
            return FalsePositiveResult(
                flags=[
                    FalsePositiveFlag(
                        detector="water_body",
                        triggered=True,
                        penalty=3.0,
                        detail="火点位于水体区域，极可能为假阳性",
                    )
                ],
                total_penalty=3.0,
                is_likely_false_positive=True,
            )
        return FalsePositiveResult(flags=[], total_penalty=0.0, is_likely_false_positive=False)

    async def fake_correction(lat: float, lon: float, current_landcover_code):
        return CoordinateCorrection(
            original_lat=lat,
            original_lon=lon,
            corrected_lat=1.001,
            corrected_lon=2.001,
            offset_m=150.0,
            correction_applied=True,
            reason="原始位置为非可燃地物，修正至最近可燃区域(草地)，偏移150m",
        )

    monkeypatch.setattr(pipeline, "get_landcover", fake_get_landcover)
    monkeypatch.setattr(pipeline, "get_environmental_factors", fake_environmental)
    monkeypatch.setattr(pipeline, "detect_false_positives", fake_false_positive)
    monkeypatch.setattr(pipeline, "correct_coordinates", fake_correction)

    result = await pipeline.validate_single_point(
        FirePointInput(
            latitude=1.0,
            longitude=2.0,
            confidence=60.0,
            acquisition_time=datetime(2026, 2, 15, tzinfo=timezone.utc),
        )
    )

    assert result.coordinate_correction is not None
    assert result.coordinate_correction.correction_applied is True
    assert result.original_analysis is not None
    assert result.original_analysis.landcover is not None
    assert result.original_analysis.landcover.class_name == "水体"
    assert result.landcover is not None
    assert result.landcover.class_name == "草地"
    assert result.verdict == Verdict.TRUE_FIRE
    assert result.final_confidence > result.original_analysis.final_confidence


@pytest.mark.asyncio
async def test_batch_fallback_confidence_uses_percent_scale(monkeypatch) -> None:
    async def fake_validate_single_point(point: FirePointInput):
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline, "validate_single_point", fake_validate_single_point)

    response = await pipeline.validate_batch([FirePointInput(latitude=1.0, longitude=2.0)])

    assert response.results[0].verdict == Verdict.UNCERTAIN
    assert response.results[0].final_confidence == 50.0


@pytest.mark.asyncio
async def test_coordinate_correction_searches_beyond_first_50_samples(monkeypatch) -> None:
    from app.core import coordinator

    calls = 0
    grass = LandCoverResult(class_code=30, class_name="草地", likelihood_ratio=3.0)

    async def fake_get_landcover(lat: float, lon: float):
        nonlocal calls
        calls += 1
        return grass if calls == 51 else None

    monkeypatch.setattr(coordinator, "get_landcover", fake_get_landcover)

    correction = await coordinator.correct_coordinates(1.0, 2.0, current_landcover_code=80)

    assert calls == 51
    assert correction.correction_applied is True
    assert correction.reason.startswith("原始位置为非可燃地物")
