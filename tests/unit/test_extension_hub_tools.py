from __future__ import annotations

from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_main_agent import _apply_extension_hub_tools
from astrbot.core.provider.entities import ProviderRequest


def test_apply_extension_hub_tools_enabled() -> None:
    req = ProviderRequest(prompt="hi")
    req.func_tool = ToolSet()
    cfg = {"provider_settings": {"extension_install": {"enable": True}}}

    _apply_extension_hub_tools(req, cfg)

    names = req.func_tool.names()
    assert "astrbot_extension_search" in names
    assert "astrbot_extension_install" in names
    assert "astrbot_extension_confirm" not in names
    assert "astrbot_extension_deny" not in names


def test_apply_extension_hub_tools_disabled() -> None:
    req = ProviderRequest(prompt="hi")
    req.func_tool = ToolSet()
    cfg = {"provider_settings": {"extension_install": {"enable": False}}}

    _apply_extension_hub_tools(req, cfg)

    assert "astrbot_extension_search" not in req.func_tool.names()


def test_apply_extension_hub_tools_disabled_with_provider_settings_only() -> None:
    req = ProviderRequest(prompt="hi")
    req.func_tool = ToolSet()
    provider_settings = {"extension_install": {"enable": False}}

    _apply_extension_hub_tools(req, provider_settings)

    assert "astrbot_extension_search" not in req.func_tool.names()
