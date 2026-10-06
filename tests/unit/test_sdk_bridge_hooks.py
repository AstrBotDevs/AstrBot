from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from astrbot.core.message.components import Plain as CorePlain
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.star.sdk_bridge import SDKPluginBridge
from astrbot.core.star.star_handler import EventType, star_handlers_registry

from tests.unit.test_sdk_bridge import FakeCoreEvent, FakeKVStore


def write_hook_plugin(
    plugin_root: Path,
    *,
    capabilities: list[dict],
    body: str,
) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "name": f"plugin_{plugin_root.name}",
                "desc": "hook bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:TestPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {"required": capabilities},
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(body, "utf-8")


HOOK_PLUGIN = """
from astrbot_sdk import MessageEvent, Plugin, hooks
from astrbot_sdk.hooks import LLMRequest, MessageResult
from astrbot_sdk.message_components import Plain

class TestPlugin(Plugin):
    @hooks.llm_request()
    async def catify(self, event: MessageEvent | None, request: LLMRequest) -> None:
        request.system_prompt += " Answer like a cat."

    @hooks.message_result()
    async def sign(
        self,
        event: MessageEvent | None,
        result: MessageResult,
    ) -> None:
        result.chain.append(Plain(" [signed]"))

    @hooks.message_sent()
    async def log_sent(self, event: MessageEvent | None) -> None:
        await self.ctx.storage.set("sent", "yes")
"""


async def run_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capabilities: list[dict],
):
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )
    plugin_root = tmp_path / "hook_e2e"
    write_hook_plugin(plugin_root, capabilities=capabilities, body=HOOK_PLUGIN)
    context = MagicMock()
    bridge = SDKPluginBridge(plugin_root, context)
    await bridge.start()
    return plugin_root, bridge


@pytest.mark.asyncio
async def test_hooks_modify_applied_when_granted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root, bridge = await run_hooks(
        tmp_path,
        monkeypatch,
        capabilities=[
            {"id": "llm.observe"},
            {"id": "llm.modify"},
            {"id": "message.observe"},
            {"id": "message.modify"},
        ],
    )
    try:
        # llm_request: system prompt is extended in place.
        event = FakeCoreEvent("hi")
        req = ProviderRequest(prompt="hi", system_prompt="Base.")
        await call_event_hook(event, EventType.OnLLMRequestEvent, req)
        assert req.system_prompt == "Base. Answer like a cat."

        # message_result: a Plain segment is appended to the outbound chain.
        event.set_result(MessageEventResult(chain=[CorePlain("hello")]))
        await call_event_hook(event, EventType.OnDecoratingResultEvent)
        chain_text = "".join(
            c.text for c in event.get_result().chain if hasattr(c, "text")
        )
        assert chain_text == "hello [signed]"
    finally:
        await bridge.stop()


@pytest.mark.asyncio
async def test_hook_writes_dropped_without_modify_grant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root, bridge = await run_hooks(
        tmp_path,
        monkeypatch,
        capabilities=[
            {"id": "llm.observe"},
            {"id": "message.observe"},
        ],
    )
    try:
        event = FakeCoreEvent("hi")
        req = ProviderRequest(prompt="hi", system_prompt="Base.")
        await call_event_hook(event, EventType.OnLLMRequestEvent, req)
        # The handler ran (observe), but its writes were not applied.
        assert req.system_prompt == "Base."
    finally:
        await bridge.stop()


@pytest.mark.asyncio
async def test_lifecycle_and_error_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )
    plugin_root = tmp_path / "lifecycle_hook_e2e"
    write_hook_plugin(
        plugin_root,
        capabilities=[
            {"id": "llm.observe"},
            {"id": "plugin.inspect"},
        ],
        body="""
from astrbot_sdk import MessageEvent, Plugin, hooks
from astrbot_sdk.context import PluginInfo
from astrbot_sdk.hooks import PluginError

class TestPlugin(Plugin):
    @hooks.waiting_llm_request()
    async def on_waiting(self, event: MessageEvent | None) -> None:
        await self.ctx.storage.set("waiting", "yes")

    @hooks.plugin_error()
    async def on_error(
        self,
        event: MessageEvent | None,
        error: PluginError,
    ) -> None:
        await self.ctx.storage.set("error_plugin", error.plugin_name)

    @hooks.plugin_loaded()
    async def on_loaded(self, info: PluginInfo) -> None:
        await self.ctx.storage.set("loaded_name", info.name)
""",
    )
    context = MagicMock()
    bridge = SDKPluginBridge(plugin_root, context)
    kv = FakeKVStore()
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        kv,
    )
    try:
        await bridge.start()

        # waiting_llm_request fires with just the event.
        event = FakeCoreEvent("hi")
        await call_event_hook(event, EventType.OnWaitingLLMRequestEvent)
        assert kv.data.get(("plugin", bridge.plugin_id, "waiting")) == "yes"

        # plugin_error carries the frozen PluginError DTO.
        await call_event_hook(
            event,
            EventType.OnPluginErrorEvent,
            "some_plugin",
            "some_handler",
            ValueError("boom"),
            "traceback...",
        )
        assert (
            kv.data.get(("plugin", bridge.plugin_id, "error_plugin"))
            == "some_plugin"
        )

        # plugin_loaded fires with StarMetadata (no event) during start.
        assert (
            kv.data.get(("plugin", bridge.plugin_id, "loaded_name"))
            == f"plugin_{plugin_root.name}"
        )
    finally:
        await bridge.stop()
