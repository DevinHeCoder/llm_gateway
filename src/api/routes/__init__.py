"""API 路由集合。"""
from fastapi import APIRouter

from src.api.routes import chat, system, models, metrics, prompts

api_router = APIRouter()
api_router.include_router(chat.router, prefix="/v1", tags=["chat"])
api_router.include_router(models.router, tags=["models"])
api_router.include_router(prompts.router, tags=["prompts"])
api_router.include_router(metrics.router, tags=["metrics"])
api_router.include_router(system.router, tags=["system"])
