"""
无并发控制实现：所有请求直接放行，用于开发测试或不需要并发限制的场景。
"""
from __future__ import annotations

from typing import Optional

from src.concurrency.base import ConcurrencyController
from src.concurrency.registry import concurrency_registry


@concurrency_registry.register("none")
class NoneController(ConcurrencyController):
    """无并发控制：不限制并发数。"""

    def __init__(self, **kwargs) -> None:
        pass

    def acquire(self, timeout: Optional[float] = None) -> bool:
        return True

    def release(self) -> None:
        pass

    def active_count(self) -> int:
        return 0

    def available(self) -> int:
        return 999999
