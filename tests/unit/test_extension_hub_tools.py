from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.core.extensions.runtime as extension_runtime
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.astr_main_agent import _apply_extension_hub_tools
from astrbot.core.extensions.llm_tools import (
    EXTENSION_DENY_ALL_TOOL,
    EXTENSION_DENY_TOOL,
    EXTENSION_INSTALL_TOOL,
    EXTENSION_SEARCH_TOOL,
)
from astrbot.core.extensions.model import InstallResultStatus
from astrbot.core.extensions.model import ExtensionKind
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context


def test_apply_extension_hub_tools_enabled() -> None:
    req = ProviderRequest(prompt="hi")
    req.func_tool = ToolSet()
    cfg = {"provider_settings": {"extension_install": {"enable": True}}}

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


def test_apply_extension_hub_tools_respects_extension_install_enable_false() -> None:
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
    assert "astrbot_extension_search" not in names
    assert "astrbot_extension_install" not in names
    assert "astrbot_extension_deny" not in names
    assert "astrbot_extension_deny_all" not in names


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


def test_get_extension_orchestrator_scopes_cache_by_session(monkeypatch) -> None:
    default_cfg = {
        "provider_settings": {
            "extension_install": {
                "default_mode": "secure",
                "allowed_roles": ["admin"],
            }
        }
    }
    session_cfg = {
        "provider_settings": {
            "extension_install": {
                "default_mode": "open",
                "allowed_roles": ["admin"],
            }
        }
    }
    context = SimpleNamespace(
        get_config=lambda umo=None: session_cfg if umo == "conv-1" else default_cfg,
        get_db=lambda: object(),
    )

    monkeypatch.setattr(
        extension_runtime,
        "PluginAdapter",
        lambda ctx: SimpleNamespace(
            kind=ExtensionKind.PLUGIN,
            provider="git",
        ),
    )
    monkeypatch.setattr(
        extension_runtime,
        "SkillAdapter",
        lambda ctx: SimpleNamespace(
            kind=ExtensionKind.SKILL,
            provider="local",
        ),
    )
    monkeypatch.setattr(
        extension_runtime,
        "McpTodoAdapter",
        lambda: SimpleNamespace(
            kind=ExtensionKind.MCP,
            provider="todo",
        ),
    )
    monkeypatch.setattr(
        extension_runtime,
        "_ensure_cleanup_task",
        lambda *args, **kwargs: None,
    )

    session_orchestrator = extension_runtime.get_extension_orchestrator(
        context,
        umo="conv-1",
    )
    default_orchestrator = extension_runtime.get_extension_orchestrator(context)

    assert session_orchestrator is not default_orchestrator
    assert session_orchestrator.policy_engine.config.mode == "open"
    assert default_orchestrator.policy_engine.config.mode == "secure"


def test_get_extension_orchestrator_reuses_single_cleanup_task(monkeypatch) -> None:
    default_cfg = {
        "provider_settings": {
            "extension_install": {
                "default_mode": "secure",
                "allowed_roles": ["admin"],
            }
        }
    }
    context = SimpleNamespace(
        get_config=lambda umo=None: default_cfg,
        get_db=lambda: object(),
    )

    monkeypatch.setattr(
        extension_runtime,
        "PluginAdapter",
        lambda ctx: SimpleNamespace(kind=ExtensionKind.PLUGIN, provider="git"),
    )
    monkeypatch.setattr(
        extension_runtime,
        "SkillAdapter",
        lambda ctx: SimpleNamespace(kind=ExtensionKind.SKILL, provider="local"),
    )
    monkeypatch.setattr(
        extension_runtime,
        "McpTodoAdapter",
        lambda: SimpleNamespace(kind=ExtensionKind.MCP, provider="todo"),
    )

    created_tasks: list[str | None] = []

    class _Loop:
        def create_task(self, coro, name=None):
            coro.close()
            task = MagicMock(spec=asyncio.Task)
            task.done.return_value = False
            created_tasks.append(name)
            return task

    monkeypatch.setattr(extension_runtime.asyncio, "get_running_loop", lambda: _Loop())

    extension_runtime.get_extension_orchestrator(context, umo="conv-1")
    extension_runtime.get_extension_orchestrator(context, umo="conv-2")

    assert created_tasks == ["astrbot-extension-pending-cleanup"]


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
        lambda *args, **kwargs: orchestrator,
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


@pytest.mark.asyncio
async def test_extension_install_tool_exposes_configured_confirmation_keywords(
    monkeypatch,
) -> None:
    orchestrator = SimpleNamespace(
        install=AsyncMock(
            return_value=SimpleNamespace(
                status=InstallResultStatus.PENDING,
                message="confirmation required",
                operation_id="op-1",
                data={
                    "candidate_name": "demo-plugin",
                    "candidate_description": "demo desc",
                },
            )
        )
    )
    monkeypatch.setattr(
        "astrbot.core.extensions.llm_tools.get_extension_orchestrator",
        lambda *args, **kwargs: orchestrator,
    )
    monkeypatch.setattr(
        "astrbot.core.extensions.llm_tools.check_admin_permission",
        lambda *args, **kwargs: None,
    )
    event = MagicMock(spec=AstrMessageEvent)
    event.unified_msg_origin = "conv-1"
    event.get_sender_id.return_value = "u1"
    event.role = "admin"
    plugin_context = MagicMock(spec=Context)
    plugin_context.get_config.return_value = {
        "provider_settings": {
            "extension_install": {
                "confirm_keyword": "点头",
                "deny_keyword": "取消",
            }
        }
    }
    context = ContextWrapper(
        AstrAgentContext(context=plugin_context, event=event),
    )

    result = await EXTENSION_INSTALL_TOOL.call(
        context, kind="plugin", target="https://github.com/example/demo"
    )
    payload = json.loads(result)

    assert payload["status"] == "pending"
    assert payload["confirm_keyword"] == "点头"
    assert payload["deny_keyword"] == "取消"
    assert "点头" in payload["hint"]
    assert "取消" in payload["hint"]
