"""
FastAPI 依赖注入：提供 GatewayService 等共享实例。
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request

from src.api.service import GatewayService


def get_gateway_service(request: Request) -> GatewayService:
    """从应用状态获取 GatewayService 实例。"""
    service: Optional[GatewayService] = getattr(request.app.state, "service", None)
    if service is None:
        raise RuntimeError("GatewayService 未初始化")
    return service
