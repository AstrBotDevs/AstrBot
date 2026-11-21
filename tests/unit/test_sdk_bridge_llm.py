from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from astrbot.core.provider.entities import LLMResponse, ProviderMeta, ProviderType
from astrbot.core.star.sdk_bridge import SDKPluginBridge
from astrbot.core.star.sdk_bridge.services.llm import LLMGenerateService
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot_sdk.errors import NotFound
from astrbot_sdk.llm import ProviderKind

from tests.unit.test_sdk_bridge import FakeCoreEvent, FakeKVStore


def make_provider(provider_id="p1", model="gpt-x", chunks=()):
    meta = ProviderMeta(
        id=provider_id,
        model=model,
        type="openai",
        provider_type=ProviderType.CHAT_COMPLETION,
    )
    provider = MagicMock()
    provider.meta.return_value = meta
    provider.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="one-shot"),
    )

    async def stream(**kwargs):
        for piece in chunks:
            yield LLMResponse(role="assistant", completion_text=piece)

    provider.text_chat_stream = stream
    return provider


def make_context(provider=None, chunks=()):
    provider = provider or make_provider(chunks=chunks)
    context = MagicMock()
    context.provider_manager.provider_insts = [provider]
    context.provider_manager.get_provider_by_id = AsyncMock(return_value=provider)
    context.provider_manager.get_using_provider_async = AsyncMock(
        return_value=provider,
    )
    context._test_provider = provider
    return context


@pytest.mark.asyncio
async def test_llm_service_provider_queries() -> None:
    context = make_context()
    service = LLMGenerateService(context)

    result = await service.handle("current_provider", {})
    assert result["provider"].id == "p1"
    assert result["provider"].kind is ProviderKind.CHAT
    assert result["provider"].model == "gpt-x"

    result = await service.handle("list_providers", {"kind": "chat"})
    assert [p.id for p in result["providers"]] == ["p1"]

    missing_context = make_context()
    missing_context.provider_manager.get_provider_by_id = AsyncMock(
        return_value=None,
    )
    with pytest.raises(NotFound):
        await LLMGenerateService(missing_context).handle(
            "current_provider",
            {"provider_id": "missing"},
        )


@pytest.mark.asyncio
async def test_llm_service_generate_and_stream() -> None:
    context = make_context(chunks=("hel", "lo"))
    service = LLMGenerateService(context)

    result = await service.handle(
        "generate",
        {"prompt": "hi", "system_prompt": "be brief"},
    )
    assert result["response"].content == "one-shot"
    kwargs = context._test_provider.text_chat.await_args.kwargs
    assert kwargs["prompt"] == "hi"
    assert kwargs["system_prompt"] == "be brief"

    stream = await service.handle("generate_stream", {"prompt": "hi"})
    deltas = [chunk.delta async for chunk in stream]
    assert deltas == ["hel", "lo"]


def write_llm_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "name": f"plugin_{plugin_root.name}",
                "desc": "llm bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:TestPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {"required": [{"id": "llm.generate"}]},
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(
        """
from astrbot_sdk import MessageEvent, Plugin, on

class TestPlugin(Plugin):
    @on.command("ask")
    async def ask(self, event: MessageEvent, question: str):
        response = await self.ctx.llm.generate(question)
        yield event.reply(f"once:{response.content}")

    @on.command("flow")
    async def flow(self, event: MessageEvent, question: str):
        chunks = []
        async for chunk in self.ctx.llm.stream(question):
            chunks.append(chunk.delta)
        yield event.reply(f"streamed:{chr(124).join(chunks)}")
""",
        "utf-8",
    )


@pytest.mark.asyncio
async def test_bridge_llm_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "llm_bridge_e2e"
    write_llm_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    context = make_context(chunks=("hel", "lo", "!"))
    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()
        handlers = star_handlers_registry.star_handlers_map

        for command, expected in [
            ("ask hello", "once:one-shot"),
            ("flow hello", "streamed:hel|lo|!"),
        ]:
            name = command.split()[0]
            handler = handlers[f"sdk_bridge.{plugin_root.name}_{name}"]
            event = FakeCoreEvent(command)
            assert handler.event_filters[0].filter(event, None)
            params = event.get_extra("parsed_params") or {}
            replies = []
            async for _ in handler.handler(event, **params):
                if event.get_result():
                    replies.append(event.get_result().chain[0].text)
                event.clear_result()
            assert replies == [expected], (command, replies)
    finally:
        await bridge.stop()
