"""
内存 Prompt 存储：基于内存字典的 Prompt 管理，重启丢失。

适合开发测试场景，不需要持久化。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from src.prompt_manager.base import (
    PromptManager,
    PromptTemplate,
    PromptVersion,
    extract_variables,
    render_prompt,
)
from src.prompt_manager.registry import prompt_manager_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.prompt_manager.memory")


@prompt_manager_registry.register("memory")
class MemoryPromptManager(PromptManager):
    """内存 Prompt 管理器。"""

    def __init__(self, provider: str = "memory", **kwargs) -> None:
        self._prompts: Dict[str, PromptTemplate] = {}
        self._lock = threading.Lock()
        logger.info("MemoryPromptManager 初始化")

    def create_prompt(
        self,
        name: str,
        content: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        created_by: str = "",
    ) -> PromptTemplate:
        now = time.time()
        variables = extract_variables(content)
        version = PromptVersion(
            version="1.0",
            content=content,
            description="初始版本",
            created_at=now,
            created_by=created_by,
            variables=variables,
        )
        template = PromptTemplate(
            name=name,
            description=description,
            current_version="1.0",
            versions=[version],
            created_at=now,
            updated_at=now,
            tags=tags or [],
        )

        with self._lock:
            if name in self._prompts:
                raise ValueError(f"Prompt '{name}' 已存在")
            self._prompts[name] = template

        logger.info("创建 Prompt: %s (v1.0)", name)
        return template

    def get_prompt(self, name: str) -> Optional[PromptTemplate]:
        with self._lock:
            return self._prompts.get(name)

    def list_prompts(self, tag: Optional[str] = None) -> List[PromptTemplate]:
        with self._lock:
            templates = list(self._prompts.values())
            if tag:
                templates = [t for t in templates if tag in t.tags]
            return sorted(templates, key=lambda t: t.updated_at, reverse=True)

    def update_prompt(
        self,
        name: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        with self._lock:
            template = self._prompts.get(name)
            if template is None:
                return False
            if description is not None:
                template.description = description
            if tags is not None:
                template.tags = tags
            template.updated_at = time.time()
        logger.info("更新 Prompt: %s", name)
        return True

    def delete_prompt(self, name: str) -> bool:
        with self._lock:
            if name in self._prompts:
                del self._prompts[name]
                logger.info("删除 Prompt: %s", name)
                return True
            return False

    def create_version(
        self,
        name: str,
        content: str,
        description: str = "",
        version: Optional[str] = None,
        created_by: str = "",
    ) -> Optional[PromptVersion]:
        with self._lock:
            template = self._prompts.get(name)
            if template is None:
                return None

            # 自动生成版本号
            if version is None:
                if template.versions:
                    last = template.versions[-1].version
                    try:
                        major, minor = last.split(".")
                        version = f"{major}.{int(minor) + 1}"
                    except (ValueError, IndexError):
                        version = f"{int(time.time())}"
                else:
                    version = "1.0"

            # 检查版本是否已存在
            if any(v.version == version for v in template.versions):
                raise ValueError(f"Prompt '{name}' 版本 '{version}' 已存在")

            now = time.time()
            variables = extract_variables(content)
            new_version = PromptVersion(
                version=version,
                content=content,
                description=description,
                created_at=now,
                created_by=created_by,
                variables=variables,
            )
            template.versions.append(new_version)
            template.updated_at = now

        logger.info("创建 Prompt 版本: %s v%s", name, version)
        return new_version

    def get_version(self, name: str, version: str) -> Optional[PromptVersion]:
        with self._lock:
            template = self._prompts.get(name)
            if template is None:
                return None
            for v in template.versions:
                if v.version == version:
                    return v
            return None

    def list_versions(self, name: str) -> List[PromptVersion]:
        with self._lock:
            template = self._prompts.get(name)
            if template is None:
                return []
            return list(template.versions)

    def set_current_version(self, name: str, version: str) -> bool:
        with self._lock:
            template = self._prompts.get(name)
            if template is None:
                return False
            if not any(v.version == version for v in template.versions):
                return False
            template.current_version = version
            template.updated_at = time.time()
        logger.info("设置当前版本: %s v%s", name, version)
        return True

    def render(
        self,
        name: str,
        variables: Dict[str, Any],
        version: Optional[str] = None,
    ) -> Optional[str]:
        with self._lock:
            template = self._prompts.get(name)
            if template is None:
                return None
            ver = version or template.current_version
            if not ver:
                return None
            for v in template.versions:
                if v.version == ver:
                    return render_prompt(v.content, variables)
            return None
