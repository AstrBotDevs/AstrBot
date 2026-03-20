from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from astrbot_sdk.clients._proxy import CapabilityProxy
from astrbot_sdk.testing import PluginHarness


def _write_overlay_test_plugin(plugin_dir: Path) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        """
_schema_version: 2
name: overlay_test_plugin
author: tests
version: 1.0.0
desc: request overlay regression tests

runtime:
  python: "3.12"

components:
  - class: main:OverlayPlugin
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "main.py").write_text(
        """
from astrbot_sdk import Context, MessageEvent, ScheduleContext, Star
from astrbot_sdk.decorators import on_event, on_schedule


class OverlayPlugin(Star):
    @on_schedule(interval_seconds=60)
    async def scheduled(self, ctx: Context, schedule: ScheduleContext) -> None:
        applied = await ctx.registry.set_handler_whitelist(["alpha", "beta"])
        current = await ctx.registry.get_handler_whitelist()
        await ctx.platform.send_by_id(
            "test",
            "schedule-target",
            f"{','.join(applied or [])}|{','.join(current or []) if current else 'none'}",
        )

    @on_event("llm_request")
    async def llm_overlay(self, event: MessageEvent) -> None:
        requested = await event.request_llm()
        current = await event.should_call_llm()
        await event.reply(f"{requested}:{current}")
""".lstrip(),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_schedule_handler_preserves_request_overlay_state(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "overlay_test_plugin"
    _write_overlay_test_plugin(plugin_dir)

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        payload = harness.build_event_payload(
            text="",
            event_type="schedule",
            request_id="req-schedule-1",
        )
        payload["schedule"] = {
            "schedule_id": "schedule-1",
            "plugin_id": "overlay_test_plugin",
            "handler_id": "overlay_test_plugin:scheduled",
            "trigger_kind": "interval",
            "interval_seconds": 60,
        }

        records = await harness.dispatch_event(payload, request_id="req-schedule-1")

    assert len(records) == 1
    assert records[0].kind == "chain"
    assert records[0].session == "test:private:schedule-target"
    assert records[0].chain is not None
    assert records[0].chain[0]["data"]["text"] == "alpha,beta|alpha,beta"


@pytest.mark.asyncio
async def test_non_message_event_preserves_request_overlay_state(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "overlay_test_plugin"
    _write_overlay_test_plugin(plugin_dir)

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        payload = harness.build_event_payload(
            text="trigger llm overlay",
            event_type="llm_request",
            request_id="req-llm-1",
        )

        records = await harness.dispatch_event(payload, request_id="req-llm-1")

    assert len(records) == 1
    assert records[0].kind == "text"
    assert records[0].text == "True:True"


class _RecordingPeer:
    def __init__(self) -> None:
        self.remote_peer = None
        self.remote_capability_map: dict[str, Any] = {}
        self.calls: list[tuple[str, dict[str, Any], str | None]] = []

    async def invoke(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        stream: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((capability, dict(payload), request_id))
        return {"ok": True, "stream": stream}


@pytest.mark.asyncio
async def test_capability_proxy_keeps_transport_ids_unique_while_forwarding_request_scope() -> (
    None
):
    peer = _RecordingPeer()
    proxy = CapabilityProxy(
        peer,
        caller_plugin_id="overlay_test_plugin",
        request_scope_id="req-parent-1",
    )

    await asyncio.gather(
        proxy.call("system.event.llm.get_state", {}),
        proxy.call("system.event.result.get", {}),
        proxy.call("platform.send", {"session": "test:private:user-1", "text": "hi"}),
    )

    assert peer.calls == [
        (
            "system.event.llm.get_state",
            {"_request_scope_id": "req-parent-1"},
            None,
        ),
        (
            "system.event.result.get",
            {"_request_scope_id": "req-parent-1"},
            None,
        ),
        (
            "platform.send",
            {"session": "test:private:user-1", "text": "hi"},
            None,
        ),
    ]
