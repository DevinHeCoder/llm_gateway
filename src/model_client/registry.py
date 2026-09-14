"""model_client 层的可插拔注册表实例。"""
from src.common.registry import Registry
from src.model_client.base import ModelClient

model_client_registry = Registry(
    name="model_client",
    base_type=ModelClient,
    default="mock",
)
