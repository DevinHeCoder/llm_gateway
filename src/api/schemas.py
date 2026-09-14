"""
API 请求/响应模型（Pydantic）。

与 OpenAI API 兼容，便于直接替换 OpenAI 客户端使用。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------- 聊天相关 ----------------

class ChatMessage(BaseModel):
    """对话消息。"""
    role: str = Field(..., description="消息角色：system / user / assistant")
    content: str = Field(..., description="消息内容")


class ChatCompletionRequest(BaseModel):
    """聊天补全请求（OpenAI 兼容格式）。"""
    model: Optional[str] = Field(None, description="模型名称")
    messages: List[ChatMessage] = Field(..., description="对话消息列表")
    temperature: Optional[float] = Field(None, description="采样温度", ge=0, le=2)
    max_tokens: Optional[int] = Field(None, description="最大生成 token 数", ge=1)
    top_p: Optional[float] = Field(None, description="核采样参数", ge=0, le=1)
    stream: bool = Field(False, description="是否流式响应")
    user: Optional[str] = Field(None, description="用户标识（用于限流和统计）")

    model_config = {"extra": "allow"}  # 允许额外参数透传


class UsageInfo(BaseModel):
    """Token 使用统计。"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatChoice(BaseModel):
    """聊天补全选择。"""
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    """聊天补全响应（OpenAI 兼容格式）。"""
    id: str = ""
    object: str = "chat.completion"
    created: int = 0
    model: str = ""
    choices: List[ChatChoice]
    usage: UsageInfo
    # 网关扩展字段
    gateway: Optional[Dict[str, Any]] = Field(None, description="网关统计信息")


class ChatCompletionChunk(BaseModel):
    """流式聊天补全片段（OpenAI 兼容 SSE 格式）。"""
    id: str = ""
    object: str = "chat.completion.chunk"
    created: int = 0
    model: str = ""
    choices: List[Dict[str, Any]]


# ---------------- 系统相关 ----------------

class HealthResponse(BaseModel):
    """健康检查响应。"""
    status: str = "ok"
    app: str = ""
    version: str = ""


class SystemInfoResponse(BaseModel):
    """系统信息响应。"""
    app: str = ""
    version: str = ""
    model_provider: str = ""
    rate_limiter_provider: str = ""
    cache_provider: str = ""
    concurrency_provider: str = ""
    monitor_provider: str = ""
    gateway_stats: Dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """错误响应。"""
    error: Dict[str, Any]
