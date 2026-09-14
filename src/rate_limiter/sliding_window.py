"""
滑动窗口限流器：进程内实现，基于时间窗口计数。

记录每个时间窗口内的请求数，滑动计算最近窗口内的请求总数。
比令牌桶更精确，但不支持突发流量（窗口内请求数严格受限）。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from src.rate_limiter.base import RateLimiter
from src.rate_limiter.registry import rate_limiter_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.rate_limiter.sliding_window")


class _WindowState:
    """单个限流键的窗口状态。"""

    __slots__ = ("requests", "lock")

    def __init__(self) -> None:
        self.requests: Deque[float] = deque()
        self.lock = threading.Lock()


@rate_limiter_registry.register("sliding_window")
class SlidingWindowLimiter(RateLimiter):
    """滑动窗口限流器（进程内）。

    参数:
        provider: 实现名
        requests_per_second: 每秒允许的请求数
        burst_size: 窗口大小（秒），默认 1 秒
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "sliding_window",
        requests_per_second: float = 10.0,
        burst_size: int = 1,
        **kwargs,
    ) -> None:
        self.max_requests = int(requests_per_second * burst_size)
        self.window_seconds = float(burst_size)
        self._states: Dict[str, _WindowState] = {}
        self._global_state = _WindowState()
        self._lock = threading.Lock()
        logger.info(
            "SlidingWindowLimiter 初始化: max=%d per %.1fs",
            self.max_requests, self.window_seconds,
        )

    def _get_state(self, key: Optional[str]) -> _WindowState:
        if key is None:
            return self._global_state
        with self._lock:
            state = self._states.get(key)
            if state is None:
                state = _WindowState()
                self._states[key] = state
            return state

    def _cleanup(self, state: _WindowState, now: float) -> None:
        """移除窗口外的请求记录。"""
        cutoff = now - self.window_seconds
        while state.requests and state.requests[0] < cutoff:
            state.requests.popleft()

    def allow(self, key: Optional[str] = None) -> bool:
        state = self._get_state(key)
        now = time.monotonic()
        with state.lock:
            self._cleanup(state, now)
            if len(state.requests) < self.max_requests:
                state.requests.append(now)
                return True
            return False

    def acquire(self, key: Optional[str] = None, timeout: float = 0) -> bool:
        if timeout <= 0:
            return self.allow(key)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.allow(key):
                return True
            # 计算最早请求过期时间
            state = self._get_state(key)
            with state.lock:
                if state.requests:
                    wait_until = state.requests[0] + self.window_seconds
                    wait_time = max(0.001, wait_until - time.monotonic())
                else:
                    wait_time = 0.01
            time.sleep(min(wait_time, 0.1))
        return False

    def reset(self, key: Optional[str] = None) -> None:
        state = self._get_state(key)
        with state.lock:
            state.requests.clear()

    def remaining(self, key: Optional[str] = None) -> int:
        state = self._get_state(key)
        now = time.monotonic()
        with state.lock:
            self._cleanup(state, now)
            return max(0, self.max_requests - len(state.requests))
