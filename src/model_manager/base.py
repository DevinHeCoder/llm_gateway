"""
模型管理抽象基类。

所有模型管理器实现统一接口：list_models() / get_model() / load_model() /
unload_model() / switch_model() / health_check()。
用于统一模型管理、版本切换、热加载协调。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModelInfo:
    """模型信息。

    属性:
        name: 模型名称（唯一标识）
        path: 模型路径或 HuggingFace ID
        version: 模型版本
        status: 模型状态（active / standby / loading / unloading / error）
        loaded: 是否已加载到显存
        backend: 推理后端（vllm / transformers 等）
        context_length: 上下文长度
        created_at: 创建时间戳
        metadata: 额外元数据
    """

    name: str
    path: str = ""
    version: str = "1.0"
    status: str = "standby"  # active / standby / loading / unloading / error
    loaded: bool = False
    backend: str = "vllm"
    context_length: int = 4096
    created_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModelManager(ABC):
    """模型管理器统一接口。"""

    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        """列出所有已注册的模型。"""
        pass

    @abstractmethod
    def get_model(self, name: str) -> Optional[ModelInfo]:
        """获取指定模型的信息。"""
        pass

    @abstractmethod
    def register_model(self, model: ModelInfo) -> bool:
        """注册一个新模型。"""
        pass

    @abstractmethod
    def unregister_model(self, name: str) -> bool:
        """注销一个模型。"""
        pass

    @abstractmethod
    def load_model(self, name: str) -> bool:
        """加载模型到显存（热加载）。"""
        pass

    @abstractmethod
    def unload_model(self, name: str) -> bool:
        """从显存卸载模型。"""
        pass

    @abstractmethod
    def switch_model(self, name: str) -> bool:
        """切换当前激活的模型。"""
        pass

    @abstractmethod
    def get_active_model(self) -> Optional[ModelInfo]:
        """获取当前激活的模型。"""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """检查所有模型的健康状态。"""
        pass
