"""
Redis 分布式限流器：基于 Redis 令牌桶脚本实现，支持多实例共享限流状态。

使用 Lua 脚本保证原子性，适合网关多副本部署场景。
"""
from __future__ import annotations

import time
from typing import Optional

try:
    import redis
except ImportError:
    redis = None  # type: ignore

from src.common.exceptions import ConfigError
from src.rate_limiter.base import RateLimiter
from src.rate_limiter.registry import rate_limiter_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.rate_limiter.redis")

# Lua 脚本：令牌桶原子操作
_TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = now - last_refill
tokens = math.min(capacity, tokens + elapsed * rate)

if tokens >= requested then
    tokens = tokens - requested
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return 1
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return 0
end
"""


@rate_limiter_registry.register("redis")
class RedisRateLimiter(RateLimiter):
    """Redis 分布式令牌桶限流器。

    参数:
        provider: 实现名
        requests_per_second: 令牌填充速率
        burst_size: 桶容量
        redis_url: Redis 连接地址
        key_prefix: 限流键前缀
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "redis",
        requests_per_second: float = 10.0,
        burst_size: int = 20,
        redis_url: str = "redis://localhost:6379/1",
        key_prefix: str = "gateway:rate_limit",
        **kwargs,
    ) -> None:
        if redis is None:
            raise ConfigError("redis 包未安装，请执行 pip install redis")

        self.rate = float(requests_per_second)
        self.capacity = float(burst_size)
        self.key_prefix = key_prefix
        self._client = redis.from_url(redis_url)
        self._script = self._client.register_script(_TOKEN_BUCKET_SCRIPT)
        logger.info(
            "RedisRateLimiter 初始化: rate=%.2f/s, capacity=%d, prefix=%s",
            self.rate, self.capacity, self.key_prefix,
        )

    def _make_key(self, key: Optional[str]) -> str:
        suffix = key or "global"
        return f"{self.key_prefix}:{suffix}"

    def allow(self, key: Optional[str] = None) -> bool:
        redis_key = self._make_key(key)
        now = time.time()
        try:
            result = self._script(
                keys=[redis_key],
                args=[self.rate, self.capacity, now, 1],
            )
            return bool(result)
        except Exception as e:
            logger.warning("Redis 限流检查失败，放行请求: %s", e)
            return True  # Redis 故障时放行，避免雪崩

    def acquire(self, key: Optional[str] = None, timeout: float = 0) -> bool:
        if timeout <= 0:
            return self.allow(key)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.allow(key):
                return True
            time.sleep(0.05)
        return False

    def reset(self, key: Optional[str] = None) -> None:
        redis_key = self._make_key(key)
        try:
            self._client.delete(redis_key)
        except Exception as e:
            logger.warning("Redis 限流重置失败: %s", e)

    def remaining(self, key: Optional[str] = None) -> int:
        redis_key = self._make_key(key)
        try:
            data = self._client.hgetall(redis_key)
            if not data:
                return int(self.capacity)
            tokens = float(data.get(b"tokens", self.capacity))
            return int(max(0, tokens))
        except Exception as e:
            logger.warning("Redis 限流查询失败: %s", e)
            return int(self.capacity)
