"""模型管理层：模型注册、版本管理、热加载协调、健康检查。"""
from src.model_manager.base import ModelInfo, ModelManager
from src.model_manager.registry import model_manager_registry
from src.model_manager import local_manager  # noqa: F401
from src.model_manager import vllm_manager  # noqa: F401


def build_model_manager(config: dict) -> ModelManager:
    """按配置创建模型管理器实例。"""
    provider = config.get("provider", "local")
    return model_manager_registry.create(provider, **config)
