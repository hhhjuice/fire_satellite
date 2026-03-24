"""Tests for satellite schemas."""
import pytest
from pydantic import ValidationError

from app.api.schemas import (
    FirePointInput,
    SatelliteValidationResult,
    ValidateRequest,
    Verdict,
)


def test_fire_point_input_accepts_valid_coordinates() -> None:
    point = FirePointInput(latitude=35.2, longitude=110.7)
    assert point.latitude == pytest.approx(35.2)
    assert point.longitude == pytest.approx(110.7)


def test_fire_point_input_rejects_invalid_latitude() -> None:
    with pytest.raises(ValidationError):
        FirePointInput(latitude=95.0, longitude=0.0)


def test_validate_request_requires_at_least_one_point() -> None:
    with pytest.raises(ValidationError):
        ValidateRequest(points=[])


def test_verdict_enum_values() -> None:
    assert Verdict.TRUE_FIRE.value == "TRUE_FIRE"
    assert Verdict.FALSE_POSITIVE.value == "FALSE_POSITIVE"
    assert Verdict.UNCERTAIN.value == "UNCERTAIN"


def test_satellite_validation_result_defaults() -> None:
    result = SatelliteValidationResult(
        input_point=FirePointInput(latitude=10.0, longitude=20.0),
        verdict=Verdict.UNCERTAIN,
        final_confidence=0.5,
    )
    assert result.reasons == []
    assert result.summary == ""
    assert result.processing_time_ms == 0.0
    assert result.coordinate_correction is None
    assert result.landcover is None
    assert result.false_positive is None
    assert result.environmental is None
    assert result.confidence_breakdown is None
