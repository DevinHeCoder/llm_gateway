"""并发控制层：统一并发控制接口，支持信号量等多种策略。"""
from src.concurrency.base import ConcurrencyController
from src.concurrency.registry import concurrency_registry
from src.concurrency import semaphore_controller  # noqa: F401
from src.concurrency import none_controller  # noqa: F401


def build_concurrency_controller(config: dict) -> ConcurrencyController:
    """按配置创建并发控制器实例。"""
    provider = config.get("provider", "semaphore")
    return concurrency_registry.create(provider, **config)
