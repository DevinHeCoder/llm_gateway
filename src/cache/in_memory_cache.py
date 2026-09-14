"""
内存 LRU 缓存：进程内实现，基于 OrderedDict 的 LRU 淘汰策略。

适合单实例部署、缓存量不大的场景。多实例部署时各实例缓存不共享。
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Optional

from src.cache.base import Cache
from src.cache.registry import cache_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.cache.in_memory")


@cache_registry.register("in_memory")
class InMemoryCache(Cache):
    """内存 LRU 缓存。

    参数:
        provider: 实现名
        ttl_seconds: 默认过期时间（秒）
        max_entries: 最大缓存条目数
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "in_memory",
        ttl_seconds: int = 3600,
        max_entries: int = 1000,
        **kwargs,
    ) -> None:
        self.default_ttl = ttl_seconds
        self.max_entries = max_entries
        self._store: OrderedDict[str, tuple[str, float]] = OrderedDict()  # key -> (value, expire_at)
        self._lock = threading.Lock()
        logger.info(
            "InMemoryCache 初始化: ttl=%ds, max_entries=%d",
            self.default_ttl, self.max_entries,
        )

    def _is_expired(self, expire_at: float) -> bool:
        return expire_at > 0 and time.monotonic() > expire_at

    def _evict_if_needed(self) -> None:
        """LRU 淘汰：超过最大条目数时删除最久未使用的。"""
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expire_at = item
            if self._is_expired(expire_at):
                del self._store[key]
                return None
            # 移动到末尾（最近使用）
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        ttl = ttl if ttl is not None else self.default_ttl
        expire_at = time.monotonic() + ttl if ttl > 0 else 0
        with self._lock:
            self._store[key] = (value, expire_at)
            self._store.move_to_end(key)
            self._evict_if_needed()
        return True

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> int:
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    def size(self) -> int:
        with self._lock:
            # 清理过期条目
            now = time.monotonic()
            expired = [k for k, (_, exp) in self._store.items() if exp > 0 and now > exp]
            for k in expired:
                del self._store[k]
            return len(self._store)
