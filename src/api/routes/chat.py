"""
聊天补全路由：/v1/chat/completions（OpenAI 兼容）。

支持非流式和流式（SSE）两种响应模式。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_gateway_service
from src.api.schemas import ChatCompletionRequest, ChatCompletionResponse, ErrorResponse
from src.api.service import GatewayService
from src.common.exceptions import ConcurrencyError, GatewayError, RateLimitError
from src.utils.logger import get_logger

logger = get_logger("gateway.api.routes.chat")

router = APIRouter()


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    summary="聊天补全（OpenAI 兼容）",
)
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    service: GatewayService = Depends(get_gateway_service),
) -> Any:
    """聊天补全接口，与 OpenAI API 兼容。

    - 非流式：返回完整的 ChatCompletionResponse
    - 流式：返回 SSE 事件流
    """
    if body.stream:
        return await _stream_chat(body, service)
    else:
        return _non_stream_chat(body, service)


def _non_stream_chat(
    body: ChatCompletionRequest,
    service: GatewayService,
) -> ChatCompletionResponse:
    """处理非流式请求。"""
    try:
        return service.chat_completion(body)
    except RateLimitError as e:
        logger.warning("限流: %s", e)
        from fastapi import HTTPException
        raise HTTPException(
            status_code=429,
            detail={"error": {"message": str(e), "type": "rate_limit_error"}},
            headers={"Retry-After": str(e.retry_after)},
        )
    except ConcurrencyError as e:
        logger.warning("并发超时: %s", e)
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail={"error": {"message": str(e), "type": "concurrency_error"}},
        )
    except GatewayError as e:
        logger.error("网关错误: %s", e)
        from fastapi import HTTPException
        raise HTTPException(
            status_code=502,
            detail={"error": {"message": str(e), "type": "gateway_error"}},
        )


async def _stream_chat(
    body: ChatCompletionRequest,
    service: GatewayService,
) -> StreamingResponse:
    """处理流式请求，返回 SSE 事件流。"""

    async def event_generator():
        try:
            async for chunk in service.stream_chat_completion(body):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except RateLimitError as e:
            logger.warning("流式限流: %s", e)
            error_chunk = {
                "error": {"message": str(e), "type": "rate_limit_error"},
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except ConcurrencyError as e:
            logger.warning("流式并发超时: %s", e)
            error_chunk = {
                "error": {"message": str(e), "type": "concurrency_error"},
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except GatewayError as e:
            logger.error("流式网关错误: %s", e)
            error_chunk = {
                "error": {"message": str(e), "type": "gateway_error"},
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )