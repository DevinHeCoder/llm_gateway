"""
API 服务层：GatewayService 业务门面，组装各层组件并暴露给路由。

不依赖 HTTP 框架，便于单元测试。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from src.api.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatChoice,
    ChatMessage,
    HealthResponse,
    SystemInfoResponse,
    UsageInfo,
)
from src.cache import build_cache
from src.common.exceptions import GatewayError
from src.concurrency import build_concurrency_controller
from src.gateway import Gateway, GatewayRequest
from src.model_client import build_model_client
from src.model_manager import build_model_manager
from src.model_manager.base import ModelInfo
from src.monitor import build_monitor
from src.monitor.base import MetricsSummary, RequestRecord
from src.prompt_manager import build_prompt_manager
from src.prompt_manager.ab_testing import ABTestManager
from src.rate_limiter import build_rate_limiter
from src.utils.config_loader import load_config
from src.utils.logger import get_logger

logger = get_logger("gateway.api.service")


class GatewayService:
    """网关服务门面：组装各层组件，提供业务方法。"""

    def __init__(
        self,
        config: dict,
        gateway: Gateway,
        monitor=None,
        model_manager=None,
        prompt_manager=None,
        ab_test_manager=None,
    ) -> None:
        self.config = config
        self.gateway = gateway
        self.monitor = monitor
        self.model_manager = model_manager
        self.prompt_manager = prompt_manager
        self.ab_test_manager = ab_test_manager

    @classmethod
    def build_from_config(cls, config: Optional[dict] = None) -> "GatewayService":
        """按配置一次性组装全部层。"""
        cfg = config or load_config()

        model_client = build_model_client(cfg.get("model", {}))
        rate_limiter = build_rate_limiter(cfg.get("rate_limit", {}))
        cache = build_cache(cfg.get("cache", {}))
        concurrency = build_concurrency_controller(cfg.get("concurrency", {}))
        monitor = build_monitor(cfg.get("monitor", {}))
        model_manager = build_model_manager(cfg.get("model_manager", {}))
        prompt_manager = build_prompt_manager(cfg.get("prompt_manager", {}))
        ab_test_manager = ABTestManager()

        gateway = Gateway(
            model_client=model_client,
            rate_limiter=rate_limiter,
            cache=cache,
            concurrency=concurrency,
            monitor=monitor,
            config=cfg.get("gateway", {}),
        )

        logger.info("GatewayService 组装完成")
        return cls(
            cfg, gateway,
            monitor=monitor,
            model_manager=model_manager,
            prompt_manager=prompt_manager,
            ab_test_manager=ab_test_manager,
        )

    # ---------------- 聊天补全 ----------------

    def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """处理聊天补全请求（非流式）。

        监控埋点已在 Gateway 内部完成（覆盖 success/cached/error/rate_limited 全场景），
        service 层不再重复记录。
        """
        request_id = f"chatcmpl-{int(time.time() * 1000)}"

        gateway_request = GatewayRequest(
            messages=[ChatMessage(role=m.role, content=m.content) for m in request.messages],
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            top_p=request.top_p,
            stream=False,
            user=request.user,
            extra=request.model_extra or {},
        )

        result = self.gateway.process(gateway_request)
        resp = result.response

        return ChatCompletionResponse(
            id=request_id,
            created=int(time.time()),
            model=resp.model,
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=resp.content),
                    finish_reason=resp.finish_reason,
                )
            ],
            usage=UsageInfo(
                prompt_tokens=resp.usage.prompt_tokens,
                completion_tokens=resp.usage.completion_tokens,
                total_tokens=resp.usage.total_tokens,
            ),
            gateway={
                "from_cache": result.from_cache,
                "latency_ms": round(result.latency_ms, 2),
                "inference_latency_ms": round(result.inference_latency_ms, 2),
                "cache_latency_ms": round(result.cache_latency_ms, 2),
            },
        )

    async def stream_chat_completion(self, request: ChatCompletionRequest):
        """处理流式聊天补全请求（异步生成器）。

        流式请求的监控埋点已在 Gateway.stream_process() 内部完成。
        此处负责：SSE chunk 封装 + 异常兜底 + CancelledError 清理。
        """
        gateway_request = GatewayRequest(
            messages=[ChatMessage(role=m.role, content=m.content) for m in request.messages],
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            top_p=request.top_p,
            stream=True,
            user=request.user,
            extra=request.model_extra or {},
        )

        chunk_id = f"chatcmpl-{int(time.time() * 1000)}"
        created = int(time.time())
        model = request.model or self.config.get("model", {}).get("default_model", "")

        try:
            async for content in self.gateway.stream_process(gateway_request):
                chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": content},
                            "finish_reason": None,
                        }
                    ],
                }
                yield chunk

            yield {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }

        except asyncio.CancelledError:
            logger.info("流式请求被取消: user=%s, model=%s", request.user, model)
            yield {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            raise

        except Exception as e:
            logger.error("流式请求异常: %s", e)
            raise

    # ---------------- 模型管理 ----------------

    def list_models(self) -> List[ModelInfo]:
        """列出所有模型。"""
        if self.model_manager is None:
            return []
        return self.model_manager.list_models()

    def get_model(self, name: str) -> Optional[ModelInfo]:
        """获取指定模型信息。"""
        if self.model_manager is None:
            return None
        return self.model_manager.get_model(name)

    def load_model(self, name: str) -> bool:
        """加载模型。"""
        if self.model_manager is None:
            return False
        return self.model_manager.load_model(name)

    def unload_model(self, name: str) -> bool:
        """卸载模型。"""
        if self.model_manager is None:
            return False
        return self.model_manager.unload_model(name)

    def switch_model(self, name: str) -> bool:
        """切换激活模型。"""
        if self.model_manager is None:
            return False
        return self.model_manager.switch_model(name)

    def get_active_model(self) -> Optional[ModelInfo]:
        """获取当前激活模型。"""
        if self.model_manager is None:
            return None
        return self.model_manager.get_active_model()

    # ---------------- 监控统计 ----------------

    def get_metrics(self, *, model: Optional[str] = None, last_seconds: int = 0) -> MetricsSummary:
        """获取监控指标。"""
        if self.monitor is None:
            return MetricsSummary()
        return self.monitor.get_metrics(model=model, last_seconds=last_seconds)

    def get_recent_records(self, limit: int = 100) -> List[RequestRecord]:
        """获取最近请求记录。"""
        if self.monitor is None:
            return []
        return self.monitor.get_recent_records(limit)

    # ---------------- 系统 ----------------

    def health(self) -> HealthResponse:
        """健康检查。"""
        app_cfg = self.config.get("app", {})
        return HealthResponse(
            status="ok",
            app=app_cfg.get("name", "llm_gateway"),
            version=app_cfg.get("version", "0.0.0"),
        )

    def system_info(self) -> SystemInfoResponse:
        """系统信息。"""
        app_cfg = self.config.get("app", {})
        return SystemInfoResponse(
            app=app_cfg.get("name", "llm_gateway"),
            version=app_cfg.get("version", "0.0.0"),
            model_provider=self.config.get("model", {}).get("provider", "unknown"),
            rate_limiter_provider=self.config.get("rate_limit", {}).get("provider", "unknown"),
            cache_provider=self.config.get("cache", {}).get("provider", "unknown"),
            concurrency_provider=self.config.get("concurrency", {}).get("provider", "unknown"),
            monitor_provider=self.config.get("monitor", {}).get("provider", "unknown"),
            gateway_stats=self.gateway.stats,
        )

    def close(self) -> None:
        """释放所有资源。"""
        self.gateway.close()
        logger.info("GatewayService 已关闭")