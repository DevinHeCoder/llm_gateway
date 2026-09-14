"""
信号量并发控制器：进程内实现，基于 threading.Semaphore。

限制同时进行的推理请求数，超过时排队等待，超时后拒绝。
适合单实例部署场景。
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from src.common.exceptions import ConcurrencyError
from src.concurrency.base import ConcurrencyController
from src.concurrency.registry import concurrency_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.concurrency.semaphore")


@concurrency_registry.register("semaphore")
class SemaphoreController(ConcurrencyController):
    """信号量并发控制器（进程内）。

    参数:
        provider: 实现名
        max_concurrent: 最大并发请求数
        queue_timeout: 默认排队等待超时（秒）
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "semaphore",
        max_concurrent: int = 5,
        queue_timeout: float = 30.0,
        **kwargs,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.default_timeout = queue_timeout
        self._semaphore = threading.Semaphore(max_concurrent)
        self._active = 0
        self._lock = threading.Lock()
        logger.info(
            "SemaphoreController 初始化: max_concurrent=%d, timeout=%.1fs",
            self.max_concurrent, self.default_timeout,
        )

    def acquire(self, timeout: Optional[float] = None) -> bool:
        wait_time = timeout if timeout is not None else self.default_timeout
        if wait_time <= 0:
            # 非阻塞尝试
            acquired = self._semaphore.acquire(blocking=False)
        else:
            acquired = self._semaphore.acquire(timeout=wait_time)

        if acquired:
            with self._lock:
                self._active += 1
            return True
        return False

    def release(self) -> None:
        with self._lock:
            if self._active > 0:
                self._active -= 1
        self._semaphore.release()

    def active_count(self) -> int:
        with self._lock:
            return self._active

    def available(self) -> int:
        with self._lock:
            return max(0, self.max_concurrent - self._active)
