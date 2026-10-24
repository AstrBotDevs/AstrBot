import asyncio
import json
from pathlib import Path

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


def _make_provider(audio_path: Path, **overrides) -> ProviderMiniMaxTTSAPI:
    config = {
        "id": "test-minimax-tts",
        "type": "minimax_tts_api",
        "api_key": "test-key",
        "api_base": "https://api.minimaxi.com/v1/t2a_v2",
        "model": "speech-02-turbo",
        "minimax-voice-id": "default_voice",
        "minimax-voice-clone-audio": str(audio_path),
        "minimax-voice-clone-id": "custom_voice",
        "minimax-voice-clone-model": "speech-2.8-hd",
        "minimax-voice-clone-api-base": "https://api.minimaxi.com/v1",
    }
    config.update(overrides)
    return ProviderMiniMaxTTSAPI(config, {})


@pytest.mark.asyncio
async def test_clone_voice_uploads_audio_and_uses_returned_voice_id(
    monkeypatch,
    tmp_path,
):
    audio_path = tmp_path / "reference.wav"
    audio_path.write_bytes(b"wav data")
    provider = _make_provider(audio_path)
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

    assert await provider.clone_voice() == "created-voice"
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
    assert session.posts[1][0] == "https://api.minimaxi.com/v1/voice_clone"
    assert session.posts[1][1]["json"] == {
        "file_id": "file-123",
        "voice_id": "custom_voice",
        "model": "speech-2.8-hd",
    }
    assert _FakeFormData.last is not None
    assert [field[0] for field in _FakeFormData.last.fields] == ["file", "purpose"]
    assert _FakeFormData.last.fields[1][1] == "voice_clone"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "api_base",
    ["https://api.minimax.io/v1", "https://api.minimaxi.com/v1"],
)
async def test_clone_voice_supports_both_regional_api_bases(
    monkeypatch,
    tmp_path,
    api_base,
):
    audio_path = tmp_path / "reference.mp3"
    audio_path.write_bytes(b"mp3 data")
    provider = _make_provider(
        audio_path,
        **{"minimax-voice-clone-api-base": api_base},
    )
    session = _FakeSession([_FakeResponse({"file_id": "file-123"}), _FakeResponse({})])
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.ClientSession",
        lambda: session,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.FormData",
        _FakeFormData,
    )

    assert await provider.clone_voice() == "custom_voice"
    assert [post[0] for post in session.posts] == [
        f"{api_base}/files/upload",
        f"{api_base}/voice_clone",
    ]


@pytest.mark.asyncio
async def test_clone_voice_is_single_flight(monkeypatch, tmp_path):
    audio_path = tmp_path / "reference.wav"
    audio_path.write_bytes(b"wav data")
    provider = _make_provider(audio_path)
    session = _FakeSession([_FakeResponse({"file_id": "file-123"}), _FakeResponse({})])
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.ClientSession",
        lambda: session,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.FormData",
        _FakeFormData,
    )

    assert await asyncio.gather(provider.clone_voice(), provider.clone_voice()) == [
        "custom_voice",
        "custom_voice",
    ]
    assert len(session.posts) == 2


@pytest.mark.asyncio
async def test_clone_voice_validates_configuration_and_audio_format(tmp_path):
    audio_path = tmp_path / "reference.txt"
    audio_path.write_text("not audio")
    provider = _make_provider(audio_path, **{"minimax-voice-clone-id": ""})
    with pytest.raises(ValueError, match="minimax-voice-clone-id"):
        await provider.clone_voice()

    provider = _make_provider(audio_path)
    with pytest.raises(ValueError, match="only \\.mp3, \\.m4a, and \\.wav"):
        await provider.clone_voice()


@pytest.mark.asyncio
async def test_clone_voice_propagates_api_status_error(monkeypatch, tmp_path):
    audio_path = tmp_path / "reference.wav"
    audio_path.write_bytes(b"wav data")
    provider = _make_provider(audio_path)
    session = _FakeSession(
        [_FakeResponse({"base_resp": {"status_code": 1004, "status_msg": "bad audio"}})]
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.ClientSession",
        lambda: session,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.minimax_tts_api_source.aiohttp.FormData",
        _FakeFormData,
    )

    with pytest.raises(RuntimeError, match="bad audio"):
        await provider.clone_voice()
