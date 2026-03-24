"""FastAPI route definitions for satellite fire point validation API."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    HealthResponse,
    ValidateRequest,
    ValidateResponse,
)
from app.core.pipeline import validate_batch

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/validate", response_model=ValidateResponse, summary="星上验证火点")
async def validate_fire_points(request: ValidateRequest) -> ValidateResponse:
    """接收火点列表并返回星上验证结果。"""
    try:
        response = await validate_batch(request.points)
    except Exception as exc:
        logger.exception("Pipeline error")
        raise HTTPException(status_code=500, detail=f"星上验证流程异常: {exc}") from exc

    return response


@router.get("/api/health", response_model=HealthResponse, summary="健康检查")
async def health_check() -> HealthResponse:
    """返回星上验证服务状态。"""
    return HealthResponse(status="ok", version="1.0.0")
