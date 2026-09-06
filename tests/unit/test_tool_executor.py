"""Unit tests for astrbot.core.agent.tool_executor: BaseFunctionToolExecutor abstract signature."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor


class TestBaseFunctionToolExecutor:
    """BaseFunctionToolExecutor cannot be instantiated; metachecks on the ABC."""

    def test_cannot_instantiate_abstract(self):
        """BaseFunctionToolExecutor cannot be instantiated directly (abstract)."""
        with pytest.raises(TypeError, match="abstract"):
            BaseFunctionToolExecutor()

    def test_execute_is_abstract_classmethod(self):
        """execute is both a classmethod and abstractmethod."""
        assert hasattr(BaseFunctionToolExecutor.execute, "__isabstractmethod__")
        assert BaseFunctionToolExecutor.execute.__isabstractmethod__ is True

    def test_execute_is_classmethod_descriptor(self):
        """execute is a classmethod (has __func__)."""
        assert hasattr(BaseFunctionToolExecutor.execute, "__func__")

    def test_concrete_subclass_must_implement_execute(self):
        """A subclass without execute is still abstract."""
        class Missing(BaseFunctionToolExecutor):
            pass
        with pytest.raises(TypeError, match="abstract"):
            Missing()

    def test_concrete_subclass_with_execute_can_instantiate(self):
        """A subclass that implements execute can be instantiated."""
        class Concrete(BaseFunctionToolExecutor):
            @classmethod
            async def execute(cls, tool, run_context, **tool_args):
                yield "result"

        instance = Concrete()
        assert isinstance(instance, BaseFunctionToolExecutor)

    def test_execute_signature_matches(self):
        """execute has the expected parameter names."""
        import inspect
        sig = inspect.signature(
            BaseFunctionToolExecutor.__dict__["execute"].__func__
        )
        param_names = list(sig.parameters.keys())
        assert "tool" in param_names
        assert "run_context" in param_names

    def test_execute_tool_parameter_type_hint(self):
        """The tool parameter is annotated as FunctionTool."""
        import inspect
        sig = inspect.signature(
            BaseFunctionToolExecutor.__dict__["execute"].__func__
        )
        tool_param = sig.parameters["tool"]
        assert tool_param.annotation is FunctionTool

    def test_execute_run_context_type_hint(self):
        """The run_context parameter is annotated as ContextWrapper."""
        import inspect
        sig = inspect.signature(
            BaseFunctionToolExecutor.__dict__["execute"].__func__
        )
        ctx_param = sig.parameters["run_context"]
        origin = getattr(ctx_param.annotation, "__origin__", None)
        assert origin is ContextWrapper

    def test_execute_returns_async_generator(self):
        """execute return annotation is AsyncGenerator."""
        import inspect
        sig = inspect.signature(
            BaseFunctionToolExecutor.__dict__["execute"].__func__
        )
        return_annotation = sig.return_annotation
        assert "AsyncGenerator" in str(return_annotation)

    def test_concrete_subclass_execute_yields(self):
        """A concrete subclass can actually yield values."""
        class Tester(BaseFunctionToolExecutor):
            @classmethod
            async def execute(cls, tool, run_context, **tool_args):
                yield "step1"
                yield "step2"

        import asyncio
        tool = FunctionTool(name="test", description="test")
        ctx = ContextWrapper(context="test")
        gen = Tester.execute(tool, ctx)
        results = asyncio.run(async_collect(gen))
        assert results == ["step1", "step2"]

    def test_concrete_subclass_generic_parameter(self):
        """Subclass can specialize the generic type parameter."""
        class TypedExecutor(BaseFunctionToolExecutor[str]):
            @classmethod
            async def execute(cls, tool, run_context, **tool_args):
                yield run_context.context

        import asyncio
        tool = FunctionTool(name="t", description="t")
        ctx = ContextWrapper(context="hello_generic")
        gen = TypedExecutor.execute(tool, ctx)
        results = asyncio.run(async_collect(gen))
        assert results == ["hello_generic"]

    def test_subclass_with_kwargs_passthrough(self):
        """execute passes **tool_args through."""
        class KwargsExecutor(BaseFunctionToolExecutor):
            @classmethod
            async def execute(cls, tool, run_context, **tool_args):
                yield tool_args

        import asyncio
        tool = FunctionTool(name="t", description="t")
        ctx = ContextWrapper(context="ctx")
        gen = KwargsExecutor.execute(tool, ctx, x=1, y="two")
        results = asyncio.run(async_collect(gen))
        assert results[0] == {"x": 1, "y": "two"}


async def async_collect(async_gen):
    """Collect all items from an async generator into a list."""
    results = []
    async for item in async_gen:
        results.append(item)
    return results
