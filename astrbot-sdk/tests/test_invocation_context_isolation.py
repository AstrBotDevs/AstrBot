"""
针对 caller_plugin_scope / invocation_context 的并发隔离单元测试。
覆盖：
  - 基本作用域绑定与清理
  - 嵌套作用域
  - 并发 Task 下 ContextVar 互不干扰
  - 作用域结束后正确 reset
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from astrbot_sdk._internal.invocation_context import (
    bind_caller_plugin_id,
    caller_plugin_scope,
    current_caller_plugin_id,
    reset_caller_plugin_id,
)


# ── 基本绑定与清理 ─────────────────────────────────────────────────


def test_default_is_none() -> None:
    assert current_caller_plugin_id() is None


def test_scope_sets_and_resets() -> None:
    assert current_caller_plugin_id() is None
    with caller_plugin_scope("plugin_a"):
        assert current_caller_plugin_id() == "plugin_a"
    # 作用域结束后必须恢复为 None
    assert current_caller_plugin_id() is None


def test_scope_resets_to_previous_value() -> None:
    token = bind_caller_plugin_id("outer")
    try:
        assert current_caller_plugin_id() == "outer"
        with caller_plugin_scope("inner"):
            assert current_caller_plugin_id() == "inner"
        assert current_caller_plugin_id() == "outer"
    finally:
        reset_caller_plugin_id(token)


def test_scope_with_none_clears_id() -> None:
    token = bind_caller_plugin_id("plugin_x")
    try:
        with caller_plugin_scope(None):
            assert current_caller_plugin_id() is None
        assert current_caller_plugin_id() == "plugin_x"
    finally:
        reset_caller_plugin_id(token)


def test_empty_string_normalized_to_none() -> None:
    token = bind_caller_plugin_id("  ")  # 空白字符串 → None
    try:
        assert current_caller_plugin_id() is None
    finally:
        reset_caller_plugin_id(token)


# ── 嵌套作用域 ────────────────────────────────────────────────────


def test_nested_scopes_restore_correctly() -> None:
    with caller_plugin_scope("a"):
        assert current_caller_plugin_id() == "a"
        with caller_plugin_scope("b"):
            assert current_caller_plugin_id() == "b"
            with caller_plugin_scope("c"):
                assert current_caller_plugin_id() == "c"
            assert current_caller_plugin_id() == "b"
        assert current_caller_plugin_id() == "a"
    assert current_caller_plugin_id() is None


# ── 并发 Task 隔离 ────────────────────────────────────────────────


def test_concurrent_tasks_do_not_share_context() -> None:
    """不同 asyncio Task 中的 ContextVar 互不干扰。"""

    results: dict[str, str | None] = {}

    async def task_fn(plugin_id: str, delay: float) -> None:
        with caller_plugin_scope(plugin_id):
            await asyncio.sleep(delay)
            results[plugin_id] = current_caller_plugin_id()

    async def run() -> None:
        # 两个 Task 并发执行，delay 设置使它们交叉运行
        await asyncio.gather(
            task_fn("plugin_alpha", 0.01),
            task_fn("plugin_beta", 0.001),
        )

    asyncio.run(run())

    assert results["plugin_alpha"] == "plugin_alpha"
    assert results["plugin_beta"] == "plugin_beta"


def test_child_task_inherits_parent_context_but_isolated() -> None:
    """子 Task 继承父 Task 的 ContextVar 快照，但修改不会影响父 Task。"""

    parent_values: list[str | None] = []
    child_values: list[str | None] = []

    async def child_task() -> None:
        # 子 Task 在父 Task 的 scope 内创建，继承 "parent_plugin" 快照
        child_values.append(current_caller_plugin_id())
        # 子 Task 内修改不应该影响父 Task
        with caller_plugin_scope("child_plugin"):
            child_values.append(current_caller_plugin_id())
        child_values.append(current_caller_plugin_id())

    async def parent_task() -> None:
        with caller_plugin_scope("parent_plugin"):
            parent_values.append(current_caller_plugin_id())
            task = asyncio.create_task(child_task())
            await asyncio.sleep(0.01)
            parent_values.append(current_caller_plugin_id())
            await task
            parent_values.append(current_caller_plugin_id())

    asyncio.run(parent_task())

    # 子 Task 继承了父 Task 的初始值
    assert child_values[0] == "parent_plugin"
    assert child_values[1] == "child_plugin"
    assert child_values[2] == "parent_plugin"

    # 父 Task 全程不受子 Task 影响
    assert all(v == "parent_plugin" for v in parent_values)


def test_scope_exception_still_resets() -> None:
    """作用域内抛出异常时，ContextVar 依然被正确 reset。"""
    assert current_caller_plugin_id() is None
    try:
        with caller_plugin_scope("error_plugin"):
            assert current_caller_plugin_id() == "error_plugin"
            raise RuntimeError("intentional error")
    except RuntimeError:
        pass
    assert current_caller_plugin_id() is None
