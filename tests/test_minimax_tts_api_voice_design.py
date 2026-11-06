import asyncio
import json

import pytest

from astrbot.core.provider.sources.minimax_tts_api_source import (
    ProviderMiniMaxTTSAPI,
)


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def json(self, **_kwargs) -> dict:
        return self.payload

    async def text(self) -> str:
        return json.dumps(self.payload)


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.posts: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    def post(self, url: str, **kwargs):
        self.posts.append((url, kwargs))
        return self.responses.pop(0)


class _FakeFormData:
    last: "_FakeFormData | None" = None

    def __init__(self) -> None:
        self.fields: list[tuple[str, object, dict]] = []
        self.__class__.last = self

    def add_field(self, name: str, value: object, **kwargs) -> None:
        self.fields.append((name, value, kwargs))


def _make_provider(**overrides) -> ProviderMiniMaxTTSAPI:
    config = {
        "id": "test-minimax-tts",
        "type": "minimax_tts_api",
        "api_key": "test-key",
        "api_base": "https://api.minimaxi.com/v1/t2a_v2",
        "model": "speech-02-turbo",
        "minimax-voice-design-prompt": "A warm and friendly female voice",
        "minimax-voice-design-preview-text": "Hello, this is a preview.",
        "minimax-voice-design-voice-id": "designed-voice",
        "minimax-voice-design-prompt-audio": "",
        "minimax-voice-design-api-base": "https://api.minimaxi.com/v1",
    }
    config.update(overrides)
    return ProviderMiniMaxTTSAPI(config, {})


@pytest.mark.asyncio
async def test_design_voice_uploads_prompt_audio_and_uses_returned_voice_id(
    monkeypatch,
    tmp_path,
):
    audio_path = tmp_path / "reference.wav"
    audio_path.write_bytes(b"wav data")
    provider = _make_provider(**{"minimax-voice-design-prompt-audio": str(audio_path)})
    session = _FakeSession(
        [
            _FakeResponse({"file": {"file_id": "file-123"}}),
            _FakeResponse({"data": {"voice_id": "created-voice"}}),
        ]
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.ClientSession",
        lambda: session,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.FormData",
        _FakeFormData,
    )

    assert await provider.design_voice() == "created-voice"
    assert provider.voice_setting["voice_id"] == "created-voice"
    assert (
        json.loads(provider._build_tts_stream_body("hello"))["voice_setting"][
            "voice_id"
        ]
        == "created-voice"
    )
    assert len(session.posts) == 2
    assert session.posts[0][0] == "https://api.minimaxi.com/v1/files/upload"
    assert session.posts[0][1]["headers"] == {"Authorization": "Bearer test-key"}
    assert session.posts[1][0] == "https://api.minimaxi.com/v1/voice_design"
    assert session.posts[1][1]["json"] == {
        "prompt": "A warm and friendly female voice",
        "preview_text": "Hello, this is a preview.",
        "voice_id": "designed-voice",
    }
    assert _FakeFormData.last is not None
    assert [field[0] for field in _FakeFormData.last.fields] == ["file", "purpose"]
    assert _FakeFormData.last.fields[1][1] == "prompt_audio"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "api_base",
    ["https://api.minimax.io/v1", "https://api.minimaxi.com/v1"],
)
async def test_design_voice_supports_both_regional_api_bases(
    monkeypatch,
    api_base,
):
    provider = _make_provider(**{"minimax-voice-design-api-base": api_base})
    session = _FakeSession([_FakeResponse({"voice_id": "created-voice"})])
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.ClientSession",
        lambda: session,
    )

    assert await provider.design_voice() == "created-voice"
    assert [post[0] for post in session.posts] == [f"{api_base}/voice_design"]


@pytest.mark.asyncio
async def test_design_voice_is_single_flight(monkeypatch):
    provider = _make_provider()
    session = _FakeSession([_FakeResponse({"voice_id": "created-voice"})])
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.ClientSession",
        lambda: session,
    )

    assert await asyncio.gather(provider.design_voice(), provider.design_voice()) == [
        "created-voice",
        "created-voice",
    ]
    assert len(session.posts) == 1


@pytest.mark.asyncio
async def test_design_voice_requires_voice_id(monkeypatch):
    provider = _make_provider(**{"minimax-voice-design-voice-id": ""})
    session = _FakeSession([])
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.ClientSession",
        lambda: session,
    )

    with pytest.raises(ValueError, match="minimax-voice-design-voice-id"):
        await provider.design_voice()
    assert session.posts == []


@pytest.mark.asyncio
async def test_design_voice_validates_configuration_and_audio_format(tmp_path):
    provider = _make_provider(**{"minimax-voice-design-preview-text": ""})
    with pytest.raises(ValueError, match="minimax-voice-design-preview-text"):
        await provider.design_voice()

    audio_path = tmp_path / "reference.txt"
    audio_path.write_text("not audio")
    provider = _make_provider(
        **{"minimax-voice-design-prompt-audio": str(audio_path)},
    )
    with pytest.raises(ValueError, match="\\.mp3"):
        await provider.design_voice()


@pytest.mark.asyncio
async def test_design_voice_requires_prompt(monkeypatch):
    provider = _make_provider(**{"minimax-voice-design-prompt": ""})
    session = _FakeSession([])
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.ClientSession",
        lambda: session,
    )

    with pytest.raises(ValueError, match="minimax-voice-design-prompt"):
        await provider.design_voice()
    assert session.posts == []


@pytest.mark.asyncio
async def test_design_voice_rejects_mixed_voices(monkeypatch):
    provider = _make_provider(**{"minimax-is-timber-weight": True})
    session = _FakeSession([])
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.ClientSession",
        lambda: session,
    )

    with pytest.raises(ValueError, match="mixed voices"):
        await provider.design_voice()
    assert session.posts == []
