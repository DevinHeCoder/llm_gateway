"""
令牌桶限流器：进程内实现，支持突发流量。

令牌以固定速率填充到桶中，桶有最大容量。每个请求消耗一个令牌，
桶空时触发限流。适合允许一定突发流量的场景。
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Optional

from src.rate_limiter.base import RateLimiter
from src.rate_limiter.registry import rate_limiter_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.rate_limiter.token_bucket")


class _Bucket:
    """单个令牌桶状态。"""

    __slots__ = ("tokens", "last_refill", "lock")

    def __init__(self, capacity: float) -> None:
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()


@rate_limiter_registry.register("token_bucket")
class TokenBucketLimiter(RateLimiter):
    """令牌桶限流器（进程内）。

    参数:
        provider: 实现名
        requests_per_second: 令牌填充速率（每秒请求数）
        burst_size: 桶容量（最大突发请求数）
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "token_bucket",
        requests_per_second: float = 10.0,
        burst_size: int = 20,
        **kwargs,
    ) -> None:
        self.rate = float(requests_per_second)
        self.capacity = float(burst_size)
        self._buckets: Dict[str, _Bucket] = {}
        self._global_bucket = _Bucket(self.capacity)
        self._lock = threading.Lock()
        logger.info(
            "TokenBucketLimiter 初始化: rate=%.2f/s, capacity=%d",
            self.rate, self.capacity,
        )

    def _get_bucket(self, key: Optional[str]) -> _Bucket:
        if key is None:
            return self._global_bucket
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(self.capacity)
                self._buckets[key] = bucket
            return bucket

    def _refill(self, bucket: _Bucket) -> None:
        """填充令牌。"""
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        if elapsed > 0:
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.rate)
            bucket.last_refill = now

    def allow(self, key: Optional[str] = None) -> bool:
        bucket = self._get_bucket(key)
        with bucket.lock:
            self._refill(bucket)
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True
            return False

    def acquire(self, key: Optional[str] = None, timeout: float = 0) -> bool:
        if timeout <= 0:
            return self.allow(key)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.allow(key):
                return True
            # 计算需要等待的时间
            bucket = self._get_bucket(key)
            with bucket.lock:
                self._refill(bucket)
                wait_time = max(0.001, (1.0 - bucket.tokens) / self.rate)
            time.sleep(min(wait_time, 0.1))
        return False

    def reset(self, key: Optional[str] = None) -> None:
        bucket = self._get_bucket(key)
        with bucket.lock:
            bucket.tokens = self.capacity
            bucket.last_refill = time.monotonic()

    def remaining(self, key: Optional[str] = None) -> int:
        bucket = self._get_bucket(key)
        with bucket.lock:
            self._refill(bucket)
            return int(bucket.tokens)
