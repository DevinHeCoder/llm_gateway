"""
P4 API 层：FastAPI 应用入口（应用工厂，支持注入便于测试）。

启动:
    python -m uvicorn src.api.main:app --host 0.0.0.0 --port 9000

或:
    uvicorn src.api.main:app --reload --port 9000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from src.api.routes import api_router
from src.api.service import GatewayService
from src.utils.config_loader import load_config
from src.utils.logger import get_logger, setup_logging

logger = get_logger("gateway.api.main")


def create_app(
    config: Optional[dict] = None,
    service: Optional[GatewayService] = None,
) -> FastAPI:
    """创建 FastAPI 应用；可注入 config / service 便于测试。"""
    cfg = config or load_config()

    logging_cfg = cfg.get("logging", {})
    setup_logging(logging_cfg.get("config_path"))

    app_cfg = cfg.get("app", {})
    server_cfg = cfg.get("server", {})

    created_service = service or GatewayService.build_from_config(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        svc = getattr(app.state, "service", None)
        if svc is not None:
            svc.close()
        logger.info("应用已关闭")

    app = FastAPI(
        title=app_cfg.get("name", "LLM Gateway"),
        version=app_cfg.get("version", "0.1.0"),
        description="轻量化 LLM 推理服务 & LLMOps 网关平台：统一代理云端 LLM API"
        "（通义 DashScope / DeepSeek 等 OpenAI 兼容服务）或本地推理后端，"
        "提供限流、缓存、并发控制、监控统计、Prompt 版本管理等能力。",
        lifespan=lifespan,
    )

    app.state.service = created_service
    app.state.config = cfg

    app.include_router(api_router)

    logger.info(
        "FastAPI 应用创建完成: %s v%s, port=%s",
        app_cfg.get("name", "LLM Gateway"),
        app_cfg.get("version", "0.1.0"),
        server_cfg.get("port", 9000),
    )
    return app


app = create_app()