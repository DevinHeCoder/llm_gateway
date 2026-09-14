"""
无监控实现：不记录任何统计，用于不需要监控的场景。
"""
from __future__ import annotations

from typing import List, Optional

from src.monitor.base import MetricsSummary, Monitor, RequestRecord
from src.monitor.registry import monitor_registry


@monitor_registry.register("none")
class NoneMonitor(Monitor):
    """无监控：不记录任何数据。"""

    def __init__(self, **kwargs) -> None:
        pass

    def record(self, record: RequestRecord) -> None:
        pass

    def get_metrics(self, *, model: Optional[str] = None, last_seconds: int = 0) -> MetricsSummary:
        return MetricsSummary()

    def get_recent_records(self, limit: int = 100) -> List[RequestRecord]:
        return []

    def clear(self) -> None:
        pass
