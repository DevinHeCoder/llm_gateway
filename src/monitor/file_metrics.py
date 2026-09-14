"""
文件/内存监控：进程内实现，基于 deque 存储请求记录，支持时间窗口统计。

适合单实例部署、监控需求简单的场景。记录保留在内存中，可配置保留窗口。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

from src.monitor.base import MetricsSummary, Monitor, RequestRecord
from src.monitor.registry import monitor_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.monitor.file_metrics")


@monitor_registry.register("file_metrics")
class FileMetricsMonitor(Monitor):
    """内存监控（进程内）。

    参数:
        provider: 实现名
        retention_seconds: 记录保留窗口（秒）
        error_rate_threshold: 错误率告警阈值
        alert_webhook: 告警 webhook URL（为空则仅日志告警）
        max_records: 最大记录数
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "file_metrics",
        retention_seconds: int = 86400,
        error_rate_threshold: float = 0.05,
        alert_webhook: str = "",
        max_records: int = 10000,
        **kwargs,
    ) -> None:
        self.retention_seconds = retention_seconds
        self.error_rate_threshold = error_rate_threshold
        self.alert_webhook = alert_webhook
        self._records: deque[RequestRecord] = deque(maxlen=max_records)
        self._lock = threading.Lock()
        self._last_alert_time = 0.0
        logger.info(
            "FileMetricsMonitor 初始化: retention=%ds, threshold=%.2f",
            retention_seconds, error_rate_threshold,
        )

    def _cleanup(self) -> None:
        """移除超过保留窗口的记录。"""
        cutoff = time.time() - self.retention_seconds
        while self._records and self._records[0].timestamp < cutoff:
            self._records.popleft()

    def _check_alert(self, records: List[RequestRecord]) -> None:
        """检查错误率是否超过阈值，触发告警。"""
        if not records:
            return
        total = len(records)
        errors = sum(1 for r in records if r.status == "error")
        error_rate = errors / total if total > 0 else 0

        if error_rate >= self.error_rate_threshold and total >= 10:
            now = time.time()
            # 告警冷却：1 分钟内不重复告警
            if now - self._last_alert_time > 60:
                self._last_alert_time = now
                msg = (
                    f"[告警] 错误率超过阈值: {error_rate:.2%} "
                    f"(阈值 {self.error_rate_threshold:.2%}), "
                    f"最近 {total} 个请求中 {errors} 个错误"
                )
                logger.error(msg)
                if self.alert_webhook:
                    try:
                        import httpx
                        httpx.post(self.alert_webhook, json={"message": msg}, timeout=5)
                    except Exception as e:
                        logger.warning("告警 webhook 发送失败: %s", e)

    def record(self, record: RequestRecord) -> None:
        if record.timestamp == 0:
            record.timestamp = time.time()
        with self._lock:
            self._records.append(record)
            self._cleanup()

        # 异步检查告警（简化：同步检查最近 100 条）
        recent = list(self._records)[-100:]
        self._check_alert(recent)

    def get_metrics(
        self,
        *,
        model: Optional[str] = None,
        last_seconds: int = 0,
    ) -> MetricsSummary:
        with self._lock:
            records = list(self._records)

        # 过滤
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
        rate_limited = sum(1 for r in records if r.status == "rate_limited")
        cache_hits = sum(1 for r in records if r.from_cache)

        latencies = sorted(r.latency_ms for r in records if r.latency_ms > 0)
        prompt_tokens = [r.prompt_tokens for r in records]
        completion_tokens = [r.completion_tokens for r in records]

        def percentile(data: List[float], p: float) -> float:
            if not data:
                return 0.0
            k = (len(data) - 1) * p
            f = int(k)
            c = min(f + 1, len(data) - 1)
            if f == c:
                return data[f]
            return data[f] + (data[c] - data[f]) * (k - f)

        # 按模型分组
        by_model: Dict[str, Dict[str, Any]] = {}
        for r in records:
            m = r.model or "unknown"
            if m not in by_model:
                by_model[m] = {"count": 0, "total_tokens": 0, "avg_latency": 0.0, "errors": 0}
            by_model[m]["count"] += 1
            by_model[m]["total_tokens"] += r.total_tokens
            by_model[m]["avg_latency"] += r.latency_ms
            if r.status == "error":
                by_model[m]["errors"] += 1
        for m in by_model:
            by_model[m]["avg_latency"] = round(by_model[m]["avg_latency"] / by_model[m]["count"], 2)
            by_model[m]["error_rate"] = round(by_model[m]["errors"] / by_model[m]["count"], 4)

        # 按状态分组
        by_status: Dict[str, int] = {}
        for r in records:
            by_status[r.status] = by_status.get(r.status, 0) + 1

        return MetricsSummary(
            total_requests=total,
            success_count=success,
            error_count=errors,
            rate_limited_count=rate_limited,
            cache_hits=cache_hits,
            cache_hit_rate=round(cache_hits / total, 4) if total > 0 else 0,
            error_rate=round(errors / total, 4) if total > 0 else 0,
            avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0,
            p50_latency_ms=round(percentile(latencies, 0.5), 2),
            p95_latency_ms=round(percentile(latencies, 0.95), 2),
            p99_latency_ms=round(percentile(latencies, 0.99), 2),
            total_prompt_tokens=sum(prompt_tokens),
            total_completion_tokens=sum(completion_tokens),
            total_tokens=sum(r.total_tokens for r in records),
            avg_prompt_tokens=round(sum(prompt_tokens) / total, 2) if total > 0 else 0,
            avg_completion_tokens=round(sum(completion_tokens) / total, 2) if total > 0 else 0,
            by_model=by_model,
            by_status=by_status,
        )

    def get_recent_records(self, limit: int = 100) -> List[RequestRecord]:
        with self._lock:
            return list(self._records)[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
        logger.info("监控统计已清空")
