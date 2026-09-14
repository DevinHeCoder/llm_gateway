"""
限流层测试。
"""
from __future__ import annotations

import time

import pytest

from src.rate_limiter import (
    NoneLimiter,
    SlidingWindowLimiter,
    TokenBucketLimiter,
    build_rate_limiter,
)


class TestTokenBucketLimiter:
    """令牌桶限流器测试。"""

    def test_allow_initial(self):
        """测试初始状态允许请求。"""
        limiter = TokenBucketLimiter(requests_per_second=10, burst_size=5)
        assert limiter.allow() is True

    def test_burst_limit(self):
        """测试突发限制。"""
        limiter = TokenBucketLimiter(requests_per_second=10, burst_size=3)
        # 前 3 个应该允许
        assert limiter.allow() is True
        assert limiter.allow() is True
        assert limiter.allow() is True
        # 第 4 个应该被限流
        assert limiter.allow() is False

    def test_refill_over_time(self):
        """测试随时间填充令牌。"""
        limiter = TokenBucketLimiter(requests_per_second=100, burst_size=1)
        assert limiter.allow() is True
        assert limiter.allow() is False
        time.sleep(0.02)  # 等待填充
        assert limiter.allow() is True

    def test_remaining(self):
        """测试剩余令牌数。"""
        limiter = TokenBucketLimiter(requests_per_second=10, burst_size=5)
        assert limiter.remaining() == 5
        limiter.allow()
        assert limiter.remaining() == 4

    def test_reset(self):
        """测试重置。"""
        limiter = TokenBucketLimiter(requests_per_second=10, burst_size=3)
        limiter.allow()
        limiter.allow()
        limiter.allow()
        assert limiter.allow() is False
        limiter.reset()
        assert limiter.allow() is True

    def test_per_key_limit(self):
        """测试按 key 限流。"""
        limiter = TokenBucketLimiter(requests_per_second=10, burst_size=1)
        assert limiter.allow("user_a") is True
        assert limiter.allow("user_a") is False
        assert limiter.allow("user_b") is True  # 不同用户独立计数


class TestSlidingWindowLimiter:
    """滑动窗口限流器测试。"""

    def test_allow_initial(self):
        """测试初始状态允许请求。"""
        limiter = SlidingWindowLimiter(requests_per_second=10, burst_size=1)
        assert limiter.allow() is True

    def test_window_limit(self):
        """测试窗口内请求数限制。"""
        limiter = SlidingWindowLimiter(requests_per_second=3, burst_size=1)
        assert limiter.allow() is True
        assert limiter.allow() is True
        assert limiter.allow() is True
        assert limiter.allow() is False

    def test_remaining(self):
        """测试剩余请求数。"""
        limiter = SlidingWindowLimiter(requests_per_second=5, burst_size=1)
        assert limiter.remaining() == 5
        limiter.allow()
        assert limiter.remaining() == 4


class TestNoneLimiter:
    """无限流器测试。"""

    def test_always_allow(self):
        """测试始终允许。"""
        limiter = NoneLimiter()
        for _ in range(100):
            assert limiter.allow() is True

    def test_acquire_always_true(self):
        """测试 acquire 始终返回 True。"""
        limiter = NoneLimiter()
        assert limiter.acquire(timeout=0) is True


class TestBuildRateLimiter:
    """build_rate_limiter 工厂函数测试。"""

    def test_build_token_bucket(self):
        """测试构建令牌桶限流器。"""
        config = {"provider": "token_bucket", "requests_per_second": 10, "burst_size": 20}
        limiter = build_rate_limiter(config)
        assert isinstance(limiter, TokenBucketLimiter)

    def test_build_sliding_window(self):
        """测试构建滑动窗口限流器。"""
        config = {"provider": "sliding_window", "requests_per_second": 10}
        limiter = build_rate_limiter(config)
        assert isinstance(limiter, SlidingWindowLimiter)

    def test_build_none(self):
        """测试构建无限流器。"""
        config = {"provider": "none"}
        limiter = build_rate_limiter(config)
        assert isinstance(limiter, NoneLimiter)

    def test_default_provider(self):
        """测试默认 provider。"""
        config = {}
        limiter = build_rate_limiter(config)
        assert isinstance(limiter, TokenBucketLimiter)
