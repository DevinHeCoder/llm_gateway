"""
Redis 缓存：分布式缓存，支持多实例共享。

适合网关多副本部署场景，所有实例共享同一份缓存。
"""
from __future__ import annotations

from typing import Optional

try:
    import redis
except ImportError:
    redis = None  # type: ignore

from src.common.exceptions import ConfigError
from src.cache.base import Cache
from src.cache.registry import cache_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.cache.redis")


@cache_registry.register("redis")
class RedisCache(Cache):
    """Redis 缓存。

    参数:
        provider: 实现名
        ttl_seconds: 默认过期时间（秒）
        redis_url: Redis 连接地址
        key_prefix: 缓存键前缀
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "redis",
        ttl_seconds: int = 3600,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "gateway:cache",
        **kwargs,
    ) -> None:
        if redis is None:
            raise ConfigError("redis 包未安装，请执行 pip install redis")

        self.default_ttl = ttl_seconds
        self.key_prefix = key_prefix
        self._client = redis.from_url(redis_url)
        logger.info(
            "RedisCache 初始化: ttl=%ds, prefix=%s",
            self.default_ttl, self.key_prefix,
        )

    def _make_key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def get(self, key: str) -> Optional[str]:
        try:
            value = self._client.get(self._make_key(key))
            if value is not None:
                return value.decode("utf-8") if isinstance(value, bytes) else value
            return None
        except Exception as e:
            logger.warning("Redis 缓存读取失败: %s", e)
            return None

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        ttl = ttl if ttl is not None else self.default_ttl
        try:
            redis_key = self._make_key(key)
            if ttl > 0:
                self._client.setex(redis_key, ttl, value)
            else:
                self._client.set(redis_key, value)
            return True
        except Exception as e:
            logger.warning("Redis 缓存写入失败: %s", e)
            return False

    def delete(self, key: str) -> bool:
        try:
            return bool(self._client.delete(self._make_key(key)))
        except Exception as e:
            logger.warning("Redis 缓存删除失败: %s", e)
            return False

    def clear(self) -> int:
        try:
            pattern = f"{self.key_prefix}:*"
            keys = list(self._client.scan_iter(match=pattern, count=100))
            if keys:
                return int(self._client.delete(*keys))
            return 0
        except Exception as e:
            logger.warning("Redis 缓存清空失败: %s", e)
            return 0

    def size(self) -> int:
        try:
            pattern = f"{self.key_prefix}:*"
            return sum(1 for _ in self._client.scan_iter(match=pattern, count=100))
        except Exception as e:
            logger.warning("Redis 缓存大小查询失败: %s", e)
            return 0
