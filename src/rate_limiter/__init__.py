"""限流层：统一限流接口，支持令牌桶、滑动窗口、Redis 分布式限流等多种算法。"""
from src.rate_limiter.base import RateLimiter
from src.rate_limiter.none_limiter import NoneLimiter
from src.rate_limiter.registry import rate_limiter_registry
from src.rate_limiter.sliding_window import SlidingWindowLimiter
from src.rate_limiter.token_bucket import TokenBucketLimiter
from src.rate_limiter import token_bucket  # noqa: F401
from src.rate_limiter import sliding_window  # noqa: F401
from src.rate_limiter import redis_limiter  # noqa: F401
from src.rate_limiter import none_limiter  # noqa: F401


def build_rate_limiter(config: dict) -> RateLimiter:
    """按配置创建限流器实例。"""
    provider = config.get("provider", "token_bucket")
    return rate_limiter_registry.create(provider, **config)
