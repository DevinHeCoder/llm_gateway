"""
无限流实现：所有请求直接放行，用于开发测试或不需要限流的场景。
"""
from __future__ import annotations

from typing import Optional

from src.rate_limiter.base import RateLimiter
from src.rate_limiter.registry import rate_limiter_registry


@rate_limiter_registry.register("none")
class NoneLimiter(RateLimiter):
    """无限流器：所有请求直接放行。"""

    def __init__(self, **kwargs) -> None:
        pass

    def allow(self, key: Optional[str] = None) -> bool:
        return True

    def acquire(self, key: Optional[str] = None, timeout: float = 0) -> bool:
        return True

    def reset(self, key: Optional[str] = None) -> None:
        pass

    def remaining(self, key: Optional[str] = None) -> int:
        return 999999
