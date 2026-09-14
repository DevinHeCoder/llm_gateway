"""
Prompt 管理层测试。
"""
from __future__ import annotations

import pytest

from src.prompt_manager import MemoryPromptManager, build_prompt_manager
from src.prompt_manager.ab_testing import ABTestManager, ABTestVariant


class TestMemoryPromptManager:
    """内存 Prompt 管理器测试。"""

    def test_create_prompt(self):
        """测试创建 Prompt。"""
        manager = MemoryPromptManager()
        template = manager.create_prompt(
            name="test_prompt",
            content="你是一个 {role}，请回答 {question}",
            description="测试 Prompt",
            tags=["test"],
        )
        assert template.name == "test_prompt"
        assert template.current_version == "1.0"
        assert len(template.versions) == 1
        assert "role" in template.versions[0].variables
        assert "question" in template.versions[0].variables

    def test_duplicate_prompt_raises(self):
        """测试重复创建 Prompt 抛出异常。"""
        manager = MemoryPromptManager()
        manager.create_prompt(name="dup", content="test")
        with pytest.raises(ValueError, match="已存在"):
            manager.create_prompt(name="dup", content="test2")

    def test_get_prompt(self):
        """测试获取 Prompt。"""
        manager = MemoryPromptManager()
        manager.create_prompt(name="test", content="test content")
        template = manager.get_prompt("test")
        assert template is not None
        assert template.name == "test"

    def test_get_missing_prompt(self):
        """测试获取不存在的 Prompt。"""
        manager = MemoryPromptManager()
        assert manager.get_prompt("nonexistent") is None

    def test_list_prompts(self):
        """测试列出 Prompt。"""
        manager = MemoryPromptManager()
        manager.create_prompt(name="p1", content="test1", tags=["a"])
        manager.create_prompt(name="p2", content="test2", tags=["b"])
        all_prompts = manager.list_prompts()
        assert len(all_prompts) == 2
        filtered = manager.list_prompts(tag="a")
        assert len(filtered) == 1
        assert filtered[0].name == "p1"

    def test_update_prompt(self):
        """测试更新 Prompt 元信息。"""
        manager = MemoryPromptManager()
        manager.create_prompt(name="test", content="test", description="old")
        manager.update_prompt(name="test", description="new", tags=["updated"])
        template = manager.get_prompt("test")
        assert template.description == "new"
        assert template.tags == ["updated"]

    def test_delete_prompt(self):
        """测试删除 Prompt。"""
        manager = MemoryPromptManager()
        manager.create_prompt(name="test", content="test")
        assert manager.delete_prompt("test") is True
        assert manager.get_prompt("test") is None

    def test_create_version(self):
        """测试创建新版本。"""
        manager = MemoryPromptManager()
        manager.create_prompt(name="test", content="v1 content")
        version = manager.create_version(name="test", content="v2 content", description="第二版")
        assert version is not None
        assert version.version == "1.1"
        template = manager.get_prompt("test")
        assert len(template.versions) == 2

    def test_create_version_with_explicit_number(self):
        """测试显式指定版本号。"""
        manager = MemoryPromptManager()
        manager.create_prompt(name="test", content="v1")
        version = manager.create_version(name="test", content="v2", version="2.0")
        assert version.version == "2.0"

    def test_list_versions(self):
        """测试列出版本。"""
        manager = MemoryPromptManager()
        manager.create_prompt(name="test", content="v1")
        manager.create_version(name="test", content="v2")
        versions = manager.list_versions("test")
        assert len(versions) == 2

    def test_set_current_version(self):
        """测试设置当前版本。"""
        manager = MemoryPromptManager()
        manager.create_prompt(name="test", content="v1")
        manager.create_version(name="test", content="v2", version="2.0")
        assert manager.set_current_version("test", "2.0") is True
        template = manager.get_prompt("test")
        assert template.current_version == "2.0"

    def test_render_prompt(self):
        """测试渲染 Prompt。"""
        manager = MemoryPromptManager()
        manager.create_prompt(
            name="test",
            content="你是一个 {role}，请回答：{question}",
        )
        result = manager.render(
            name="test",
            variables={"role": "程序员", "question": "什么是 Python？"},
        )
        assert result == "你是一个 程序员，请回答：什么是 Python？"

    def test_render_missing_variable_keeps_placeholder(self):
        """测试缺少变量时保持占位符。"""
        manager = MemoryPromptManager()
        manager.create_prompt(name="test", content="Hello {name}, welcome to {place}")
        result = manager.render(name="test", variables={"name": "Alice"})
        assert result == "Hello Alice, welcome to {place}"

    def test_render_specific_version(self):
        """测试渲染指定版本。"""
        manager = MemoryPromptManager()
        manager.create_prompt(name="test", content="v1: {msg}")
        manager.create_version(name="test", content="v2: {msg}", version="2.0")
        result_v1 = manager.render(name="test", variables={"msg": "hello"}, version="1.0")
        result_v2 = manager.render(name="test", variables={"msg": "hello"}, version="2.0")
        assert result_v1 == "v1: hello"
        assert result_v2 == "v2: hello"


