"""rate_limiter 层的可插拔注册表实例。"""
from src.common.registry import Registry
from src.rate_limiter.base import RateLimiter

rate_limiter_registry = Registry(
    name="rate_limiter",
    base_type=RateLimiter,
    default="token_bucket",
)
