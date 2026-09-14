"""
Prompt 管理路由：Prompt CRUD、版本管理、A/B 测试。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import get_gateway_service
from src.api.service import GatewayService
from src.prompt_manager.base import PromptTemplate, PromptVersion
from src.prompt_manager.ab_testing import ABTest, ABTestVariant
from src.utils.logger import get_logger

logger = get_logger("gateway.api.routes.prompts")

router = APIRouter(prefix="/v1/prompts", tags=["prompts"])


# ---------------- 请求/响应模型 ----------------

class CreatePromptRequest(BaseModel):
    name: str = Field(..., description="Prompt 名称（唯一）")
    content: str = Field(..., description="Prompt 模板内容（支持 {variable} 占位符）")
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    created_by: str = ""


class UpdatePromptRequest(BaseModel):
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class CreateVersionRequest(BaseModel):
    content: str
    description: str = ""
    version: Optional[str] = None
    created_by: str = ""


class RenderRequest(BaseModel):
    variables: Dict[str, Any] = Field(default_factory=dict)
    version: Optional[str] = None


class CreateABTestRequest(BaseModel):
    name: str
    description: str = ""
    variants: List[Dict[str, Any]]


class PromptVersionOut(BaseModel):
    version: str
    content: str
    description: str = ""
    created_at: float = 0
    created_by: str = ""
    variables: List[str] = Field(default_factory=list)


class PromptTemplateOut(BaseModel):
    name: str
    description: str = ""
    current_version: str = ""
    versions: List[PromptVersionOut] = Field(default_factory=list)
    created_at: float = 0
    updated_at: float = 0
    tags: List[str] = Field(default_factory=list)


def _version_to_out(v: PromptVersion) -> PromptVersionOut:
    return PromptVersionOut(
        version=v.version,
        content=v.content,
        description=v.description,
        created_at=v.created_at,
        created_by=v.created_by,
        variables=v.variables,
    )


def _template_to_out(t: PromptTemplate) -> PromptTemplateOut:
    return PromptTemplateOut(
        name=t.name,
        description=t.description,
        current_version=t.current_version,
        versions=[_version_to_out(v) for v in t.versions],
        created_at=t.created_at,
        updated_at=t.updated_at,
        tags=t.tags,
    )


# ---------------- Prompt 模板 CRUD ----------------

@router.post("", response_model=PromptTemplateOut, summary="创建 Prompt 模板")
async def create_prompt(
    body: CreatePromptRequest,
    service: GatewayService = Depends(get_gateway_service),
) -> PromptTemplateOut:
    """创建新的 Prompt 模板（同时创建 1.0 版本）。"""
    if service.prompt_manager is None:
        raise HTTPException(status_code=503, detail="Prompt 管理未启用")
    try:
        template = service.prompt_manager.create_prompt(
            name=body.name,
            content=body.content,
            description=body.description,
            tags=body.tags,
            created_by=body.created_by,
        )
        return _template_to_out(template)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[PromptTemplateOut], summary="列出所有 Prompt")
async def list_prompts(
    tag: Optional[str] = None,
    service: GatewayService = Depends(get_gateway_service),
) -> List[PromptTemplateOut]:
    """列出所有 Prompt 模板。"""
    if service.prompt_manager is None:
        return []
    templates = service.prompt_manager.list_prompts(tag=tag)
    return [_template_to_out(t) for t in templates]


@router.get("/{prompt_name}", response_model=PromptTemplateOut, summary="获取 Prompt 详情")
async def get_prompt(
    prompt_name: str,
    service: GatewayService = Depends(get_gateway_service),
) -> PromptTemplateOut:
    """获取指定 Prompt 的详细信息（含所有版本）。"""
    if service.prompt_manager is None:
        raise HTTPException(status_code=503, detail="Prompt 管理未启用")
    template = service.prompt_manager.get_prompt(prompt_name)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' 未找到")
    return _template_to_out(template)


@router.put("/{prompt_name}", summary="更新 Prompt 元信息")
async def update_prompt(
    prompt_name: str,
    body: UpdatePromptRequest,
    service: GatewayService = Depends(get_gateway_service),
) -> Dict[str, Any]:
    """更新 Prompt 模板的描述和标签。"""
    if service.prompt_manager is None:
        raise HTTPException(status_code=503, detail="Prompt 管理未启用")
    success = service.prompt_manager.update_prompt(
        name=prompt_name,
        description=body.description,
        tags=body.tags,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' 未找到")
    return {"status": "updated", "name": prompt_name}


@router.delete("/{prompt_name}", summary="删除 Prompt")
async def delete_prompt(
    prompt_name: str,
    service: GatewayService = Depends(get_gateway_service),
) -> Dict[str, Any]:
    """删除 Prompt 模板（含所有版本）。"""
    if service.prompt_manager is None:
        raise HTTPException(status_code=503, detail="Prompt 管理未启用")
    success = service.prompt_manager.delete_prompt(prompt_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' 未找到")
    return {"status": "deleted", "name": prompt_name}


# ---------------- 版本管理 ----------------

@router.post("/{prompt_name}/versions", response_model=PromptVersionOut, summary="创建新版本")
async def create_version(
    prompt_name: str,
    body: CreateVersionRequest,
    service: GatewayService = Depends(get_gateway_service),
) -> PromptVersionOut:
    """为指定 Prompt 创建新版本。"""
    if service.prompt_manager is None:
        raise HTTPException(status_code=503, detail="Prompt 管理未启用")
    try:
        version = service.prompt_manager.create_version(
            name=prompt_name,
            content=body.content,
            description=body.description,
            version=body.version,
            created_by=body.created_by,
        )
        if version is None:
            raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' 未找到")
        return _version_to_out(version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{prompt_name}/versions", response_model=List[PromptVersionOut], summary="列出所有版本")
async def list_versions(
    prompt_name: str,
    service: GatewayService = Depends(get_gateway_service),
) -> List[PromptVersionOut]:
    """列出指定 Prompt 的所有版本。"""
    if service.prompt_manager is None:
        return []
    versions = service.prompt_manager.list_versions(prompt_name)
    return [_version_to_out(v) for v in versions]


@router.post("/{prompt_name}/versions/{version}/activate", summary="设置当前版本")
async def set_current_version(
    prompt_name: str,
    version: str,
    service: GatewayService = Depends(get_gateway_service),
) -> Dict[str, Any]:
    """设置指定版本为当前激活版本。"""
    if service.prompt_manager is None:
        raise HTTPException(status_code=503, detail="Prompt 管理未启用")
    success = service.prompt_manager.set_current_version(prompt_name, version)
    if not success:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' 或版本 '{version}' 未找到")
    return {"status": "activated", "name": prompt_name, "version": version}


@router.post("/{prompt_name}/render", summary="渲染 Prompt")
async def render_prompt(
    prompt_name: str,
    body: RenderRequest,
    service: GatewayService = Depends(get_gateway_service),
) -> Dict[str, Any]:
    """渲染 Prompt 模板，替换变量占位符。"""
    if service.prompt_manager is None:
        raise HTTPException(status_code=503, detail="Prompt 管理未启用")
    result = service.prompt_manager.render(
        name=prompt_name,
        variables=body.variables,
        version=body.version,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' 未找到或版本不存在")
    return {"name": prompt_name, "version": body.version or "current", "rendered": result}


# ---------------- A/B 测试 ----------------

@router.post("/ab-tests", summary="创建 A/B 测试")
async def create_ab_test(
    body: CreateABTestRequest,
    service: GatewayService = Depends(get_gateway_service),
) -> Dict[str, Any]:
    """创建新的 A/B 测试实验。"""
    if service.ab_test_manager is None:
        raise HTTPException(status_code=503, detail="A/B 测试未启用")
    try:
        variants = [
            ABTestVariant(
                name=v["name"],
                prompt_name=v["prompt_name"],
                prompt_version=v["prompt_version"],
                traffic_percent=v.get("traffic_percent", 50.0),
                description=v.get("description", ""),
            )
            for v in body.variants
        ]
        test = service.ab_test_manager.create_test(
            name=body.name,
            variants=variants,
            description=body.description,
        )
        return {"id": test.id, "name": test.name, "status": test.status, "variants": len(variants)}
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ab-tests", summary="列出 A/B 测试")
async def list_ab_tests(
    status: Optional[str] = None,
    service: GatewayService = Depends(get_gateway_service),
) -> List[Dict[str, Any]]:
    """列出所有 A/B 测试实验。"""
    if service.ab_test_manager is None:
        return []
    tests = service.ab_test_manager.list_tests(status=status)
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "status": t.status,
            "variants": [
                {"name": v.name, "prompt_name": v.prompt_name, "prompt_version": v.prompt_version, "traffic_percent": v.traffic_percent}
                for v in t.variants
            ],
            "created_at": t.created_at,
        }
        for t in tests
    ]


@router.get("/ab-tests/{test_id}/results", summary="获取 A/B 测试结果")
async def get_ab_test_results(
    test_id: str,
    service: GatewayService = Depends(get_gateway_service),
) -> Dict[str, Any]:
    """获取 A/B 测试的结果对比。"""
    if service.ab_test_manager is None:
        raise HTTPException(status_code=503, detail="A/B 测试未启用")
    result = service.ab_test_manager.get_test_result(test_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"A/B 测试 '{test_id}' 未找到")
    return {
        "test_id": result.test_id,
        "test_name": result.test_name,
        "status": result.status,
        "winner": result.winner,
        "confidence": result.confidence,
        "variant_results": result.variant_results,
    }


@router.post("/ab-tests/{test_id}/pause", summary="暂停 A/B 测试")
async def pause_ab_test(
    test_id: str,
    service: GatewayService = Depends(get_gateway_service),
) -> Dict[str, Any]:
    """暂停 A/B 测试实验。"""
    if service.ab_test_manager is None:
        raise HTTPException(status_code=503, detail="A/B 测试未启用")
    success = service.ab_test_manager.pause_test(test_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"A/B 测试 '{test_id}' 未找到")
    return {"status": "paused", "test_id": test_id}


@router.post("/ab-tests/{test_id}/resume", summary="恢复 A/B 测试")
async def resume_ab_test(
    test_id: str,
    service: GatewayService = Depends(get_gateway_service),
) -> Dict[str, Any]:
    """恢复 A/B 测试实验。"""
    if service.ab_test_manager is None:
        raise HTTPException(status_code=503, detail="A/B 测试未启用")
    success = service.ab_test_manager.resume_test(test_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"A/B 测试 '{test_id}' 未找到")
    return {"status": "running", "test_id": test_id}
