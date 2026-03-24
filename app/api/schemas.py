"""Pydantic schemas for the satellite fire validation system.

No TIF fields. Output includes all data needed by the ground system.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    """Fire point validation verdict."""
    TRUE_FIRE = "TRUE_FIRE"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    UNCERTAIN = "UNCERTAIN"


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

class FirePointInput(BaseModel):
    """Single fire point input from satellite sensor. No TIF fields."""
    latitude: float = Field(..., ge=-90, le=90, description="纬度")
    longitude: float = Field(..., ge=-180, le=180, description="经度")
    satellite: Optional[str] = Field(None, description="卫星来源 (e.g. MODIS, VIIRS)")
    brightness: Optional[float] = Field(None, description="亮温值 (K)")
    frp: Optional[float] = Field(None, ge=0, description="火辐射功率 (MW)")
    confidence: Optional[float] = Field(None, ge=0, le=100, description="卫星原始置信度 (0-100)")
    acquisition_time: Optional[datetime] = Field(None, description="观测时间 (UTC)")


class ValidateRequest(BaseModel):
    """Request to validate one or more fire points. No TIF fields."""
    points: list[FirePointInput] = Field(..., min_length=1, description="火点列表")


# ---------------------------------------------------------------------------
# Sub-results
# ---------------------------------------------------------------------------

class LandCoverResult(BaseModel):
    """Land cover analysis result for a fire point."""
    class_code: int = Field(..., description="ESA WorldCover 地物编码")
    class_name: str = Field(..., description="地物类型名称")
    likelihood_ratio: float = Field(..., description="地物火灾似然比")
    description: str = Field("", description="地物类型描述")


class FalsePositiveFlag(BaseModel):
    """A single false positive detection flag."""
    detector: str = Field(..., description="检测器名称")
    triggered: bool = Field(..., description="是否触发")
    penalty: float = Field(0.0, ge=0, description="置信度惩罚值")
    detail: str = Field("", description="检测细节")


class FalsePositiveResult(BaseModel):
    """Combined false positive detection results."""
    flags: list[FalsePositiveFlag] = Field(default_factory=list, description="各检测器结果")
    total_penalty: float = Field(0.0, ge=0, description="总惩罚值")
    is_likely_false_positive: bool = Field(False, description="是否可能为假阳性")


class EnvironmentalResult(BaseModel):
    """Environmental factor analysis result."""
    is_daytime: bool = Field(..., description="是否为白天")
    solar_zenith_angle: float = Field(..., description="太阳天顶角 (度)")
    fire_season_factor: float = Field(..., description="火灾季节因子")
    env_score: float = Field(0.0, description="环境综合评分")
    detail: str = Field("", description="环境因素详情")


class CoordinateCorrection(BaseModel):
    """Coordinate correction result."""
    original_lat: float = Field(..., description="原始纬度")
    original_lon: float = Field(..., description="原始经度")
    corrected_lat: float = Field(..., description="修正纬度")
    corrected_lon: float = Field(..., description="修正经度")
    offset_m: float = Field(0.0, ge=0, description="修正偏移量 (m)")
    correction_applied: bool = Field(False, description="是否进行了修正")
    reason: str = Field("", description="修正原因")


class ConfidenceBreakdown(BaseModel):
    """Detailed breakdown of confidence score calculation."""
    initial_confidence: float = Field(0.5, description="初始置信度")
    landcover_contribution: float = Field(0.0, description="地物类型贡献")
    environmental_contribution: float = Field(0.0, description="环境因素贡献")
    brightness_bonus: float = Field(0.0, description="亮温加成")
    frp_bonus: float = Field(0.0, description="FRP加成")
    false_positive_penalty: float = Field(0.0, description="假阳性惩罚")
    final_confidence: float = Field(0.0, ge=0, le=1, description="最终置信度")


# ---------------------------------------------------------------------------
# Output (this is what gets downlinked to the ground system)
# ---------------------------------------------------------------------------

class SatelliteValidationResult(BaseModel):
    """Complete satellite validation result for a single fire point.

    This schema is the output of the satellite system and the input to the
    ground enhancement system.
    """
    input_point: FirePointInput = Field(..., description="输入火点")

    verdict: Verdict = Field(..., description="判定结果")
    final_confidence: float = Field(..., ge=0, le=1, description="最终置信度")
    reasons: list[str] = Field(default_factory=list, description="判断原因列表")
    summary: str = Field("", description="综合判断摘要")

    coordinate_correction: Optional[CoordinateCorrection] = Field(None, description="坐标修正结果")
    landcover: Optional[LandCoverResult] = Field(None, description="地物分析结果")
    false_positive: Optional[FalsePositiveResult] = Field(None, description="假阳性检测结果")
    environmental: Optional[EnvironmentalResult] = Field(None, description="环境因素分析")
    confidence_breakdown: Optional[ConfidenceBreakdown] = Field(None, description="置信度分解")

    processing_time_ms: float = Field(0.0, ge=0, description="处理耗时 (毫秒)")


class ValidateResponse(BaseModel):
    """Response for fire point validation request."""
    results: list[SatelliteValidationResult] = Field(..., description="验证结果列表")
    total_points: int = Field(..., ge=0, description="总火点数")
    true_fire_count: int = Field(0, ge=0, description="真火点数")
    false_positive_count: int = Field(0, ge=0, description="假阳性数")
    uncertain_count: int = Field(0, ge=0, description="待确认数")
    total_processing_time_ms: float = Field(0.0, ge=0, description="总处理耗时 (毫秒)")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field("ok", description="服务状态")
    version: str = Field("1.0.0", description="版本号")
