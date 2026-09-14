"""
ModelClient 推理客户端测试。
"""
from __future__ import annotations

import pytest

from src.model_client import ChatMessage, MockClient, build_model_client
from src.model_client.registry import model_client_registry


class TestMockClient:
    """Mock 客户端测试。"""

    def test_chat_returns_response(self):
        """测试 chat 返回响应。"""
        client = MockClient(response_delay=0)
        messages = [
            ChatMessage(role="user", content="你好"),
        ]
        response = client.chat(messages)
        assert response.content is not None
        assert len(response.content) > 0
        assert response.model == "mock-model"
        assert response.usage.total_tokens > 0

    def test_chat_with_model(self):
        """测试指定模型名称。"""
        client = MockClient(response_delay=0)
        messages = [ChatMessage(role="user", content="test")]
        response = client.chat(messages, model="custom-model")
        assert response.model == "custom-model"

    def test_fixed_response(self):
        """测试固定响应。"""
        client = MockClient(response_delay=0, fixed_response="固定回复内容")
        messages = [ChatMessage(role="user", content="anything")]
        response = client.chat(messages)
        assert response.content == "固定回复内容"

    def test_multiple_requests(self):
        """测试多次请求。"""
        client = MockClient(response_delay=0)
        messages = [ChatMessage(role="user", content="test")]
        r1 = client.chat(messages)
        r2 = client.chat(messages)
        assert r1 is not None
        assert r2 is not None

    def test_stream_chat(self):
        """测试流式聊天。"""
        import asyncio
        client = MockClient(response_delay=0.001)
        messages = [ChatMessage(role="user", content="test")]

        async def _run():
            chunks = []
            async for chunk in client.stream_chat(messages):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_run())
        assert len(chunks) > 0
        full_content = "".join(chunks)
        assert len(full_content) > 0

    def test_health(self):
        """测试健康检查。"""
        import asyncio
        client = MockClient()
        healthy = asyncio.run(client.health())
        assert healthy is True


class TestBuildModelClient:
    """build_model_client 工厂函数测试。"""

    def test_build_mock(self):
        """测试构建 Mock 客户端。"""
        config = {"provider": "mock", "response_delay": 0}
        client = build_model_client(config)
        assert isinstance(client, MockClient)

    def test_default_provider(self):
        """测试默认 provider。"""
        config = {}
        client = build_model_client(config)
        assert isinstance(client, MockClient)

    def test_registry_has_mock(self):
        """测试注册表包含 mock 实现。"""
        assert model_client_registry.has("mock")
