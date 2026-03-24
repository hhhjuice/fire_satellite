"""Generate human-readable Chinese verdict reasons and summary — satellite context.

No historical fire references (ground-only). Includes brightness/FRP bonus reasons.
"""
from typing import Optional

from app.api.schemas import (
    ConfidenceBreakdown,
    CoordinateCorrection,
    EnvironmentalResult,
    FalsePositiveResult,
    LandCoverResult,
    Verdict,
)


def generate_reasons(
    verdict: Verdict,
    confidence: float,
    landcover: Optional[LandCoverResult] = None,
    false_positive: Optional[FalsePositiveResult] = None,
    environmental: Optional[EnvironmentalResult] = None,
    coordinate_correction: Optional[CoordinateCorrection] = None,
    brightness: Optional[float] = None,
    frp: Optional[float] = None,
) -> list[str]:
    """Generate list of Chinese reason strings explaining the satellite verdict."""
    reasons: list[str] = []

    # Land cover reason
    if landcover is not None:
        if landcover.likelihood_ratio >= 2.0:
            reasons.append(f"地物类型为{landcover.class_name}，属于高火灾风险区域")
        elif landcover.likelihood_ratio >= 1.0:
            reasons.append(f"地物类型为{landcover.class_name}，火灾风险适中")
        elif landcover.likelihood_ratio >= 0.1:
            reasons.append(f"地物类型为{landcover.class_name}，火灾可能性较低")
        else:
            reasons.append(f"地物类型为{landcover.class_name}，该区域极不可能发生火灾")

    # False positive reasons
    if false_positive is not None:
        triggered = [f for f in false_positive.flags if f.triggered]
        if triggered:
            for flag in triggered:
                reasons.append(flag.detail)
        else:
            reasons.append("未检测到假阳性特征")

    # Environmental reason
    if environmental is not None:
        reasons.append(environmental.detail)

    # Brightness bonus reason
    if brightness is not None and brightness > 340.0:
        reasons.append(f"亮温{brightness:.1f}K，高亮温增强火点置信度")

    # FRP bonus reason
    if frp is not None and frp > 20.0:
        reasons.append(f"火辐射功率{frp:.1f}MW，高FRP增强火点置信度")

    # Coordinate correction reason
    if coordinate_correction is not None and coordinate_correction.correction_applied:
        reasons.append(coordinate_correction.reason)

    return reasons


def generate_summary(
    verdict: Verdict,
    confidence: float,
    landcover: Optional[LandCoverResult] = None,
    false_positive: Optional[FalsePositiveResult] = None,
) -> str:
    """Generate a one-paragraph Chinese summary of the satellite validation verdict."""
    verdict_text = {
        Verdict.TRUE_FIRE: "判定为真实火点",
        Verdict.FALSE_POSITIVE: "判定为假阳性",
        Verdict.UNCERTAIN: "判定结果待确认",
    }

    parts: list[str] = []
    parts.append(f"星上分析{verdict_text.get(verdict, '未知')}，最终置信度{confidence:.1%}。")

    if landcover is not None:
        parts.append(f"该位置地物类型为{landcover.class_name}（火灾似然比{landcover.likelihood_ratio}）。")

    if false_positive is not None and false_positive.is_likely_false_positive:
        triggered_names = [f.detector for f in false_positive.flags if f.triggered]
        parts.append(f"假阳性检测器触发: {', '.join(triggered_names)}，总惩罚{false_positive.total_penalty:.1f}。")

    return "".join(parts)
