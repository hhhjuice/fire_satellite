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
    confidence: Optional[float] = Field(None, ge=0, le=100, description="卫星原始置信度 (0-100)")
    acquisition_time: Optional[datetime] = Field(None, description="观测时间 (UTC)")
    fire_pixel: Optional[int] = Field(None, ge=1, description="火点像素大小（像素数）")


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
    initial_confidence: float = Field(50.0, description="初始置信度 (0-100)")
    landcover_contribution: float = Field(0.0, description="地物类型贡献 (logit 空间)")
    environmental_contribution: float = Field(0.0, description="环境因素贡献 (logit 空间)")
    false_positive_penalty: float = Field(0.0, description="假阳性惩罚 (logit 空间)")
    final_confidence: float = Field(0.0, ge=0, le=100, description="最终置信度 (0-100)")


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
    final_confidence: float = Field(..., ge=0, le=100, description="最终置信度 (0-100)")
    fire_area_m2: Optional[float] = Field(None, ge=0, description="火点估算面积 (m²)")
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


# ---------------------------------------------------------------------------
# Ground validation schemas (input contract for the ground enhancement system)
# ---------------------------------------------------------------------------

class FirmsMatchLevel(str, Enum):
    """FIRMS historical fire data spatial/temporal match level."""
    EXACT_MATCH = "EXACT_MATCH"               # Same 1km², same season (±1mo), ≤3yr
    NEARBY_SAME_SEASON = "NEARBY_SAME_SEASON"  # ≤5km, same season, ≤5yr
    REGIONAL = "REGIONAL"                      # ≤10km, any time
    NO_SEASON_RECORD = "NO_SEASON_RECORD"      # Fire season but no nearby record
    NO_HISTORY = "NO_HISTORY"                  # No record within 50km
    CONFIRMED_NONE = "CONFIRMED_NONE"          # Confirmed non-fire zone


class IndustrialProximity(str, Enum):
    """Nearest industrial heat-source proximity class."""
    WITHIN_500M = "WITHIN_500M"
    WITHIN_2KM = "WITHIN_2KM"
    WITHIN_5KM = "WITHIN_5KM"
    NONE = "NONE"                              # No facility within 10km


class FirmsResult(BaseModel):
    """FIRMS historical fire data match result (ground stage input)."""
    match_level: FirmsMatchLevel = Field(..., description="FIRMS 时空匹配等级")
    nearest_fire_km: Optional[float] = Field(None, ge=0, description="最近历史火点距离 (km)")
    nearest_fire_date: Optional[datetime] = Field(None, description="最近历史火点日期")
    detail: str = Field("", description="详情说明")


class IndustrialResult(BaseModel):
    """Industrial facility proximity detection result (ground stage input)."""
    proximity: IndustrialProximity = Field(..., description="最近工业设施距离等级")
    nearest_facility_m: Optional[float] = Field(None, ge=0, description="最近工业设施距离 (m)")
    facility_type: Optional[str] = Field(None, description="设施类型（电厂/钢铁厂/化工厂等）")
    is_gas_flare: bool = Field(False, description="是否为油气火炬（真实燃烧源，不施加惩罚）")
    detail: str = Field("", description="详情说明")


class GroundConfidenceBreakdown(BaseModel):
    """Breakdown of the ground-stage confidence calculation."""
    satellite_confidence: float = Field(..., description="星上验证输出置信度 (0-100)")
    firms_contribution: float = Field(0.0, description="FIRMS 贡献 (logit 空间)")
    industrial_contribution: float = Field(0.0, description="工业设施修正 (logit 空间)")
    final_confidence: float = Field(..., ge=0, le=100, description="最终置信度 (0-100)")


class GroundValidationResult(BaseModel):
    """Final ground-enhanced validation result for a single fire point.

    This is the authoritative output after both satellite and ground stages.
    Verdict uses thresholds 75/50 (same as satellite stage).
    """
    satellite_result: SatelliteValidationResult = Field(..., description="星上验证结果（输入）")
    verdict: Verdict = Field(..., description="最终判决（阈值 75/50）")
    final_confidence: float = Field(..., ge=0, le=100, description="最终置信度 (0-100)")
    firms: Optional[FirmsResult] = Field(None, description="FIRMS 历史数据结果")
    industrial: Optional[IndustrialResult] = Field(None, description="工业设施检测结果")
    confidence_breakdown: Optional[GroundConfidenceBreakdown] = Field(None, description="置信度分解")
    reasons: list[str] = Field(default_factory=list, description="判断原因列表")
    summary: str = Field("", description="综合判断摘要")
