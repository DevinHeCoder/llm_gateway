"""
vLLM 模型管理器：通过 vLLM 管理 API 协调模型加载/卸载/切换。

vLLM 0.5+ 支持动态模型加载（通过 /v1/models 管理端点）。
本管理器封装这些 API，提供统一的模型管理接口。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

import httpx

from src.common.exceptions import ModelManagerError
from src.model_manager.base import ModelInfo, ModelManager
from src.model_manager.registry import model_manager_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.model_manager.vllm")


@model_manager_registry.register("vllm")
class VLLMModelManager(ModelManager):
    """vLLM 模型管理器（通过 API 协调）。

    参数:
        provider: 实现名
        management_url: vLLM 管理 API 地址
        health_check_interval: 健康检查间隔（秒）
        models: 初始模型配置列表
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "vllm",
        management_url: str = "http://localhost:8000",
        health_check_interval: int = 30,
        models: Optional[List[dict]] = None,
        **kwargs,
    ) -> None:
        self.management_url = management_url.rstrip("/")
        self.health_check_interval = health_check_interval
        self._models: Dict[str, ModelInfo] = {}
        self._active_model: Optional[str] = None
        self._lock = threading.Lock()
        self._client = httpx.Client(timeout=30)
        self._last_health_check = 0.0

        # 从配置加载模型注册信息
        if models:
            for m_cfg in models:
                model = ModelInfo(
                    name=m_cfg.get("name", ""),
                    path=m_cfg.get("path", ""),
                    version=m_cfg.get("version", "1.0"),
                    status=m_cfg.get("status", "standby"),
                    created_at=time.time(),
                )
                if model.name:
                    self._models[model.name] = model
                    if model.status == "active":
                        self._active_model = model.name

        logger.info(
            "VLLMModelManager 初始化: url=%s, %d 个模型",
            self.management_url, len(self._models),
        )

    def _api_request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """调用 vLLM 管理 API。"""
        url = f"{self.management_url}{path}"
        try:
            resp = self._client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPError as e:
            logger.error("vLLM 管理 API 调用失败: %s %s - %s", method, path, e)
            raise ModelManagerError(f"vLLM API 调用失败: {e}") from e

    def list_models(self) -> List[ModelInfo]:
        """从 vLLM 获取当前加载的模型列表，合并本地注册信息。"""
        try:
            data = self._api_request("GET", "/v1/models")
            vllm_models = data.get("data", [])
            vllm_model_names = {m.get("id") for m in vllm_models}

            with self._lock:
                # 更新本地模型状态
                for name in self._models:
                    if name in vllm_model_names:
                        self._models[name].status = "active"
                        self._models[name].loaded = True
                    else:
                        if self._models[name].status == "active":
                            self._models[name].status = "standby"
                            self._models[name].loaded = False

                # 添加 vLLM 中存在但本地未注册的模型
                for m in vllm_models:
                    name = m.get("id", "")
                    if name and name not in self._models:
                        self._models[name] = ModelInfo(
                            name=name,
                            status="active",
                            loaded=True,
                            created_at=time.time(),
                            metadata={"vllm": True},
                        )

                return list(self._models.values())
        except ModelManagerError:
            # API 失败时返回本地缓存
            with self._lock:
                return list(self._models.values())

    def get_model(self, name: str) -> Optional[ModelInfo]:
        with self._lock:
            return self._models.get(name)

    def register_model(self, model: ModelInfo) -> bool:
        with self._lock:
            if model.name in self._models:
                logger.warning("模型已注册: %s", model.name)
                return False
            model.created_at = time.time()
            self._models[model.name] = model
            logger.info("注册模型: %s (%s)", model.name, model.path)
            return True

    def unregister_model(self, name: str) -> bool:
        with self._lock:
            if name not in self._models:
                return False
            if self._active_model == name:
                logger.warning("不能注销当前激活的模型: %s", name)
                return False
            del self._models[name]
            logger.info("注销模型: %s", name)
            return True

    def load_model(self, name: str) -> bool:
        """通过 vLLM API 加载模型（vLLM 0.5+ 支持动态加载）。"""
        with self._lock:
            model = self._models.get(name)
            if model is None:
                logger.error("模型未注册: %s", name)
                return False

        try:
            # vLLM 动态加载模型（具体 API 路径取决于 vLLM 版本）
            self._api_request(
                "POST",
                "/v1/load_model",
                json={"model": model.path or model.name},
            )
            with self._lock:
                model.status = "active"
                model.loaded = True
            logger.info("模型加载成功: %s", name)
            return True
        except ModelManagerError as e:
            logger.error("模型加载失败: %s - %s", name, e)
            with self._lock:
                model.status = "error"
            return False

    def unload_model(self, name: str) -> bool:
        """通过 vLLM API 卸载模型。"""
        with self._lock:
            model = self._models.get(name)
            if model is None:
                return False
            if self._active_model == name:
                logger.warning("不能卸载当前激活的模型: %s", name)
                return False

        try:
            self._api_request(
                "POST",
                "/v1/unload_model",
                json={"model": model.path or model.name},
            )
            with self._lock:
                model.status = "standby"
                model.loaded = False
            logger.info("模型卸载成功: %s", name)
            return True
        except ModelManagerError as e:
            logger.error("模型卸载失败: %s - %s", name, e)
            return False

    def switch_model(self, name: str) -> bool:
        """切换激活模型：加载新模型，卸载旧模型。"""
        with self._lock:
            if name not in self._models:
                logger.error("模型不存在: %s", name)
                return False
            old_active = self._active_model

        # 加载新模型
        if not self.load_model(name):
            return False

        # 卸载旧模型
        if old_active and old_active != name:
            self.unload_model(old_active)

        with self._lock:
            self._active_model = name
        logger.info("切换激活模型: %s -> %s", old_active, name)
        return True

    def get_active_model(self) -> Optional[ModelInfo]:
        with self._lock:
            if self._active_model:
                return self._models.get(self._active_model)
            return None

    async def health_check(self) -> Dict[str, Any]:
        """检查 vLLM 服务和模型健康状态。"""
        self._last_health_check = time.time()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.management_url}/health")
                healthy = resp.status_code == 200
        except Exception as e:
            logger.warning("vLLM 健康检查失败: %s", e)
            healthy = False

        with self._lock:
            models_status = {
                name: {"status": m.status, "loaded": m.loaded}
                for name, m in self._models.items()
            }

        return {
            "healthy": healthy,
            "active_model": self._active_model,
            "models": models_status,
            "checked_at": self._last_health_check,
        }
