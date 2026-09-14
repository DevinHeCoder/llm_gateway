"""
监控指标路由：统计指标查询、最近请求记录。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from src.api.dependencies import get_gateway_service
from src.api.service import GatewayService
from src.monitor.base import MetricsSummary, RequestRecord
from src.utils.logger import get_logger

logger = get_logger("gateway.api.routes.metrics")

router = APIRouter(prefix="/metrics", tags=["metrics"])


class RequestRecordOut(BaseModel):
    """请求记录输出。"""
    request_id: str = ""
    model: str = ""
    user: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    inference_latency_ms: float = 0.0
    status: str = "success"
    error_type: str = ""
    from_cache: bool = False
    timestamp: float = 0.0


def _record_to_out(record: RequestRecord) -> RequestRecordOut:
    return RequestRecordOut(
        request_id=record.request_id,
        model=record.model,
        user=record.user,
        prompt_tokens=record.prompt_tokens,
        completion_tokens=record.completion_tokens,
        total_tokens=record.total_tokens,
        latency_ms=record.latency_ms,
        inference_latency_ms=record.inference_latency_ms,
        status=record.status,
        error_type=record.error_type,
        from_cache=record.from_cache,
        timestamp=record.timestamp,
    )


@router.get("/summary", response_model=MetricsSummary, summary="获取统计指标汇总")
async def get_metrics_summary(
    model: Optional[str] = Query(None, description="按模型过滤"),
    last_seconds: int = Query(0, description="只统计最近 N 秒，0 表示全部"),
    service: GatewayService = Depends(get_gateway_service),
) -> MetricsSummary:
    """获取监控统计指标汇总。"""
    return service.get_metrics(model=model, last_seconds=last_seconds)


@router.get("/requests", response_model=List[RequestRecordOut], summary="获取最近请求记录")
async def get_recent_requests(
    limit: int = Query(100, ge=1, le=1000, description="返回记录数"),
    service: GatewayService = Depends(get_gateway_service),
) -> List[RequestRecordOut]:
    """获取最近的请求记录。"""
    records = service.get_recent_records(limit)
    return [_record_to_out(r) for r in records]


@router.get("/prometheus", summary="Prometheus 指标导出")
async def prometheus_metrics(service: GatewayService = Depends(get_gateway_service)) -> Any:
    """以 Prometheus 格式导出指标（需 monitor provider=prometheus）。"""
    monitor = service.monitor
    if monitor is None or not hasattr(monitor, "generate_latest_metrics"):
        return PlainTextResponse(
            content="# Prometheus metrics not available (monitor provider is not prometheus)\n",
            media_type="text/plain",
        )
    try:
        data = monitor.generate_latest_metrics()
        return PlainTextResponse(content=data, media_type="text/plain")
    except Exception as e:
        logger.error("Prometheus 指标导出失败: %s", e)
        return PlainTextResponse(content=f"# Error: {e}\n", media_type="text/plain")
