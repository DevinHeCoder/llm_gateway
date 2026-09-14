"""
系统路由：健康检查、系统信息。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_gateway_service
from src.api.schemas import HealthResponse, SystemInfoResponse
from src.api.service import GatewayService

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def health(service: GatewayService = Depends(get_gateway_service)) -> HealthResponse:
    """健康检查端点，用于负载均衡和监控。"""
    return service.health()


@router.get("/system/info", response_model=SystemInfoResponse, summary="系统信息")
async def system_info(service: GatewayService = Depends(get_gateway_service)) -> SystemInfoResponse:
    """获取系统配置和运行统计信息。"""
    return service.system_info()
