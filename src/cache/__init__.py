"""缓存层：统一缓存接口，支持 Redis、内存 LRU 等多种后端。"""
from src.cache.base import Cache
from src.cache.in_memory_cache import InMemoryCache
from src.cache.none_cache import NoneCache
from src.cache.redis_cache import RedisCache
from src.cache.registry import cache_registry
from src.cache import redis_cache  # noqa: F401
from src.cache import in_memory_cache  # noqa: F401
from src.cache import none_cache  # noqa: F401


def build_cache(config: dict) -> Cache:
    """按配置创建缓存实例。"""
    provider = config.get("provider", "none")
    return cache_registry.create(provider, **config)


def make_cache_key(model: str, messages: list, **kwargs) -> str:
    """根据请求参数生成缓存键。

    缓存键 = hash(model + messages + 生成参数)，确保相同请求命中缓存。
    """
    import hashlib
    import json

    payload = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages] if hasattr(messages[0], "role") else messages,
        "params": {k: v for k, v in sorted(kwargs.items()) if v is not None},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
