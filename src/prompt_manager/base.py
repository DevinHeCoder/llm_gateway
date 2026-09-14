"""
Prompt 管理抽象基类。

所有 Prompt 管理器实现统一接口：create_prompt() / get_prompt() / list_prompts() /
update_prompt() / delete_prompt() / create_version() / get_version() / list_versions() /
render_prompt()。
用于 Prompt 版本管理、模板渲染。
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PromptVersion:
    """Prompt 版本。

    属性:
        version: 版本号（如 "1.0", "1.1"）
        content: Prompt 模板内容（支持 {variable} 占位符）
        description: 版本描述
        created_at: 创建时间戳
        created_by: 创建者
        variables: 模板中提取的变量列表
        metadata: 额外元数据
    """

    version: str
    content: str
    description: str = ""
    created_at: float = 0.0
    created_by: str = ""
    variables: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptTemplate:
    """Prompt 模板。

    属性:
        name: 模板名称（唯一标识）
        description: 模板描述
        current_version: 当前激活版本号
        versions: 所有版本列表
        created_at: 创建时间戳
        updated_at: 最后更新时间戳
        tags: 标签列表
        metadata: 额外元数据
    """

    name: str
    description: str = ""
    current_version: str = ""
    versions: List[PromptVersion] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def extract_variables(content: str) -> List[str]:
    """从 Prompt 模板中提取 {variable} 占位符变量名。"""
    pattern = r"\{(\w+)\}"
    return list(set(re.findall(pattern, content)))


def render_prompt(content: str, variables: Dict[str, Any]) -> str:
    """渲染 Prompt 模板，替换 {variable} 占位符。

    未提供的变量保持原样（不替换），避免静默丢失。
    """
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name in variables:
            return str(variables[var_name])
        return match.group(0)  # 保持原样

    pattern = r"\{(\w+)\}"
    return re.sub(pattern, _replace, content)


class PromptManager(ABC):
    """Prompt 管理器统一接口。"""

    @abstractmethod
    def create_prompt(
        self,
        name: str,
        content: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        created_by: str = "",
    ) -> PromptTemplate:
        """创建新的 Prompt 模板（同时创建 1.0 版本）。"""
        pass

    @abstractmethod
    def get_prompt(self, name: str) -> Optional[PromptTemplate]:
        """获取 Prompt 模板（含所有版本）。"""
        pass

    @abstractmethod
    def list_prompts(self, tag: Optional[str] = None) -> List[PromptTemplate]:
        """列出所有 Prompt 模板。"""
        pass

    @abstractmethod
    def update_prompt(
        self,
        name: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """更新 Prompt 模板元信息。"""
        pass

    @abstractmethod
    def delete_prompt(self, name: str) -> bool:
        """删除 Prompt 模板（含所有版本）。"""
        pass

    @abstractmethod
    def create_version(
        self,
        name: str,
        content: str,
        description: str = "",
        version: Optional[str] = None,
        created_by: str = "",
    ) -> Optional[PromptVersion]:
        """创建新的 Prompt 版本。"""
        pass

    @abstractmethod
    def get_version(self, name: str, version: str) -> Optional[PromptVersion]:
        """获取指定版本的 Prompt。"""
        pass

    @abstractmethod
    def list_versions(self, name: str) -> List[PromptVersion]:
        """列出指定 Prompt 的所有版本。"""
        pass

    @abstractmethod
    def set_current_version(self, name: str, version: str) -> bool:
        """设置当前激活版本。"""
        pass

    @abstractmethod
    def render(
        self,
        name: str,
        variables: Dict[str, Any],
        version: Optional[str] = None,
    ) -> Optional[str]:
        """渲染 Prompt 模板。

        参数:
            name: 模板名称
            variables: 变量字典
            version: 指定版本，为空时使用当前激活版本

        返回:
            渲染后的 Prompt 文本，模板不存在时返回 None
        """
        pass
