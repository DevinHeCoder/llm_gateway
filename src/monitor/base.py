"""
监控统计抽象基类。

所有监控实现统一接口：record() 记录请求，get_metrics() 获取统计指标。
用于调用日志、耗时监控、token 统计、错误告警。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RequestRecord:
    """单次请求记录。

    属性:
        request_id: 请求 ID
        model: 模型名称
        user: 用户标识
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        total_tokens: 总 token 数
        latency_ms: 总耗时（毫秒）
        inference_latency_ms: 推理耗时（毫秒）
        status: 请求状态（success / error / rate_limited / cached）
        error_type: 错误类型（status=error 时）
        error_message: 错误信息
        from_cache: 是否来自缓存
        timestamp: 请求时间戳（Unix 秒）
        extra: 额外字段
    """

    request_id: str = ""
    model: str = ""
    user: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    inference_latency_ms: float = 0.0
    status: str = "success"  # success / error / rate_limited / cached
    error_type: str = ""
    error_message: str = ""
    from_cache: bool = False
    timestamp: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricsSummary:
    """统计指标汇总。"""

    total_requests: int = 0
    success_count: int = 0
    error_count: int = 0
    rate_limited_count: int = 0
    cache_hits: int = 0
    cache_hit_rate: float = 0.0
    error_rate: float = 0.0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    avg_prompt_tokens: float = 0.0
    avg_completion_tokens: float = 0.0
    by_model: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_status: Dict[str, int] = field(default_factory=dict)


class Monitor(ABC):
    """监控统计统一接口。"""

    @abstractmethod
    def record(self, record: RequestRecord) -> None:
        """记录一次请求。

        参数:
            record: 请求记录
        """
        pass

    @abstractmethod
    def get_metrics(self, *, model: Optional[str] = None, last_seconds: int = 0) -> MetricsSummary:
        """获取统计指标。

        参数:
            model: 按模型过滤，为空时统计全部
            last_seconds: 只统计最近 N 秒，0 表示全部

        返回:
            MetricsSummary 统计汇总
        """
        pass

    @abstractmethod
    def get_recent_records(self, limit: int = 100) -> List[RequestRecord]:
        """获取最近的请求记录。"""
        pass

    @abstractmethod
    def clear(self) -> None:
        """清空所有统计数据。"""
        pass