class TestABTestManager:
    """A/B 测试管理器测试。"""

    def test_create_test(self):
        """测试创建 A/B 测试。"""
        manager = ABTestManager()
        variants = [
            ABTestVariant(name="A", prompt_name="p1", prompt_version="1.0", traffic_percent=50),
            ABTestVariant(name="B", prompt_name="p1", prompt_version="2.0", traffic_percent=50),
        ]
        test = manager.create_test(name="test_ab", variants=variants)
        assert test.id is not None
        assert test.name == "test_ab"
        assert test.status == "running"
        assert len(test.variants) == 2

    def test_invalid_traffic_percent_raises(self):
        """测试流量百分比之和不为 100 抛出异常。"""
        manager = ABTestManager()
        variants = [
            ABTestVariant(name="A", prompt_name="p1", prompt_version="1.0", traffic_percent=30),
            ABTestVariant(name="B", prompt_name="p1", prompt_version="2.0", traffic_percent=30),
        ]
        with pytest.raises(ValueError, match="100"):
            manager.create_test(name="test", variants=variants)

    def test_assign_variant_stable(self):
        """测试同一用户始终分配到同一变体。"""
        manager = ABTestManager()
        variants = [
            ABTestVariant(name="A", prompt_name="p1", prompt_version="1.0", traffic_percent=50),
            ABTestVariant(name="B", prompt_name="p1", prompt_version="2.0", traffic_percent=50),
        ]
        test = manager.create_test(name="test", variants=variants)
        v1 = manager.assign_variant(test.id, "user_123")
        v2 = manager.assign_variant(test.id, "user_123")
        assert v1.name == v2.name

    def test_assign_variant_paused_test(self):
        """测试已暂停的实验不分配变体。"""
        manager = ABTestManager()
        variants = [
            ABTestVariant(name="A", prompt_name="p1", prompt_version="1.0", traffic_percent=100),
        ]
        test = manager.create_test(name="test", variants=variants)
        manager.pause_test(test.id)
        assert manager.assign_variant(test.id, "user") is None

    def test_record_metric(self):
        """测试记录指标。"""
        manager = ABTestManager()
        variants = [
            ABTestVariant(name="A", prompt_name="p1", prompt_version="1.0", traffic_percent=50),
            ABTestVariant(name="B", prompt_name="p1", prompt_version="2.0", traffic_percent=50),
        ]
        test = manager.create_test(name="test", variants=variants)
        manager.record_metric(test.id, "A", latency_ms=100, tokens=50)
        manager.record_metric(test.id, "A", latency_ms=200, tokens=100)
        manager.record_metric(test.id, "B", latency_ms=150, tokens=75, error=True)

        result = manager.get_test_result(test.id)
        assert result is not None
        assert result.variant_results["A"]["requests"] == 2
        assert result.variant_results["B"]["requests"] == 1
        assert result.variant_results["B"]["errors"] == 1

    def test_pause_and_resume(self):
        """测试暂停和恢复实验。"""
        manager = ABTestManager()
        variants = [
            ABTestVariant(name="A", prompt_name="p1", prompt_version="1.0", traffic_percent=100),
        ]
        test = manager.create_test(name="test", variants=variants)
        assert manager.pause_test(test.id) is True
        assert manager.get_test(test.id).status == "paused"
        assert manager.resume_test(test.id) is True
        assert manager.get_test(test.id).status == "running"

    def test_complete_test(self):
        """测试完成实验。"""
        manager = ABTestManager()
        variants = [
            ABTestVariant(name="A", prompt_name="p1", prompt_version="1.0", traffic_percent=100),
        ]
        test = manager.create_test(name="test", variants=variants)
        assert manager.complete_test(test.id) is True
        assert manager.get_test(test.id).status == "completed"


class TestBuildPromptManager:
    """build_prompt_manager 工厂函数测试。"""

    def test_build_memory(self):
        """测试构建内存 Prompt 管理器。"""
        config = {"provider": "memory"}
        manager = build_prompt_manager(config)
        assert isinstance(manager, MemoryPromptManager)

    def test_default_provider(self):
        """测试默认 provider（sqlite）。"""
        from src.prompt_manager import SQLitePromptManager
        config = {}
        manager = build_prompt_manager(config)
        assert isinstance(manager, SQLitePromptManager)
