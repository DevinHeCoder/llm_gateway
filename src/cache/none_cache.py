"""
无缓存实现：所有 get() 返回 None，set() 不存储，用于不需要缓存的场景。
"""
from __future__ import annotations

from typing import Optional

from src.cache.base import Cache
from src.cache.registry import cache_registry


@cache_registry.register("none")
class NoneCache(Cache):
    """无缓存：不存储任何数据。"""

    def __init__(self, **kwargs) -> None:
        pass

    def get(self, key: str) -> Optional[str]:
        return None

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        return True

    def delete(self, key: str) -> bool:
        return False

    def clear(self) -> int:
        return 0

    def size(self) -> int:
        return 0
