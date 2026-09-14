"""
模型管理路由：模型列表、加载、卸载、切换。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import get_gateway_service
from src.api.service import GatewayService
from src.model_manager.base import ModelInfo
from src.utils.logger import get_logger

logger = get_logger("gateway.api.routes.models")

router = APIRouter(prefix="/v1/models", tags=["models"])


class ModelInfoOut(BaseModel):
    """模型信息输出。"""
    name: str
    path: str = ""
    version: str = "1.0"
    status: str = "standby"
    loaded: bool = False
    backend: str = "vllm"
    context_length: int = 4096


class ModelActionRequest(BaseModel):
    """模型操作请求。"""
    name: str


def _model_to_out(model: ModelInfo) -> ModelInfoOut:
    return ModelInfoOut(
        name=model.name,
        path=model.path,
        version=model.version,
        status=model.status,
        loaded=model.loaded,
        backend=model.backend,
        context_length=model.context_length,
    )


@router.get("", response_model=List[ModelInfoOut], summary="列出所有模型")
async def list_models(service: GatewayService = Depends(get_gateway_service)) -> List[ModelInfoOut]:
    """列出所有已注册的模型。"""
    models = service.list_models()
    return [_model_to_out(m) for m in models]


@router.get("/{model_name}", response_model=ModelInfoOut, summary="获取模型信息")
async def get_model(model_name: str, service: GatewayService = Depends(get_gateway_service)) -> ModelInfoOut:
    """获取指定模型的详细信息。"""
    model = service.get_model(model_name)
    if model is None:
        raise HTTPException(status_code=404, detail=f"模型 '{model_name}' 未找到")
    return _model_to_out(model)


@router.post("/{model_name}/load", summary="加载模型")
async def load_model(model_name: str, service: GatewayService = Depends(get_gateway_service)) -> Dict[str, Any]:
    """加载模型到显存（热加载）。"""
    success = service.load_model(model_name)
    if not success:
        raise HTTPException(status_code=400, detail=f"模型 '{model_name}' 加载失败")
    return {"status": "loading", "model": model_name}


@router.post("/{model_name}/unload", summary="卸载模型")
async def unload_model(model_name: str, service: GatewayService = Depends(get_gateway_service)) -> Dict[str, Any]:
    """从显存卸载模型。"""
    success = service.unload_model(model_name)
    if not success:
        raise HTTPException(status_code=400, detail=f"模型 '{model_name}' 卸载失败")
    return {"status": "unloaded", "model": model_name}


@router.post("/{model_name}/switch", summary="切换激活模型")
async def switch_model(model_name: str, service: GatewayService = Depends(get_gateway_service)) -> Dict[str, Any]:
    """切换当前激活的模型。"""
    success = service.switch_model(model_name)
    if not success:
        raise HTTPException(status_code=400, detail=f"模型 '{model_name}' 切换失败")
    return {"status": "switched", "active_model": model_name}


@router.get("/active/current", response_model=Optional[ModelInfoOut], summary="获取当前激活模型")
async def get_active_model(service: GatewayService = Depends(get_gateway_service)) -> Optional[ModelInfoOut]:
    """获取当前激活的模型。"""
    model = service.get_active_model()
    if model is None:
        return None
    return _model_to_out(model)
