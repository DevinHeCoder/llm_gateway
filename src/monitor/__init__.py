"""监控统计层：调用日志、耗时统计、token 统计、错误告警。"""
from src.monitor.base import Monitor, RequestRecord
from src.monitor.registry import monitor_registry
from src.monitor import file_metrics  # noqa: F401
from src.monitor import prometheus_exporter  # noqa: F401
from src.monitor import none_monitor  # noqa: F401


def build_monitor(config: dict) -> Monitor:
    """按配置创建监控实例。"""
    provider = config.get("provider", "file_metrics")
    return monitor_registry.create(provider, **config)
