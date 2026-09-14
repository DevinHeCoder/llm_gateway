"""
Mock 推理客户端：无真实推理服务时用于开发、测试和演示。

返回预设的模拟响应，支持配置延迟和自定义响应内容，驱动全链路测试。
"""
from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, List, Optional

from src.model_client.base import ChatMessage, ModelClient, ModelResponse, UsageInfo
from src.model_client.registry import model_client_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.model_client.mock")


@model_client_registry.register("mock")
class MockClient(ModelClient):
    """Mock 推理客户端。

    参数:
        provider: 实现名（注册用）
        default_model: 默认模型名称
        response_delay: 模拟响应延迟（秒）
        fixed_response: 固定响应文本；为空时根据输入生成模拟回复
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "mock",
        default_model: str = "mock-model",
        response_delay: float = 0.1,
        fixed_response: str = "",
        **kwargs,
    ) -> None:
        self.default_model = default_model
        self.response_delay = response_delay
        self.fixed_response = fixed_response
        self._request_count = 0
        logger.info("MockClient 初始化: default_model=%s", self.default_model)

    def _generate_response(self, messages: List[ChatMessage], model: str) -> ModelResponse:
        self._request_count += 1

        if self.fixed_response:
            content = self.fixed_response
        else:
            # 根据最后一条用户消息生成模拟回复
            last_user = ""
            for m in reversed(messages):
                if m.role == "user":
                    last_user = m.content
                    break
            content = (
                f"[Mock 响应 #{self._request_count}] 收到你的消息：{last_user[:100]}\n\n"
                f"这是一个模拟回复，当前使用模型：{model}。"
                f"共处理 {len(messages)} 条消息。"
            )

        # 模拟 token 统计
        prompt_tokens = sum(len(m.content) // 4 for m in messages)
        completion_tokens = len(content) // 4

        return ModelResponse(
            content=content,
            model=model,
            usage=UsageInfo(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            finish_reason="stop",
            raw={"mock": True, "request_id": self._request_count},
        )

    def chat(
        self,
        messages: List[ChatMessage],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        **kwargs,
    ) -> ModelResponse:
        model_name = model or self.default_model
        # 模拟延迟
        if self.response_delay > 0:
            time.sleep(self.response_delay)

        logger.debug(
            "Mock chat: model=%s, messages=%d, temp=%s",
            model_name, len(messages), temperature,
        )
        return self._generate_response(messages, model_name)

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        model_name = model or self.default_model
        response = self._generate_response(messages, model_name)

        # 模拟流式输出：按字符分段
        chunk_size = 10
        for i in range(0, len(response.content), chunk_size):
            if self.response_delay > 0:
                await asyncio.sleep(self.response_delay / 10)
            yield response.content[i:i + chunk_size]

    async def health(self) -> bool:
        """Mock 客户端始终健康。"""
        return True

    def close(self) -> None:
        """Mock 客户端无需释放资源。"""
        logger.info("MockClient 已关闭，共处理 %d 个请求", self._request_count)
