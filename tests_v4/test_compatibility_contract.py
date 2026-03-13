"""Compatibility contract tests for the controlled ``astrbot`` facade."""

from __future__ import annotations

from importlib import import_module

import pytest

LEVEL_ONE_MODULES = [
    "astrbot.api",
    "astrbot.api.all",
    "astrbot.api.components",
    "astrbot.api.components.command",
    "astrbot.api.message_components",
    "astrbot.api.event",
    "astrbot.api.event.filter",
    "astrbot.api.star",
    "astrbot.api.platform",
    "astrbot.api.provider",
    "astrbot.api.util",
]

LEVEL_TWO_MODULES = [
    "astrbot.core",
    "astrbot.core.config",
    "astrbot.core.config.astrbot_config",
    "astrbot.core.message",
    "astrbot.core.message.components",
    "astrbot.core.message.message_event_result",
    "astrbot.core.agent",
    "astrbot.core.agent.message",
    "astrbot.core.db",
    "astrbot.core.db.po",
    "astrbot.core.platform",
    "astrbot.core.platform.astr_message_event",
    "astrbot.core.platform.astrbot_message",
    "astrbot.core.platform.message_type",
    "astrbot.core.platform.platform_metadata",
    "astrbot.core.platform.register",
    "astrbot.core.platform.sources.aiocqhttp",
    "astrbot.core.provider",
    "astrbot.core.provider.entities",
    "astrbot.core.provider.provider",
    "astrbot.core.utils",
    "astrbot.core.utils.astrbot_path",
    "astrbot.core.utils.session_waiter",
]


@pytest.mark.parametrize("module_name", LEVEL_ONE_MODULES)
def test_level_one_legacy_facade_modules_import(module_name: str):
    """一级 compat 合同中的旧公开模块必须始终可导入。"""
    assert import_module(module_name) is not None


@pytest.mark.parametrize("module_name", LEVEL_TWO_MODULES)
def test_level_two_legacy_facade_modules_import(module_name: str):
    """二级 compat 合同中的高频深路径必须始终可导入。"""
    assert import_module(module_name) is not None


def test_level_two_html_renderer_stays_loud_fail():
    """未实现的旧 HTML 渲染系统应保持显式失败，而不是静默伪兼容。"""
    from astrbot.core import html_renderer

    with pytest.raises(NotImplementedError, match="html_renderer"):
        html_renderer()
