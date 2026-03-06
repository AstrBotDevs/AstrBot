from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.astr_main_agent import _apply_extension_hub_tools
from astrbot.core.extensions.llm_tools import (
    EXTENSION_DENY_ALL_TOOL,
    EXTENSION_DENY_TOOL,
    EXTENSION_SEARCH_TOOL,
)
from astrbot.core.extensions.model import InstallResultStatus
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context


def test_apply_extension_hub_tools_enabled() -> None:
    req = ProviderRequest(prompt="hi")
    req.func_tool = ToolSet()
    cfg = {"provider_settings": {"extension_install": {"enable": False}}}

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "astrbot.core.astr_main_agent.sp.get",
            lambda *args, **kwargs: [],
        )
        _apply_extension_hub_tools(req, cfg)

    names = req.func_tool.names()
    assert "astrbot_extension_search" in names
    assert "astrbot_extension_install" in names
    assert "astrbot_extension_confirm" not in names
    assert "astrbot_extension_deny" in names
    assert "astrbot_extension_deny_all" in names


def test_apply_extension_hub_tools_disabled() -> None:
    req = ProviderRequest(prompt="hi")
    req.func_tool = ToolSet()
    cfg = {"provider_settings": {}}

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "astrbot.core.astr_main_agent.sp.get",
            lambda *args, **kwargs: [
                "astrbot.builtin_stars.builtin_extension_hub.main"
            ],
        )
        _apply_extension_hub_tools(req, cfg)

    assert "astrbot_extension_search" not in req.func_tool.names()


def test_apply_extension_hub_tools_disabled_with_provider_settings_only() -> None:
    req = ProviderRequest(prompt="hi")
    req.func_tool = ToolSet()
    provider_settings = {"extension_install": {"enable": True}}

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "astrbot.core.astr_main_agent.sp.get",
            lambda *args, **kwargs: [],
        )
        _apply_extension_hub_tools(req, provider_settings)

    assert "astrbot_extension_search" in req.func_tool.names()


def test_extension_search_tool_exposes_optional_limit_for_bot_control() -> None:
    params = EXTENSION_SEARCH_TOOL.parameters
    assert "limit" in params["properties"]
    assert "choose" in EXTENSION_SEARCH_TOOL.description.lower()


@pytest.mark.asyncio
async def test_extension_deny_tool_calls_conversation_reject_without_admin_check(
    monkeypatch,
) -> None:
    orchestrator = SimpleNamespace(
        deny_for_conversation=AsyncMock(
            return_value=SimpleNamespace(
                status=InstallResultStatus.DENIED,
                message="operation rejected",
                operation_id="op-1",
                data={"count": 1},
            )
        )
    )
    monkeypatch.setattr(
        "astrbot.core.extensions.llm_tools.get_extension_orchestrator",
        lambda _: orchestrator,
    )
    event = MagicMock(spec=AstrMessageEvent)
    event.unified_msg_origin = "conv-1"
    event.get_sender_id.return_value = "u1"
    event.role = "member"
    plugin_context = MagicMock(spec=Context)
    context = ContextWrapper(
        AstrAgentContext(context=plugin_context, event=event),
    )

    result = await EXTENSION_DENY_TOOL.call(context)
    payload = json.loads(result)

    assert payload["status"] == "denied"
    assert payload["data"]["count"] == 1
    orchestrator.deny_for_conversation.assert_awaited_once()


@pytest.mark.asyncio
async def test_extension_deny_all_tool_calls_global_reject() -> None:
    orchestrator = SimpleNamespace(
        deny_all=AsyncMock(
            return_value=SimpleNamespace(
                status=InstallResultStatus.DENIED,
                message="rejected 2 operations",
                operation_id=None,
                data={"count": 2},
            )
        )
    )
    event = MagicMock(spec=AstrMessageEvent)
    event.unified_msg_origin = "conv-1"
    event.get_sender_id.return_value = "u1"
    event.role = "admin"
    plugin_context = MagicMock(spec=Context)
    context = ContextWrapper(
        AstrAgentContext(context=plugin_context, event=event),
    )

    monkeypatch_target = "astrbot.core.extensions.llm_tools.get_extension_orchestrator"
    from unittest.mock import patch

    with patch(monkeypatch_target, return_value=orchestrator):
        result = await EXTENSION_DENY_ALL_TOOL.call(context, scope="all")

    payload = json.loads(result)
    assert payload["status"] == "denied"
    assert payload["data"]["count"] == 2
    orchestrator.deny_all.assert_awaited_once_with(
        actor_id="u1",
        actor_role="admin",
        kind=None,
        reason="rejected by agent",
    )
