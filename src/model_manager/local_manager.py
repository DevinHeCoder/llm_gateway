"""
本地模型管理器：基于配置文件的模型注册管理，不直接操作 vLLM 进程。

适合单模型部署、模型切换不频繁的场景。模型列表从配置文件加载，
状态管理在网关进程内维护。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from src.model_manager.base import ModelInfo, ModelManager
from src.model_manager.registry import model_manager_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.model_manager.local")


@model_manager_registry.register("local")
class LocalModelManager(ModelManager):
    """本地模型管理器（基于配置）。

    参数:
        provider: 实现名
        models: 模型配置列表（从 settings.yaml 加载）
        health_check_interval: 健康检查间隔（秒）
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "local",
        models: Optional[List[dict]] = None,
        health_check_interval: int = 30,
        **kwargs,
    ) -> None:
        self._models: Dict[str, ModelInfo] = {}
        self._active_model: Optional[str] = None
        self._lock = threading.Lock()
        self.health_check_interval = health_check_interval
        self._last_health_check = 0.0

        # 从配置加载模型
        if models:
            for m_cfg in models:
                model = ModelInfo(
                    name=m_cfg.get("name", ""),
                    path=m_cfg.get("path", ""),
                    version=m_cfg.get("version", "1.0"),
                    status=m_cfg.get("status", "standby"),
                    loaded=m_cfg.get("status") == "active",
                    created_at=time.time(),
                )
                if model.name:
                    self._models[model.name] = model
                    if model.status == "active":
                        self._active_model = model.name

        logger.info(
            "LocalModelManager 初始化: %d 个模型, active=%s",
            len(self._models), self._active_model,
        )

    def list_models(self) -> List[ModelInfo]:
        with self._lock:
            return list(self._models.values())

    def get_model(self, name: str) -> Optional[ModelInfo]:
        with self._lock:
            return self._models.get(name)

    def register_model(self, model: ModelInfo) -> bool:
        with self._lock:
            if model.name in self._models:
                logger.warning("模型已存在: %s", model.name)
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
        """本地管理器不实际加载模型，只更新状态。"""
        with self._lock:
            model = self._models.get(name)
            if model is None:
                logger.error("模型不存在: %s", name)
                return False
            model.status = "active"
            model.loaded = True
            logger.info("模型已标记为加载: %s", name)
            return True

    def unload_model(self, name: str) -> bool:
        with self._lock:
            model = self._models.get(name)
            if model is None:
                return False
            if self._active_model == name:
                logger.warning("不能卸载当前激活的模型: %s", name)
                return False
            model.status = "standby"
            model.loaded = False
            logger.info("模型已标记为卸载: %s", name)
            return True

    def switch_model(self, name: str) -> bool:
        with self._lock:
            if name not in self._models:
                logger.error("模型不存在: %s", name)
                return False
            # 取消当前激活
            if self._active_model and self._active_model in self._models:
                self._models[self._active_model].status = "standby"
            # 激活新模型
            self._models[name].status = "active"
            self._models[name].loaded = True
            self._active_model = name
            logger.info("切换激活模型: %s", name)
            return True

    def get_active_model(self) -> Optional[ModelInfo]:
        with self._lock:
            if self._active_model:
                return self._models.get(self._active_model)
            return None

    async def health_check(self) -> Dict[str, Any]:
        """本地管理器的健康检查：检查模型状态是否正常。"""
        self._last_health_check = time.time()
        with self._lock:
            models_status = {
                name: {"status": m.status, "loaded": m.loaded}
                for name, m in self._models.items()
            }
        return {
            "healthy": True,
            "active_model": self._active_model,
            "models": models_status,
            "checked_at": self._last_health_check,
        }
