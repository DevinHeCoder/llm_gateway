"""
pytest 配置和共享 fixture。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def sample_messages():
    """示例对话消息。"""
    from src.model_client import ChatMessage
    return [
        ChatMessage(role="system", content="你是一个 helpful 的助手。"),
        ChatMessage(role="user", content="你好"),
    ]


@pytest.fixture
def mock_config():
    """测试用配置。"""
    return {
        "app": {"name": "test_gateway", "version": "0.1.0"},
        "model": {
            "provider": "mock",
            "default_model": "test-model",
            "response_delay": 0.01,
        },
        "rate_limit": {
            "provider": "token_bucket",
            "requests_per_second": 100,
            "burst_size": 100,
        },
        "cache": {
            "provider": "in_memory",
            "ttl_seconds": 60,
            "max_entries": 100,
        },
        "concurrency": {
            "provider": "semaphore",
            "max_concurrent": 10,
            "queue_timeout": 5,
        },
        "gateway": {
            "enable_cache": True,
            "enable_monitor": True,
        },
    }


@pytest.fixture
def gateway(mock_config):
    """测试用 Gateway 实例。"""
    from src.cache import build_cache
    from src.concurrency import build_concurrency_controller
    from src.gateway import Gateway
    from src.model_client import build_model_client
    from src.rate_limiter import build_rate_limiter

    model_client = build_model_client(mock_config["model"])
    rate_limiter = build_rate_limiter(mock_config["rate_limit"])
    cache = build_cache(mock_config["cache"])
    concurrency = build_concurrency_controller(mock_config["concurrency"])

    gw = Gateway(
        model_client=model_client,
        rate_limiter=rate_limiter,
        cache=cache,
        concurrency=concurrency,
        config=mock_config["gateway"],
    )
    yield gw
    gw.close()
