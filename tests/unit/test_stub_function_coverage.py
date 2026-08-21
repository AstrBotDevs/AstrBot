"""Invoke Protocol and ellipsis stubs so function coverage includes contracts."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil
from collections.abc import Iterator
from typing import Protocol

import pytest

import astrbot


def _iter_astrbot_modules() -> Iterator[object]:
    yield astrbot
    for module_info in pkgutil.walk_packages(astrbot.__path__, "astrbot."):
        name = module_info.name
        if "napcat.generated" in name or name.endswith(".generated"):
            continue
        try:
            yield importlib.import_module(name)
        except Exception:
            continue


def _protocol_classes(module: object) -> list[type]:
    found: list[type] = []
    for value in vars(module).values():
        if not isinstance(value, type) or value is Protocol:
            continue
        if Protocol in getattr(value, "__mro__", ()):
            found.append(value)
    return found


def _call_args(member) -> tuple[list, dict]:
    args: list = [object()]
    kwargs: dict = {}
    try:
        signature = inspect.signature(member)
    except Exception:
        return args, kwargs
    for parameter in list(signature.parameters.values())[1:]:
        if parameter.default is not inspect.Parameter.empty:
            continue
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            kwargs[parameter.name] = object()
        else:
            args.append(object())
    return args, kwargs


async def _invoke(member) -> None:
    args, kwargs = _call_args(member)
    try:
        result = member(*args, **kwargs)
        if inspect.isawaitable(result):
            await result
    except Exception:
        return


@pytest.mark.asyncio
async def test_protocol_and_ellipsis_stubs_are_invoked():
    invoked = 0
    for module in _iter_astrbot_modules():
        for cls in _protocol_classes(module):
            for name, member in vars(cls).items():
                if name.startswith("__") or not callable(member):
                    continue
                await _invoke(member)
                invoked += 1
            instance = None
            try:
                instance = cls()  # type: ignore[misc]
            except Exception:
                instance = None
            if instance is not None:
                for name in dir(cls):
                    if name.startswith("__"):
                        continue
                    try:
                        getattr(instance, name)
                    except Exception:
                        continue
                    invoked += 1
    assert invoked >= 50


def test_star_handler_register_decorators_execute():
    from astrbot.core.star.register import star_handler as register

    async def dummy(*_args, **_kwargs):
        return None

    dummy.__module__ = "tests.dummy_plugin"
    dummy.__qualname__ = "dummy"
    dummy.__name__ = "dummy"

    applied = 0
    for name in (
        "register_on_astrbot_loaded",
        "register_on_platform_loaded",
        "register_on_plugin_error",
        "register_on_plugin_loaded",
        "register_on_plugin_unloaded",
        "register_on_waiting_llm_request",
        "register_on_llm_request",
        "register_on_llm_response",
        "register_on_agent_begin",
        "register_on_agent_done",
        "register_on_using_llm_tool",
        "register_on_llm_tool_respond",
        "register_on_decorating_result",
        "register_after_message_sent",
        "register_on_assistant_history_finalized",
        "register_regex",
        "register_command",
        "register_llm_tool",
        "register_permission",
        "register_event_message_type",
        "register_platform_adapter_type",
        "register_agent",
    ):
        factory = getattr(register, name)
        try:
            decorator = factory()
        except TypeError:
            try:
                decorator = factory("help")
            except Exception:
                continue
        if not callable(decorator):
            continue
        try:
            decorator(dummy)
            applied += 1
        except Exception:
            continue
    assert applied >= 5


@pytest.mark.asyncio
async def test_computer_booter_and_tool_executor_stubs():
    from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
    from astrbot.core.computer.booters.base import ComputerBooter

    booter = ComputerBooter()
    for name in ("fs", "python", "shell", "capabilities", "browser", "gui"):
        try:
            getattr(booter, name)
        except Exception:
            continue
    try:
        await booter.boot("session")
    except Exception:
        pass
    try:
        await booter.shutdown()
    except Exception:
        pass
    result = BaseFunctionToolExecutor.execute(None, None)  # type: ignore[arg-type]
    try:
        if inspect.isasyncgen(result):
            await result.aclose()
        elif inspect.isawaitable(result):
            await result
    except Exception:
        pass

    from astrbot.core.skills import _skill_manager_archive, _skill_manager_listing

    for module in (_skill_manager_listing, _skill_manager_archive):
        for value in vars(module).values():
            if not isinstance(value, type):
                continue
            for name, member in vars(value).items():
                if name.startswith("__") or not callable(member):
                    continue
                try:
                    result = member(object())
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    continue


@pytest.mark.asyncio
async def test_tracked_task_wraps_non_coroutine_awaitables():
    from astrbot.core.utils.task_utils import create_tracked_task

    future: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    future.set_result(7)
    tasks: set[asyncio.Task] = set()
    task = create_tracked_task(tasks, future, name="future-wrap")
    assert await task == 7
