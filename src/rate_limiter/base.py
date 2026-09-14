"""
限流器抽象基类。

所有限流器实现统一接口：allow() 检查是否允许请求，acquire() 阻塞等待直到允许。
触发限流时抛出 RateLimitError，上层应返回 HTTP 429。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class RateLimiter(ABC):
    """限流器统一接口。"""

    @abstractmethod
    def allow(self, key: Optional[str] = None) -> bool:
        """检查是否允许请求通过（非阻塞）。

        参数:
            key: 限流键（如用户 ID、API Key），为空时使用全局限流

        返回:
            True 表示允许，False 表示触发限流
        """
        pass

    @abstractmethod
    def acquire(self, key: Optional[str] = None, timeout: float = 0) -> bool:
        """阻塞等待直到请求被允许或超时。

        参数:
            key: 限流键
            timeout: 最大等待时间（秒），0 表示不等待

        返回:
            True 表示获得许可，False 表示超时
        """
        pass

    @abstractmethod
    def reset(self, key: Optional[str] = None) -> None:
        """重置指定键的限流计数。"""
        pass

    @abstractmethod
    def remaining(self, key: Optional[str] = None) -> int:
        """获取当前剩余可用请求数。"""
        pass
