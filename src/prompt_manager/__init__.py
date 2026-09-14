"""Prompt 管理层：Prompt 版本管理、A/B 测试、流量分配。"""
from src.prompt_manager.ab_testing import ABTestManager, ABTest, ABTestResult, ABTestVariant
from src.prompt_manager.base import PromptManager, PromptTemplate, PromptVersion
from src.prompt_manager.memory_store import MemoryPromptManager
from src.prompt_manager.registry import prompt_manager_registry
from src.prompt_manager.sqlite_store import SQLitePromptManager
from src.prompt_manager import sqlite_store  # noqa: F401
from src.prompt_manager import memory_store  # noqa: F401


def build_prompt_manager(config: dict) -> PromptManager:
    """按配置创建 Prompt 管理器实例。"""
    provider = config.get("provider", "sqlite")
    return prompt_manager_registry.create(provider, **config)


__all__ = [
    "PromptTemplate",
    "PromptVersion",
    "PromptManager",
    "MemoryPromptManager",
    "SQLitePromptManager",
    "ABTestManager",
    "ABTest",
    "ABTestResult",
    "ABTestVariant",
    "build_prompt_manager",
]
