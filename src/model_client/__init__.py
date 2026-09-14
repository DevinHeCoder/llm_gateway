"""推理客户端层：统一模型调用接口，支持 vLLM / Mock 等多种后端。"""
from src.model_client.base import ChatMessage, ModelClient, ModelResponse, UsageInfo
from src.model_client.mock_client import MockClient
from src.model_client.registry import model_client_registry
from src.model_client.vllm_client import VLLMClient
from src.model_client import vllm_client  # noqa: F401  触发注册
from src.model_client import mock_client  # noqa: F401  触发注册


def build_model_client(config: dict) -> ModelClient:
    """按配置创建推理客户端实例。

    参数:
        config: model 段配置字典，需包含 provider 字段。

    返回:
        ModelClient 实例
    """
    provider = config.get("provider", "mock")
    return model_client_registry.create(provider, **config)
