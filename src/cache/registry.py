"""cache 层的可插拔注册表实例。"""
from src.common.registry import Registry
from src.cache.base import Cache

cache_registry = Registry(
    name="cache",
    base_type=Cache,
    default="none",
)
