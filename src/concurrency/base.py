"""
并发控制抽象基类。

所有并发控制器实现统一接口：acquire() 获取许可，release() 释放许可。
用于限制同时进行的推理请求数，防止 vLLM 服务过载。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Iterator, Optional


class ConcurrencyController(ABC):
    """并发控制器统一接口。"""

    @abstractmethod
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """获取并发许可。

        参数:
            timeout: 最大等待时间（秒），None 表示使用默认超时，0 表示不等待

        返回:
            True 表示获得许可，False 表示超时或被拒绝
        """
        pass

    @abstractmethod
    def release(self) -> None:
        """释放并发许可。"""
        pass

    @abstractmethod
    def active_count(self) -> int:
        """当前活跃请求数。"""
        pass

    @abstractmethod
    def available(self) -> int:
        """当前可用许可数。"""
        pass

    @contextmanager
    def guard(self, timeout: Optional[float] = None) -> Iterator[bool]:
        """上下文管理器：自动获取和释放许可。

        用法::

            with controller.guard(timeout=5) as acquired:
                if not acquired:
                    raise ConcurrencyError("并发超时")
                # 执行推理请求
        """
        acquired = self.acquire(timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self.release()
