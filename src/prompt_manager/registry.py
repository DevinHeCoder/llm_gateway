"""prompt_manager 层的可插拔注册表实例。"""
from src.common.registry import Registry
from src.prompt_manager.base import PromptManager

prompt_manager_registry = Registry(
    name="prompt_manager",
    base_type=PromptManager,
    default="sqlite",
)
