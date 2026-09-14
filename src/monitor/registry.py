"""monitor 层的可插拔注册表实例。"""
from src.common.registry import Registry
from src.monitor.base import Monitor

monitor_registry = Registry(
    name="monitor",
    base_type=Monitor,
    default="file_metrics",
)
