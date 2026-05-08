"""FastAPI route definitions for satellite fire point validation API."""
from __future__ import annotations

import logging
import asyncio

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    HealthResponse,
    ValidateRequest,
    ValidateResponse,
)
from app.core.pipeline import validate_batch
from app.data.worldcover import check_worldcover_readiness

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/validate", response_model=ValidateResponse, summary="星上验证火点")
async def validate_fire_points(request: ValidateRequest) -> ValidateResponse:
    """接收火点列表并返回星上验证结果。"""
    try:
        response = await validate_batch(request.points)
    except Exception as exc:
        logger.exception("Pipeline error")
        raise HTTPException(status_code=500, detail="星上验证流程异常，请查看服务端日志") from exc

    return response


@router.get("/api/health", response_model=HealthResponse, summary="健康检查")
async def health_check() -> HealthResponse:
    """返回星上验证服务状态。"""
    return HealthResponse(status="ok", version="1.0.0", services={"pipeline": True})


@router.get("/api/health/ready", response_model=HealthResponse, summary="就绪检查")
async def readiness_check() -> HealthResponse:
    """检查星上服务关键本地数据依赖是否可用。"""
    report = await asyncio.to_thread(check_worldcover_readiness)
    details = report["details"]
    response = HealthResponse(
        status="ok" if report["ready"] else "degraded",
        version="1.0.0",
        services={"worldcover": bool(report["ready"])},
        details={
            "required_tile_count": len(details.get("required_tiles", [])),
            "missing_tile_count": len(details.get("missing_tiles", [])),
        },
    )
    if not report["ready"]:
        logger.warning(
            "WorldCover readiness failed: error=%s missing_tile_count=%d exception=%s",
            details.get("error", "unknown"),
            len(details.get("missing_tiles", [])),
            details.get("exception", ""),
        )
        raise HTTPException(status_code=503, detail="WorldCover data unavailable")
    return response
