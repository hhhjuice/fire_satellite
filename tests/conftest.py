"""Shared test fixtures for satellite fire validation tests."""
import os

import pytest

from app.api.schemas import (
    FalsePositiveFlag,
    FalsePositiveResult,
    LandCoverResult,
)

# Ensure test env doesn't use real data paths
os.environ.setdefault("SAT_WORLDCOVER_DIR", "/tmp/test_worldcover")


@pytest.fixture
def grassland_result() -> LandCoverResult:
    return LandCoverResult(class_code=30, class_name="草地", likelihood_ratio=3.0)


@pytest.fixture
def water_result() -> LandCoverResult:
    return LandCoverResult(class_code=80, class_name="水体", likelihood_ratio=0.01)


@pytest.fixture
def water_flag_result() -> FalsePositiveResult:
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
