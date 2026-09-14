"""concurrency 层的可插拔注册表实例。"""
from src.common.registry import Registry
from src.concurrency.base import ConcurrencyController

concurrency_registry = Registry(
    name="concurrency",
    base_type=ConcurrencyController,
    default="semaphore",
)
