"""
Prometheus 监控导出器：将统计指标以 Prometheus 格式导出。

基于 prometheus_client 库，提供 /metrics 端点供 Prometheus 抓取。
适合生产环境多实例部署场景。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
except ImportError:
    Counter = Histogram = Gauge = None  # type: ignore
    generate_latest = None  # type: ignore
    CONTENT_TYPE_LATEST = "text/plain"

from src.common.exceptions import ConfigError
from src.monitor.base import MetricsSummary, Monitor, RequestRecord
from src.monitor.registry import monitor_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.monitor.prometheus")


@monitor_registry.register("prometheus")
class PrometheusMonitor(Monitor):
    """Prometheus 监控导出器。

    参数:
        provider: 实现名
        retention_seconds: 记录保留窗口（用于 get_metrics）
        error_rate_threshold: 错误率告警阈值
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "prometheus",
        retention_seconds: int = 86400,
        error_rate_threshold: float = 0.05,
        **kwargs,
    ) -> None:
        if Counter is None:
            raise ConfigError("prometheus_client 未安装，请执行 pip install prometheus-client")

        self.retention_seconds = retention_seconds
        self.error_rate_threshold = error_rate_threshold

        # 定义 Prometheus 指标
        self.requests_total = Counter(
            "gateway_requests_total",
            "Total number of requests",
            ["model", "status", "user"],
        )
        self.tokens_total = Counter(
            "gateway_tokens_total",
            "Total number of tokens",
            ["model", "type"],  # type: prompt / completion
        )
        self.request_duration = Histogram(
            "gateway_request_duration_seconds",
            "Request duration in seconds",
            ["model"],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
        )
        self.inference_duration = Histogram(
            "gateway_inference_duration_seconds",
            "Inference duration in seconds",
            ["model"],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
        )
        self.cache_hits_total = Counter(
            "gateway_cache_hits_total",
            "Total number of cache hits",
            ["model"],
        )
        self.active_requests = Gauge(
            "gateway_active_requests",
            "Number of active requests",
        )

        # 内存记录（用于 get_metrics）
        self._records: List[RequestRecord] = []
        self._records_lock = __import__("threading").Lock()

        logger.info("PrometheusMonitor 初始化完成")

    def record(self, record: RequestRecord) -> None:
        if record.timestamp == 0:
            record.timestamp = time.time()

        model = record.model or "unknown"
        user = record.user or "anonymous"

        # 更新 Prometheus 指标
        self.requests_total.labels(model=model, status=record.status, user=user).inc()
        self.tokens_total.labels(model=model, type="prompt").inc(record.prompt_tokens)
        self.tokens_total.labels(model=model, type="completion").inc(record.completion_tokens)

        if record.latency_ms > 0:
            self.request_duration.labels(model=model).observe(record.latency_ms / 1000)
        if record.inference_latency_ms > 0:
            self.inference_duration.labels(model=model).observe(record.inference_latency_ms / 1000)
        if record.from_cache:
            self.cache_hits_total.labels(model=model).inc()

        # 内存记录
        with self._records_lock:
            self._records.append(record)
            # 清理过期记录
            cutoff = time.time() - self.retention_seconds
            self._records = [r for r in self._records if r.timestamp >= cutoff]

    def get_metrics(
        self,
        *,
        model: Optional[str] = None,
        last_seconds: int = 0,
    ) -> MetricsSummary:
        """从内存记录计算统计（Prometheus 指标通过 /metrics 端点导出）。"""
        with self._records_lock:
            records = list(self._records)

        now = time.time()
        if last_seconds > 0:
            cutoff = now - last_seconds
            records = [r for r in records if r.timestamp >= cutoff]
        if model:
            records = [r for r in records if r.model == model]

        if not records:
            return MetricsSummary()

        total = len(records)
        success = sum(1 for r in records if r.status == "success")
        errors = sum(1 for r in records if r.status == "error")
        cache_hits = sum(1 for r in records if r.from_cache)

        latencies = sorted(r.latency_ms for r in records if r.latency_ms > 0)

        def percentile(data: List[float], p: float) -> float:
            if not data:
                return 0.0
            k = (len(data) - 1) * p
            f = int(k)
            c = min(f + 1, len(data) - 1)
            return data[f] if f == c else data[f] + (data[c] - data[f]) * (k - f)

        return MetricsSummary(
            total_requests=total,
            success_count=success,
            error_count=errors,
            cache_hits=cache_hits,
            cache_hit_rate=round(cache_hits / total, 4),
            error_rate=round(errors / total, 4),
            avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0,
            p50_latency_ms=round(percentile(latencies, 0.5), 2),
            p95_latency_ms=round(percentile(latencies, 0.95), 2),
            p99_latency_ms=round(percentile(latencies, 0.99), 2),
            total_prompt_tokens=sum(r.prompt_tokens for r in records),
            total_completion_tokens=sum(r.completion_tokens for r in records),
            total_tokens=sum(r.total_tokens for r in records),
        )

    def get_recent_records(self, limit: int = 100) -> List[RequestRecord]:
        with self._records_lock:
            return self._records[-limit:]

    def clear(self) -> None:
        with self._records_lock:
            self._records.clear()
        logger.info("Prometheus 监控统计已清空")

    def generate_latest_metrics(self) -> bytes:
        """生成 Prometheus 格式的最新指标数据。"""
        if generate_latest is not None:
            return generate_latest()
        return b""
