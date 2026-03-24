"""Tests for satellite reason generator."""
from app.api.schemas import FalsePositiveFlag, FalsePositiveResult, Verdict
from app.utils.reason_generator import generate_reasons, generate_summary


def test_generate_reasons_with_grassland_contains_expected_keywords(grassland_result) -> None:
    reasons = generate_reasons(
        verdict=Verdict.TRUE_FIRE,
        confidence=0.82,
        landcover=grassland_result,
    )
    joined = " ".join(reasons)
    assert "草地" in joined
    assert "高火灾风险" in joined


def test_generate_reasons_with_triggered_false_positive_contains_detail() -> None:
    fp = FalsePositiveResult(
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
    reasons = generate_reasons(
        verdict=Verdict.FALSE_POSITIVE,
        confidence=0.03,
        false_positive=fp,
    )
    assert any("水体" in reason for reason in reasons)


def test_generate_reasons_with_no_data_returns_empty() -> None:
    reasons = generate_reasons(
        verdict=Verdict.UNCERTAIN,
        confidence=0.5,
    )
    assert reasons == []


def test_generate_reasons_brightness_bonus() -> None:
    reasons = generate_reasons(
        verdict=Verdict.TRUE_FIRE,
        confidence=0.85,
        brightness=360.0,
    )
    assert any("亮温" in r for r in reasons)


def test_generate_reasons_frp_bonus() -> None:
    reasons = generate_reasons(
        verdict=Verdict.TRUE_FIRE,
        confidence=0.85,
        frp=30.0,
    )
    assert any("火辐射功率" in r or "FRP" in r for r in reasons)


def test_generate_summary_contains_verdict_and_confidence(grassland_result) -> None:
    summary = generate_summary(
        verdict=Verdict.TRUE_FIRE,
        confidence=0.82,
        landcover=grassland_result,
    )
    assert "判定为真实火点" in summary
    assert "82.0%" in summary
    assert "星上" in summary
