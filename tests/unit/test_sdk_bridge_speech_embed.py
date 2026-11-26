from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from astrbot.core.star.sdk_bridge import SDKPluginBridge
from astrbot.core.star.sdk_bridge.services.assets import AssetStore
from astrbot.core.star.sdk_bridge.services.embed import LLMEmbedService
from astrbot.core.star.sdk_bridge.services.speech import (
    SpeechSynthesizeService,
    SpeechTranscribeService,
)
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot_sdk.assets import AssetRef
from astrbot_sdk.errors import InvalidRequest, NotFound

from tests.unit.test_sdk_bridge import FakeCoreEvent, FakeKVStore


def make_context() -> MagicMock:
    from astrbot.core.provider.entities import ProviderType

    context = MagicMock()

    embedding = MagicMock()
    embedding.get_embeddings = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])

    stt = MagicMock()
    stt.get_text = AsyncMock(return_value="转写结果")

    tts = MagicMock()
    tts.get_audio = AsyncMock(return_value="/tmp/fake-tts.wav")

    providers = {
        ProviderType.EMBEDDING: embedding,
        ProviderType.SPEECH_TO_TEXT: stt,
        ProviderType.TEXT_TO_SPEECH: tts,
    }

    async def resolve(provider_type=None, umo=None):
        return providers[provider_type]

    context.provider_manager.get_using_provider_async = AsyncMock(
        side_effect=resolve,
    )
    context._embedding = embedding
    context._stt = stt
    context._tts = tts
    return context


@pytest.mark.asyncio
async def test_embed_service() -> None:
    context = make_context()
    service = LLMEmbedService(context)
    result = await service.handle(
        "embed",
        {"input": ["hello", "world"], "umo": None},
    )
    assert result["response"].embeddings == ((0.1, 0.2), (0.3, 0.4))
    context._embedding.get_embeddings.assert_awaited_once_with(["hello", "world"])

    with pytest.raises(InvalidRequest):
        await service.handle("embed", {"input": []})
    with pytest.raises(NotFound):
        await service.handle("rerank", {"input": "x"})


@pytest.mark.asyncio
async def test_transcribe_service(tmp_path: Path) -> None:
    context = make_context()
    store = AssetStore(tmp_path, "author/plugin")
    asset = store.put(b"audio-bytes", filename="a.wav", media_type="audio/wav")

    service = SpeechTranscribeService(context, store)
    result = await service.handle("transcribe", {"audio": asset, "umo": None})
    assert result["transcript"].text == "转写结果"
    called_path = context._stt.get_text.await_args.args[0]
    assert called_path.endswith(f"{asset.id}.bin")

    result = await service.handle(
        "transcribe",
        {"audio": "https://example.com/a.wav", "umo": None},
    )
    assert result["transcript"].text == "转写结果"
    assert context._stt.get_text.await_args.args[0] == "https://example.com/a.wav"

    with pytest.raises(InvalidRequest):
        await service.handle("transcribe", {"audio": "ftp://x"})


@pytest.mark.asyncio
async def test_synthesize_service(tmp_path: Path) -> None:
    context = make_context()
    audio = tmp_path / "fake-tts.wav"
    audio.write_bytes(b"wav-bytes")
    context._tts.get_audio = AsyncMock(return_value=str(audio))

    store = AssetStore(tmp_path / "assets", "author/plugin")
    service = SpeechSynthesizeService(context, store)
    result = await service.handle(
        "synthesize",
        {"text": "你好", "umo": None},
    )
    asset = result["asset"]
    assert asset.media_type == "audio/wav"
    assert store.read(asset.id, 0, 9) == b"wav-bytes"

    with pytest.raises(InvalidRequest):
        await service.handle("synthesize", {"text": ""})


def write_speech_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "name": f"plugin_{plugin_root.name}",
                "desc": "speech/embed bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:TestPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {
                    "required": [
                        {"id": "llm.embed"},
                        {"id": "speech.transcribe"},
                        {"id": "speech.synthesize"},
                    ],
                },
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(
        """
from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.message_components import Record

class TestPlugin(Plugin):
    @on.command("vec")
    async def vec(self, event: MessageEvent):
        response = await self.ctx.llm.embed(("a", "b"))
        yield event.reply(f"dims:{len(response.embeddings)}x{len(response.embeddings[0])}")

    @on.command("say")
    async def say(self, event: MessageEvent, text: str):
        asset = await self.ctx.llm.synthesize(text)
        yield event.reply(Record(source=asset))

    @on.command("hear")
    async def hear(self, event: MessageEvent):
        asset = await self.ctx.assets.upload(b"speech-bytes", filename="s.wav")
        transcript = await self.ctx.llm.transcribe(asset)
        yield event.reply(f"heard:{transcript.text}")
""",
        "utf-8",
    )


@pytest.mark.asyncio
async def test_bridge_speech_embed_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "speech_bridge_e2e"
    write_speech_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    context = make_context()
    audio = tmp_path / "fake-tts.wav"
    audio.write_bytes(b"wav-bytes")
    context._tts.get_audio = AsyncMock(return_value=str(audio))

    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()
        handlers = star_handlers_registry.star_handlers_map

        cases = {
            "vec": "dims:2x2",
            "say hi there": None,  # checked below
            "hear": "heard:转写结果",
        }
        for command, expected in cases.items():
            name = command.split()[0]
            handler = handlers[f"sdk_bridge.{plugin_root.name}_{name}"]
            event = FakeCoreEvent(command)
            assert handler.event_filters[0].filter(event, None)
            params = event.get_extra("parsed_params") or {}
            replies = []
            async for _ in handler.handler(event, **params):
                if event.get_result():
                    replies.append(event.get_result())
                event.clear_result()
            if expected is None:
                record = replies[0].chain[0]
                assert Path(record.path).read_bytes() == b"wav-bytes"
            else:
                assert replies[0].chain[0].text == expected, (command, replies)
    finally:
        await bridge.stop()
