"""FastAPI application entry point for Satellite Fire Validation System.

Headless — no static files, no database, no CORS.
Designed to run on resource-constrained satellite hardware.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    logger.info("Starting Satellite Fire Validation System...")
    logger.info("System ready.")
    yield
    logger.info("Shutting down Satellite Fire Validation System.")


app = FastAPI(
    title="星上火点验证系统",
    description="卫星星上火点主判系统，基于本地GIS数据进行多维度分析和置信度评分",
    version="1.0.0",
    lifespan=lifespan,
)

# Include API router
app.include_router(router)
