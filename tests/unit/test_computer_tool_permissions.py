import json
from types import SimpleNamespace

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.tools.computer_tools.shipyard_neo.browser import BrowserExecTool
from astrbot.core.tools.computer_tools.shipyard_neo.neo_skills import (
    GetExecutionHistoryTool,
)
from tests.fixtures.auth import attach_authorized_tool_context


class _FakeBrowser:
    async def exec(self, **kwargs):
        return {
            "ok": True,
            "cmd": kwargs["cmd"],
        }


class _FakeSandbox:
    async def get_execution_history(self, **kwargs):
        return {
            "items": [],
            "limit": kwargs["limit"],
        }


def _make_run_context(
    role: str = "member",
    computer_runtime: object | None = None,
) -> ContextWrapper:
    config_holder = SimpleNamespace(
        get_config=lambda umo: {  # noqa: ARG005
            "provider_settings": {}
        },
        computer_runtime=computer_runtime,
    )
    event = SimpleNamespace(
        role=role,
        unified_msg_origin="qq_official:friend:user-1",
        get_sender_id=lambda: "user-1",
    )
    attach_authorized_tool_context(
        event,
        config_holder,
        "tool.browser_control",
        "extension.manage",
    )
    astr_ctx = SimpleNamespace(context=config_holder, event=event)
    return ContextWrapper(context=astr_ctx)


@pytest.mark.asyncio
async def test_browser_tool_direct_component_call_is_not_gated_by_legacy_config(
    monkeypatch,
):
    async def _fake_get_booter(_ctx, _session_id):
        return SimpleNamespace(browser=_FakeBrowser())

    result = await BrowserExecTool().call(
        _make_run_context(
            computer_runtime=SimpleNamespace(get_booter=_fake_get_booter),
        ),
        cmd="open https://example.com",
    )

    assert json.loads(result)["ok"] is True


@pytest.mark.asyncio
async def test_neo_skill_tool_direct_component_call_is_not_gated_by_legacy_config(
    monkeypatch,
):
    async def _fake_get_booter(_ctx, _session_id):
        return SimpleNamespace(
            bay_client=object(),
            sandbox=_FakeSandbox(),
        )

    result = await GetExecutionHistoryTool().call(
        _make_run_context(
            computer_runtime=SimpleNamespace(get_booter=_fake_get_booter),
        ),
        limit=5,
    )

    payload = json.loads(result)
    assert payload["items"] == []
    assert payload["limit"] == 5


@pytest.mark.asyncio
async def test_browser_tool_without_runtime_context_is_not_gated_by_legacy_config():
    result = await BrowserExecTool().call(
        _make_run_context(),
        cmd="open https://example.com",
    )

    assert "Error executing browser command" in result
