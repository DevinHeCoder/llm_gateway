"""
缓存层测试。
"""
from __future__ import annotations

import time

import pytest

from src.cache import InMemoryCache, NoneCache, build_cache, make_cache_key
from src.model_client import ChatMessage


class TestInMemoryCache:
    """内存缓存测试。"""

    def test_set_and_get(self):
        """测试设置和获取。"""
        cache = InMemoryCache(ttl_seconds=60, max_entries=100)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing(self):
        """测试获取不存在的键。"""
        cache = InMemoryCache()
        assert cache.get("nonexistent") is None

    def test_delete(self):
        """测试删除。"""
        cache = InMemoryCache()
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None

    def test_delete_missing(self):
        """测试删除不存在的键。"""
        cache = InMemoryCache()
        assert cache.delete("nonexistent") is False

    def test_ttl_expiry(self):
        """测试 TTL 过期。"""
        cache = InMemoryCache(ttl_seconds=0.1)
        cache.set("key1", "value1", ttl=0.1)
        assert cache.get("key1") == "value1"
        time.sleep(0.15)
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        """测试 LRU 淘汰。"""
        cache = InMemoryCache(max_entries=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        # 访问 key1，使其成为最近使用
        cache.get("key1")
        # 添加 key4，应淘汰最久未使用的 key2
        cache.set("key4", "value4")
        assert cache.get("key2") is None
        assert cache.get("key1") == "value1"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_size(self):
        """测试缓存大小。"""
        cache = InMemoryCache()
        assert cache.size() == 0
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        assert cache.size() == 2

    def test_clear(self):
        """测试清空。"""
        cache = InMemoryCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cleared = cache.clear()
        assert cleared == 2
        assert cache.size() == 0


class TestNoneCache:
    """无缓存测试。"""

    def test_get_always_none(self):
        """测试 get 始终返回 None。"""
        cache = NoneCache()
        cache.set("key1", "value1")
        assert cache.get("key1") is None

    def test_size_always_zero(self):
        """测试 size 始终为 0。"""
        cache = NoneCache()
        assert cache.size() == 0


class TestMakeCacheKey:
    """缓存键生成测试。"""

    def test_deterministic(self):
        """测试相同输入生成相同键。"""
        messages = [ChatMessage(role="user", content="hello")]
        key1 = make_cache_key("model1", messages, temperature=0.7)
        key2 = make_cache_key("model1", messages, temperature=0.7)
        assert key1 == key2

    def test_different_model(self):
        """测试不同模型生成不同键。"""
        messages = [ChatMessage(role="user", content="hello")]
        key1 = make_cache_key("model1", messages)
        key2 = make_cache_key("model2", messages)
        assert key1 != key2

    def test_different_messages(self):
        """测试不同消息生成不同键。"""
        m1 = [ChatMessage(role="user", content="hello")]
        m2 = [ChatMessage(role="user", content="world")]
        key1 = make_cache_key("model", m1)
        key2 = make_cache_key("model", m2)
        assert key1 != key2

    def test_different_params(self):
        """测试不同参数生成不同键。"""
        messages = [ChatMessage(role="user", content="hello")]
        key1 = make_cache_key("model", messages, temperature=0.7)
        key2 = make_cache_key("model", messages, temperature=0.9)
        assert key1 != key2


class TestBuildCache:
    """build_cache 工厂函数测试。"""

    def test_build_in_memory(self):
        """测试构建内存缓存。"""
        config = {"provider": "in_memory", "ttl_seconds": 60, "max_entries": 100}
        cache = build_cache(config)
        assert isinstance(cache, InMemoryCache)

    def test_build_none(self):
        """测试构建无缓存。"""
        config = {"provider": "none"}
        cache = build_cache(config)
        assert isinstance(cache, NoneCache)

    def test_default_provider(self):
        """测试默认 provider。"""
        config = {}
        cache = build_cache(config)
        assert isinstance(cache, NoneCache)
