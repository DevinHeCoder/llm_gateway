"""model_manager 层的可插拔注册表实例。"""
from src.common.registry import Registry
from src.model_manager.base import ModelManager

model_manager_registry = Registry(
    name="model_manager",
    base_type=ModelManager,
    default="local",
)
