"""
Registry 可插拔注册中心测试。
"""
from __future__ import annotations

import pytest

from src.common.exceptions import RegistryError
from src.common.registry import Registry


class TestRegistry:
    """Registry 基础功能测试。"""

    def test_register_and_get(self):
        """测试注册和获取实现类。"""
        reg = Registry(name="test", base_type=object)

        @reg.register("impl_a")
        class ImplA:
            pass

        assert reg.has("impl_a")
        assert reg.get("impl_a") is ImplA
        assert "impl_a" in reg.names

    def test_create_instance(self):
        """测试创建实例。"""
        reg = Registry(name="test", base_type=object)

        @reg.register("with_args")
        class WithArgs:
            def __init__(self, x: int, y: str = "default"):
                self.x = x
                self.y = y

        instance = reg.create("with_args", x=42, y="hello")
        assert instance.x == 42
        assert instance.y == "hello"

    def test_duplicate_register_raises(self):
        """测试重复注册抛出异常。"""
        reg = Registry(name="test", base_type=object)

        @reg.register("dup")
        class Impl1:
            pass

        with pytest.raises(RegistryError, match="已注册"):
            @reg.register("dup")
            class Impl2:
                pass

    def test_get_unregistered_raises(self):
        """测试获取未注册实现抛出异常。"""
        reg = Registry(name="test", base_type=object)
        with pytest.raises(RegistryError, match="未注册"):
            reg.get("nonexistent")

    def test_default_implementation(self):
        """测试默认实现。"""
        reg = Registry(name="test", base_type=object, default="default_impl")

        @reg.register("default_impl")
        class DefaultImpl:
            pass

        assert reg.get() is DefaultImpl
        assert reg.create() is not None

    def test_set_default(self):
        """测试设置默认实现。"""
        reg = Registry(name="test", base_type=object)

        @reg.register("a")
        class ImplA:
            pass

        reg.set_default("a")
        assert reg.get() is ImplA

    def test_set_default_unregistered_raises(self):
        """测试设置未注册的默认实现抛出异常。"""
        reg = Registry(name="test", base_type=object)
        with pytest.raises(RegistryError):
            reg.set_default("nonexistent")

    def test_type_check(self):
        """测试类型校验。"""
        class Base:
            pass

        class Sub(Base):
            pass

        class NotSub:
            pass

        reg = Registry(name="test", base_type=Base)

        @reg.register("sub")
        class ImplSub(Sub):
            pass

        assert reg.has("sub")

        with pytest.raises(RegistryError, match="不是"):
            @reg.register("not_sub")
            class ImplNotSub(NotSub):
                pass
