"""
推理客户端抽象基类：ChatMessage + ModelResponse + ModelClient。

上层（Gateway）只依赖 ModelClient 的 chat() / stream_chat()，可通过 Registry
无缝切换实现：真实场景用 vllm_client（vLLM OpenAI 兼容协议），开发/测试用
mock_client（无推理服务驱动全链路）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional


@dataclass
class ChatMessage:
    """对话消息（与大模型 API 对齐的通用形态）。

    属性:
        role: system / user / assistant / tool
        content: 消息文本
    """

    role: str
    content: str


@dataclass
class UsageInfo:
    """token 使用统计。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ModelResponse:
    """模型响应结果。

    属性:
        content: 生成的文本内容
        model: 实际使用的模型名称
        usage: token 使用统计
        finish_reason: 结束原因（stop / length / content_filter 等）
        raw: 原始响应（用于调试）
    """

    content: str
    model: str = ""
    usage: UsageInfo = field(default_factory=UsageInfo)
    finish_reason: str = "stop"
    raw: Optional[Dict] = None


class ModelClient(ABC):
    """大模型客户端统一接口。"""

    @abstractmethod
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
        """多轮对话，返回完整响应。

        参数:
            messages: 对话历史（含 system 指令）
            model: 模型名称，为空时使用默认模型
            temperature: 采样温度
            max_tokens: 最大生成 token 数
            top_p: 核采样参数
            **kwargs: 其他透传参数
        """
        pass

    @abstractmethod
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
        """流式对话，异步迭代输出文本片段。

        参数:
            同 chat()

        返回:
            异步迭代器，每次产出一个文本片段
        """
        pass

    @abstractmethod
    async def health(self) -> bool:
        """检查推理服务健康状态。"""
        pass

    @abstractmethod
    def close(self) -> None:
        """释放底层连接资源。"""
        pass
