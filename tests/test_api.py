"""
API 层测试。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.service import GatewayService


@pytest.fixture
def test_client():
    """测试用 FastAPI 客户端。"""
    config = {
        "app": {"name": "test_gateway", "version": "0.1.0"},
        "logging": {"config_path": None},
        "model": {
            "provider": "mock",
            "default_model": "test-model",
            "response_delay": 0.001,
        },
        "rate_limit": {
            "provider": "token_bucket",
            "requests_per_second": 100,
            "burst_size": 100,
        },
        "cache": {"provider": "in_memory", "ttl_seconds": 60, "max_entries": 100},
        "concurrency": {"provider": "semaphore", "max_concurrent": 10, "queue_timeout": 5},
        "monitor": {"provider": "file_metrics", "retention_seconds": 3600},
        "model_manager": {"provider": "local", "models": []},
        "prompt_manager": {"provider": "memory"},
        "gateway": {"enable_cache": True, "enable_monitor": True},
        "server": {"host": "0.0.0.0", "port": 9000},
    }
    service = GatewayService.build_from_config(config)
    app = create_app(config=config, service=service)
    client = TestClient(app)
    yield client
    service.close()


class TestHealthEndpoint:
    """健康检查端点测试。"""

    def test_health(self, test_client):
        """测试 /health 端点。"""
        resp = test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["app"] == "test_gateway"
        assert data["version"] == "0.1.0"


class TestSystemInfoEndpoint:
    """系统信息端点测试。"""

    def test_system_info(self, test_client):
        """测试 /system/info 端点。"""
        resp = test_client.get("/system/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["app"] == "test_gateway"
        assert data["model_provider"] == "mock"
        assert data["rate_limiter_provider"] == "token_bucket"
        assert data["cache_provider"] == "in_memory"
        assert data["concurrency_provider"] == "semaphore"


class TestChatCompletionEndpoint:
    """聊天补全端点测试。"""

    def test_non_stream_chat(self, test_client):
        """测试非流式聊天补全。"""
        payload = {
            "model": "test-model",
            "messages": [
                {"role": "system", "content": "你是一个助手。"},
                {"role": "user", "content": "你好"},
            ],
            "temperature": 0.7,
            "max_tokens": 100,
            "user": "test_user",
        }
        resp = test_client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert data["model"] == "test-model"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert len(data["choices"][0]["message"]["content"]) > 0
        assert "usage" in data
        assert "gateway" in data

    def test_stream_chat(self, test_client):
        """测试流式聊天补全。"""
        payload = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "写一首诗"}],
            "stream": True,
            "user": "test_user",
        }
        with test_client.stream("POST", "/v1/chat/completions", json=payload) as resp:
            assert resp.status_code == 200
            lines = list(resp.iter_lines())
            # 应该有 data: 开头的行
            data_lines = [l for l in lines if l and l.startswith("data: ")]
            assert len(data_lines) > 0
            # 最后一行应该是 [DONE]
            assert data_lines[-1] == "data: [DONE]"

    def test_missing_messages(self, test_client):
        """测试缺少 messages 参数。"""
        payload = {"model": "test-model"}
        resp = test_client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 422  # Pydantic 校验错误


class TestMetricsEndpoint:
    """监控指标端点测试。"""

    def test_metrics_summary(self, test_client):
        """测试 /metrics/summary 端点。"""
        # 先发送一个请求
        test_client.post("/v1/chat/completions", json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "test"}],
        })
        resp = test_client.get("/metrics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] >= 1
        assert "avg_latency_ms" in data
        assert "p50_latency_ms" in data
        assert "p95_latency_ms" in data


class TestModelsEndpoint:
    """模型管理端点测试。"""

    def test_list_models(self, test_client):
        """测试 /v1/models 端点。"""
        resp = test_client.get("/v1/models")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
