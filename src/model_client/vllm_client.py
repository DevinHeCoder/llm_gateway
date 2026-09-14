"""
vLLM 推理客户端：通过 OpenAI 兼容 HTTP API 调用独立部署的 vLLM 服务。

vLLM 本身是一个独立进程，提供 OpenAI 兼容的 /v1/chat/completions 端点。
本客户端通过 httpx 发起 HTTP 请求，支持同步和流式调用。
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Dict, List, Optional

import httpx

from src.common.exceptions import ModelClientError, ModelTimeoutError
from src.model_client.base import ChatMessage, ModelClient, ModelResponse, UsageInfo
from src.model_client.registry import model_client_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.model_client.vllm")


@model_client_registry.register("vllm_openai")
class VLLMClient(ModelClient):
    """vLLM OpenAI 兼容 API 客户端。

    参数:
        provider: 实现名（注册用，不参与逻辑）
        base_url: vLLM 服务地址，如 http://localhost:8000/v1
        api_key: API 密钥（vLLM 默认不需要，可为空）
        default_model: 默认模型名称
        timeout: 请求超时（秒）
        max_retries: 最大重试次数
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "vllm_openai",
        base_url: str = "http://localhost:8000/v1",
        api_key: str = "",
        default_model: str = "qwen2.5-7b-instruct",
        timeout: float = 60.0,
        max_retries: int = 2,
        **kwargs,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout
        self.max_retries = max_retries

        self._client = httpx.Client(timeout=timeout)
        self._async_client: Optional[httpx.AsyncClient] = None

        logger.info("VLLMClient 初始化: base_url=%s, default_model=%s", self.base_url, self.default_model)

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_payload(
        self,
        messages: List[ChatMessage],
        *,
        model: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        top_p: Optional[float],
        stream: bool = False,
        **kwargs,
    ) -> Dict:
        payload: Dict = {
            "model": model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if top_p is not None:
            payload["top_p"] = top_p
        # 透传额外参数
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v
        return payload

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
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(
            messages, model=model, temperature=temperature,
            max_tokens=max_tokens, top_p=top_p, stream=False, **kwargs,
        )

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                return self._parse_response(data)
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning("请求超时（第 %d/%d 次）: %s", attempt + 1, self.max_retries + 1, e)
            except httpx.HTTPStatusError as e:
                # 4xx 不重试
                if 400 <= e.response.status_code < 500:
                    raise ModelClientError(
                        f"vLLM API 错误 {e.response.status_code}: {e.response.text}"
                    ) from e
                last_error = e
                logger.warning("服务端错误（第 %d/%d 次）: %s", attempt + 1, self.max_retries + 1, e)
            except (httpx.HTTPError, json.JSONDecodeError) as e:
                last_error = e
                logger.warning("请求失败（第 %d/%d 次）: %s", attempt + 1, self.max_retries + 1, e)

        raise ModelTimeoutError(f"vLLM 请求失败，已重试 {self.max_retries} 次: {last_error}")

    def _parse_response(self, data: Dict) -> ModelResponse:
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            model = data.get("model", "")
            usage_data = data.get("usage", {})
            usage = UsageInfo(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )
            finish_reason = choice.get("finish_reason", "stop")
            return ModelResponse(
                content=content,
                model=model,
                usage=usage,
                finish_reason=finish_reason,
                raw=data,
            )
        except (KeyError, IndexError, TypeError) as e:
            raise ModelClientError(f"解析 vLLM 响应失败: {e}, raw={data}") from e

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
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(
            messages, model=model, temperature=temperature,
            max_tokens=max_tokens, top_p=top_p, stream=True, **kwargs,
        )

        client = self._get_async_client()
        try:
            async with client.stream("POST", url, json=payload, headers=self._headers()) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except httpx.TimeoutException as e:
            raise ModelTimeoutError(f"流式请求超时: {e}") from e
        except httpx.HTTPStatusError as e:
            raise ModelClientError(
                f"vLLM 流式 API 错误 {e.response.status_code}: {e.response.text}"
            ) from e

    async def health(self) -> bool:
        """检查 vLLM 服务健康状态。"""
        # vLLM 提供 /health 端点
        health_url = self.base_url.replace("/v1", "") + "/health"
        client = self._get_async_client()
        try:
            resp = await client.get(health_url, headers=self._headers())
            return resp.status_code == 200
        except Exception as e:
            logger.warning("健康检查失败: %s", e)
            return False

    def close(self) -> None:
        """释放 HTTP 连接资源。"""
        self._client.close()
        if self._async_client and not self._async_client.is_closed:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._async_client.aclose())
                else:
                    loop.run_until_complete(self._async_client.aclose())
            except Exception:
                pass
        logger.info("VLLMClient 已关闭")
