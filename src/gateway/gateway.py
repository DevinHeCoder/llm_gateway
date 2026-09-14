"""
网关核心编排类：串联 限流 → 缓存 → 并发控制 → 推理调用 → 监控埋点 → 响应。

这是网关的核心业务逻辑，不依赖 HTTP 框架，便于单元测试和复用。
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.cache import make_cache_key
from src.cache.base import Cache
from src.common.exceptions import (
    ConcurrencyError,
    GatewayError,
    RateLimitError,
)
from src.concurrency import ConcurrencyController
from src.model_client import ChatMessage, ModelClient, ModelResponse, UsageInfo
from src.monitor.base import Monitor, RequestRecord
from src.rate_limiter import RateLimiter
from src.utils.logger import get_logger

logger = get_logger("gateway.core")


@dataclass
class GatewayRequest:
    """网关请求参数。

    属性:
        messages: 对话消息列表
        model: 模型名称，为空时使用默认模型
        temperature: 采样温度
        max_tokens: 最大生成 token 数
        top_p: 核采样参数
        stream: 是否流式响应
        user: 用户标识（用于限流键）
        extra: 额外透传参数
    """

    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stream: bool = False
    user: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayResult:
    """网关响应结果。

    属性:
        response: 模型响应
        from_cache: 是否来自缓存
        latency_ms: 总耗时（毫秒）
        cache_latency_ms: 缓存查询耗时（毫秒）
        inference_latency_ms: 推理耗时（毫秒）
    """

    response: ModelResponse
    from_cache: bool = False
    latency_ms: float = 0.0
    cache_latency_ms: float = 0.0
    inference_latency_ms: float = 0.0


class Gateway:
    """网关核心编排器。

    串联各层组件，处理完整的推理请求生命周期。

    参数:
        model_client: 推理客户端
        rate_limiter: 限流器
        cache: 缓存
        concurrency: 并发控制器
        monitor: 监控统计器（可选，不注入则跳过监控埋点）
        config: 网关配置字典
    """

    def __init__(
        self,
        model_client: ModelClient,
        rate_limiter: RateLimiter,
        cache: Cache,
        concurrency: ConcurrencyController,
        monitor: Optional[Monitor] = None,
        config: Optional[dict] = None,
    ) -> None:
        self.model_client = model_client
        self.rate_limiter = rate_limiter
        self.cache = cache
        self.concurrency = concurrency
        self.monitor = monitor
        self.config = config or {}

        self.enable_cache = self.config.get("enable_cache", True)
        self.enable_monitor = self.config.get("enable_monitor", True)

        self._lock = threading.Lock()
        self._total_requests = 0
        self._cache_hits = 0
        self._rate_limited = 0
        self._errors = 0

        logger.info(
            "Gateway 初始化: cache=%s, monitor=%s",
            self.enable_cache, self.enable_monitor,
        )

    # ---------------- 内部工具 ----------------

    def _record_stats(self, attr: str, delta: int = 1) -> None:
        """线程安全的计数器自增。"""
        with self._lock:
            setattr(self, attr, getattr(self, attr) + delta)

    def _emit_monitor(
        self,
        *,
        status: str,
        model: str = "",
        user: str = "",
        latency_ms: float = 0.0,
        inference_latency_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        from_cache: bool = False,
        error_type: str = "",
        error_message: str = "",
    ) -> None:
        """统一监控埋点入口，吞掉异常保证主流程不受影响。"""
        if not self.enable_monitor or self.monitor is None:
            return
        try:
            record = RequestRecord(
                request_id=uuid.uuid4().hex[:12],
                model=model,
                user=user,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
                inference_latency_ms=inference_latency_ms,
                status=status,
                error_type=error_type,
                error_message=error_message,
                from_cache=from_cache,
                timestamp=time.time(),
            )
            self.monitor.record(record)
        except Exception as e:
            logger.warning("监控埋点失败: %s", e)

    # ---------------- 核心方法 ----------------

    def process(self, request: GatewayRequest) -> GatewayResult:
        """处理一个推理请求（非流式）。

        流程：限流检查 → 缓存查询 → 并发控制 → 推理调用 → 缓存回写 → 监控埋点 → 响应

        参数:
            request: 网关请求

        返回:
            GatewayResult 响应结果

        抛出:
            RateLimitError: 触发限流
            ConcurrencyError: 并发超时
            GatewayError: 其他网关错误
        """
        start_time = time.monotonic()
        self._record_stats("_total_requests")

        rate_key = request.user or "global"
        model_name = request.model or "unknown"

        # 1. 限流检查
        if not self.rate_limiter.allow(rate_key):
            self._record_stats("_rate_limited")
            total_latency = (time.monotonic() - start_time) * 1000
            logger.warning("触发限流: user=%s", rate_key)
            self._emit_monitor(
                status="rate_limited",
                model=model_name,
                user=rate_key,
                latency_ms=total_latency,
                error_type="rate_limited",
            )
            raise RateLimitError(
                f"Rate limit exceeded for user '{rate_key}'", retry_after=1.0
            )

        # 2. 缓存查询（仅非流式请求）
        cache_key = None
        cache_latency = 0.0
        if self.enable_cache and not request.stream:
            cache_start = time.monotonic()
            cache_key = make_cache_key(
                model=model_name,
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                **request.extra,
            )
            cached = self.cache.get(cache_key)
            cache_latency = (time.monotonic() - cache_start) * 1000

            if cached is not None:
                try:
                    cached_data = json.loads(cached)
                    usage_data = cached_data.get("usage", {})
                    response = ModelResponse(
                        content=cached_data["content"],
                        model=cached_data.get("model", model_name),
                        usage=UsageInfo(**usage_data) if usage_data else UsageInfo(),
                        raw={"cached": True},
                    )
                    self._record_stats("_cache_hits")
                    total_latency = (time.monotonic() - start_time) * 1000
                    logger.info(
                        "缓存命中: key=%s, latency=%.2fms", cache_key[:16], total_latency
                    )
                    self._emit_monitor(
                        status="cached",
                        model=response.model,
                        user=rate_key,
                        latency_ms=total_latency,
                        inference_latency_ms=0.0,
                        prompt_tokens=response.usage.prompt_tokens,
                        completion_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens,
                        from_cache=True,
                    )
                    return GatewayResult(
                        response=response,
                        from_cache=True,
                        latency_ms=total_latency,
                        cache_latency_ms=cache_latency,
                        inference_latency_ms=0.0,
                    )
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning("缓存数据解析失败，回源: %s", e)

        # 3. 并发控制 + 推理调用
        with self.concurrency.guard(timeout=None) as acquired:
            if not acquired:
                self._record_stats("_errors")
                total_latency = (time.monotonic() - start_time) * 1000
                logger.error(
                    "并发控制超时: active=%d", self.concurrency.active_count()
                )
                self._emit_monitor(
                    status="error",
                    model=model_name,
                    user=rate_key,
                    latency_ms=total_latency,
                    error_type="concurrency_timeout",
                    error_message="Concurrency limit exceeded",
                )
                raise ConcurrencyError(
                    "Concurrency limit exceeded, request timed out"
                )

            inference_start = time.monotonic()
            try:
                response = self.model_client.chat(
                    messages=request.messages,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    top_p=request.top_p,
                    **request.extra,
                )
            except Exception as e:
                self._record_stats("_errors")
                total_latency = (time.monotonic() - start_time) * 1000
                logger.error("推理调用失败: %s", e)
                self._emit_monitor(
                    status="error",
                    model=model_name,
                    user=rate_key,
                    latency_ms=total_latency,
                    error_type="inference_error",
                    error_message=str(e),
                )
                raise GatewayError(f"Inference failed: {e}") from e

            inference_latency = (time.monotonic() - inference_start) * 1000

        # 4. 缓存回写
        if self.enable_cache and cache_key and not request.stream:
            try:
                cache_data = json.dumps(
                    {
                        "content": response.content,
                        "model": response.model,
                        "usage": {
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens,
                        },
                    },
                    ensure_ascii=False,
                )
                self.cache.set(cache_key, cache_data)
            except Exception as e:
                logger.warning("缓存回写失败: %s", e)

        total_latency = (time.monotonic() - start_time) * 1000
        logger.info(
            "请求完成: model=%s, latency=%.2fms (inference=%.2fms, cache=%.2fms), tokens=%d",
            response.model,
            total_latency,
            inference_latency,
            cache_latency,
            response.usage.total_tokens,
        )

        # 5. 成功监控埋点
        self._emit_monitor(
            status="success",
            model=response.model,
            user=rate_key,
            latency_ms=total_latency,
            inference_latency_ms=inference_latency,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            from_cache=False,
        )

        return GatewayResult(
            response=response,
            from_cache=False,
            latency_ms=total_latency,
            cache_latency_ms=cache_latency,
            inference_latency_ms=inference_latency,
        )

    async def stream_process(self, request: GatewayRequest):
        """处理流式推理请求（异步生成器）。

        流程：限流检查 → 并发控制 → 流式推理 → 监控埋点 → yield

        注意：并发控制使用同步 guard（基于 threading.Semaphore），在 async
        上下文中若超时等待会阻塞事件循环。建议后续为 ConcurrencyController
        增加 async guard（asyncio.Semaphore）支持。
        """
        self._record_stats("_total_requests")
        start_time = time.monotonic()
        rate_key = request.user or "global"
        model_name = request.model or "unknown"

        # 1. 限流检查
        if not self.rate_limiter.allow(rate_key):
            self._record_stats("_rate_limited")
            total_latency = (time.monotonic() - start_time) * 1000
            logger.warning("触发限流(流式): user=%s", rate_key)
            self._emit_monitor(
                status="rate_limited",
                model=model_name,
                user=rate_key,
                latency_ms=total_latency,
                error_type="rate_limited",
            )
            raise RateLimitError(f"Rate limit exceeded for user '{rate_key}'")

        # 2. 并发控制 + 流式推理
        with self.concurrency.guard(timeout=None) as acquired:
            if not acquired:
                self._record_stats("_errors")
                total_latency = (time.monotonic() - start_time) * 1000
                logger.error(
                    "并发控制超时(流式): active=%d", self.concurrency.active_count()
                )
                self._emit_monitor(
                    status="error",
                    model=model_name,
                    user=rate_key,
                    latency_ms=total_latency,
                    error_type="concurrency_timeout",
                    error_message="Concurrency limit exceeded",
                )
                raise ConcurrencyError("Concurrency limit exceeded")

            inference_latency = 0.0
            try:
                inference_start = time.monotonic()
                async for chunk in self.model_client.stream_chat(
                    messages=request.messages,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    top_p=request.top_p,
                    **request.extra,
                ):
                    yield chunk
                inference_latency = (time.monotonic() - inference_start) * 1000
            except (Exception, asyncio.CancelledError) as e:
                self._record_stats("_errors")
                total_latency = (time.monotonic() - start_time) * 1000
                logger.error("流式推理失败: %s", e)
                self._emit_monitor(
                    status="error",
                    model=model_name,
                    user=rate_key,
                    latency_ms=total_latency,
                    inference_latency_ms=inference_latency,
                    error_type="inference_error",
                    error_message=str(e),
                )
                raise
            finally:
                if inference_latency > 0:
                    total_latency = (time.monotonic() - start_time) * 1000
                    self._emit_monitor(
                        status="success",
                        model=model_name,
                        user=rate_key,
                        latency_ms=total_latency,
                        inference_latency_ms=inference_latency,
                        from_cache=False,
                    )

    # ---------------- 统计信息 ----------------

    @property
    def stats(self) -> Dict[str, Any]:
        """获取网关统计信息（线程安全快照）。"""
        with self._lock:
            total = self._total_requests
            cache_hits = self._cache_hits
            rate_limited = self._rate_limited
            errors = self._errors
        return {
            "total_requests": total,
            "cache_hits": cache_hits,
            "cache_misses": total - cache_hits,
            "cache_hit_rate": (cache_hits / total) if total > 0 else 0,
            "rate_limited": rate_limited,
            "errors": errors,
            "active_concurrent": self.concurrency.active_count(),
            "available_concurrent": self.concurrency.available(),
            "cache_size": self.cache.size(),
        }

    def close(self) -> None:
        """释放所有资源。"""
        self.model_client.close()
        logger.info("Gateway 已关闭，统计: %s", self.stats)