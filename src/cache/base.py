"""
缓存抽象基类。

所有缓存实现统一接口：get() / set() / delete() / clear()。
缓存值为序列化后的模型响应（JSON 字符串）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class Cache(ABC):
    """缓存统一接口。"""

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """获取缓存值。

        参数:
            key: 缓存键

        返回:
            缓存值（JSON 字符串），未命中返回 None
        """
        pass

    @abstractmethod
    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """设置缓存值。

        参数:
            key: 缓存键
            value: 缓存值（JSON 字符串）
            ttl: 过期时间（秒），为空时使用默认 TTL

        返回:
            True 表示成功
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除缓存键。"""
        pass

    @abstractmethod
    def clear(self) -> int:
        """清空所有缓存，返回删除的条目数。"""
        pass

    @abstractmethod
    def size(self) -> int:
        """获取当前缓存条目数。"""
        pass
