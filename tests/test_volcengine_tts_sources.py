import base64
import builtins
from pathlib import Path
from typing import Any

import aiohttp
import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.register import provider_cls_map
from astrbot.core.provider.sources.volcengine_tts import ProviderVolcengineTTS
from astrbot.core.provider.sources.volcengine_tts_v3 import (
    ProviderVolcengineTTSV3,
)


class _FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        text: str = "",
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self._text = text
        self._body = body
        self.headers = headers or {}

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def text(self) -> str:
        return self._text

    async def read(self) -> bytes:
        return self._body


class _FakeSession:
    def __init__(
        self,
        post_response: _FakeResponse,
        get_response: _FakeResponse | None = None,
    ) -> None:
        self.post_response = post_response
        self.get_response = get_response
        self.post_calls: list[tuple[str, dict[str, Any]]] = []
        self.get_calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.post_calls.append((url, kwargs))
        return self.post_response

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.get_calls.append((url, kwargs))
        if self.get_response is None:
            raise AssertionError("Unexpected audio download request")
        return self.get_response


def _make_v1_provider(overrides: dict[str, Any] | None = None) -> ProviderVolcengineTTS:
    provider_config: dict[str, Any] = {
        "id": "test-volcengine-v1",
        "type": "volcengine_tts",
        "api_key": "test-key",
        "appid": "test-app-id",
        "volcengine_cluster": "volcano_tts",
        "volcengine_voice_type": "test-voice",
        "volcengine_speed_ratio": 1.25,
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderVolcengineTTS(provider_config, {})


def _make_v3_provider(
    overrides: dict[str, Any] | None = None,
) -> ProviderVolcengineTTSV3:
    provider_config: dict[str, Any] = {
        "id": "test-volcengine-v3",
        "type": "volcengine_tts_v3",
        "api_key": "test-secret-key",
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderVolcengineTTSV3(provider_config, {})


def _install_fake_session(
    provider: ProviderVolcengineTTSV3,
    post_response: _FakeResponse,
    get_response: _FakeResponse | None = None,
) -> _FakeSession:
    session = _FakeSession(post_response, get_response)
    provider._session_factory = lambda: session
    return session


def _set_temp_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "astrbot.core.provider.sources.volcengine_tts_v3.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )


def test_volcengine_v1_payload_structure():
    provider = _make_v1_provider()

    payload = provider._build_request_payload("hello")

    assert payload["app"] == {
        "appid": "test-app-id",
        "token": "test-key",
        "cluster": "volcano_tts",
    }
    assert payload["audio"]["voice_type"] == "test-voice"
    assert payload["audio"]["encoding"] == "mp3"
    assert payload["audio"]["speed_ratio"] == 1.25
    assert payload["request"]["text"] == "hello"
    assert payload["request"]["operation"] == "query"


def test_volcengine_v1_defaults():
    provider = ProviderVolcengineTTS(
        {"id": "test-volcengine-v1", "type": "volcengine_tts"},
        {},
    )

    assert provider.api_base == "https://openspeech.bytedance.com/api/v1/tts"
    assert provider.timeout == 20


def test_volcengine_v3_config_template_and_schema():
    provider_metadata = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]
    template = provider_metadata["config_template"]["火山引擎_TTS(音频生成API)"]
    provider_items = provider_metadata["items"]

    assert template["type"] == "volcengine_tts_v3"
    assert template["provider_type"] == "text_to_speech"
    assert template["api_base"] == (
        "https://openspeech.bytedance.com/api/v3/tts/create"
    )
    assert template["hint"] == "provider_group.provider.volcengine_tts_v3.hint"
    assert template["model"] == "seed-audio-1.0"
    assert template["volcengine_v3_format"] == "mp3"
    assert template["volcengine_v3_sample_rate"] == 48000
    assert template["timeout"] == 300

    assert provider_items["volcengine_v3_format"]["options"] == [
        "wav",
        "mp3",
        "pcm",
        "ogg_opus",
    ]
    assert provider_items["volcengine_v3_sample_rate"]["options"] == [
        8000,
        16000,
        24000,
        32000,
        44100,
        48000,
    ]
    assert provider_items["volcengine_v3_speech_rate"]["slider"] == {
        "min": -50,
        "max": 100,
        "step": 1,
    }
    assert provider_items["volcengine_v3_loudness_rate"]["slider"] == {
        "min": -50,
        "max": 100,
        "step": 1,
    }
    assert provider_items["volcengine_v3_pitch_rate"]["slider"] == {
        "min": -12,
        "max": 12,
        "step": 1,
    }


def test_volcengine_v3_provider_registration():
    metadata = provider_cls_map["volcengine_tts_v3"]

    assert metadata.provider_type is ProviderType.TEXT_TO_SPEECH
    assert metadata.cls_type is ProviderVolcengineTTSV3


def test_provider_manager_dynamic_imports_volcengine_v3(
    monkeypatch: pytest.MonkeyPatch,
):
    from astrbot.core import astr_main_agent as _astr_main_agent  # noqa: F401
    from astrbot.core.provider.manager import ProviderManager

    imported_modules: list[tuple[str, int]] = []
    original_import = builtins.__import__

    def track_import(
        name: str,
        globals_: dict[str, Any] | None = None,
        locals_: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        imported_modules.append((name, level))
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", track_import)

    ProviderManager.dynamic_import_provider(object(), "volcengine_tts_v3")

    assert ("sources.volcengine_tts_v3", 1) in imported_modules


def test_volcengine_v3_payload_uses_defaults_without_reference():
    provider = _make_v3_provider()

    payload = provider._build_payload("hello")

    assert payload == {
        "model": "seed-audio-1.0",
        "text_prompt": "hello",
        "audio_config": {
            "format": "mp3",
            "sample_rate": 48000,
            "speech_rate": 0,
            "loudness_rate": 0,
            "pitch_rate": 0,
        },
    }


def test_volcengine_v3_normalizes_blank_endpoint_and_model_to_defaults():
    provider = _make_v3_provider({"api_base": "  ", "model": "  "})

    assert provider.api_base == "https://openspeech.bytedance.com/api/v3/tts/create"
    assert provider.model_name == "seed-audio-1.0"


def test_volcengine_v3_payload_maps_config_and_speaker():
    provider = _make_v3_provider(
        {
            "model": "custom-model",
            "volcengine_v3_speaker": "speaker-id",
            "volcengine_v3_format": "wav",
            "volcengine_v3_sample_rate": 24000,
            "volcengine_v3_speech_rate": -50,
            "volcengine_v3_loudness_rate": 100,
            "volcengine_v3_pitch_rate": 12,
        }
    )

    payload = provider._build_payload("hello")

    assert payload["model"] == "custom-model"
    assert payload["references"] == [{"speaker": "speaker-id"}]
    assert payload["audio_config"] == {
        "format": "wav",
        "sample_rate": 24000,
        "speech_rate": -50,
        "loudness_rate": 100,
        "pitch_rate": 12,
    }


@pytest.mark.asyncio
async def test_volcengine_v3_decodes_audio_and_sends_expected_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_v3_provider({"proxy": "http://proxy.example:8080"})
    encoded_audio = base64.b64encode(b"audio-bytes").decode()
    session = _install_fake_session(
        provider,
        _FakeResponse(
            text=f'{{"audio": "{encoded_audio}"}}',
            headers={"X-Tt-Logid": "test-log-id"},
        ),
    )
    _set_temp_path(monkeypatch, tmp_path)

    result = Path(await provider.get_audio("hello"))

    assert result.parent == tmp_path
    assert result.suffix == ".mp3"
    assert result.read_bytes() == b"audio-bytes"
    assert len(session.post_calls) == 1
    request_url, request = session.post_calls[0]
    assert request_url == "https://openspeech.bytedance.com/api/v3/tts/create"
    assert request["json"]["text_prompt"] == "hello"
    assert request["headers"]["X-Api-Key"] == "test-secret-key"
    assert request["headers"]["X-Api-Request-Id"]
    assert "Authorization" not in request["headers"]
    assert "X-Api-Resource-Id" not in request["headers"]
    assert isinstance(request["timeout"], aiohttp.ClientTimeout)
    assert request["timeout"].total == 300
    assert request["proxy"] == "http://proxy.example:8080"


@pytest.mark.asyncio
async def test_volcengine_v3_accepts_data_audio_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_v3_provider()
    encoded_audio = base64.b64encode(b"alias-audio").decode()
    _install_fake_session(
        provider,
        _FakeResponse(text=f'{{"data": "{encoded_audio}"}}'),
    )
    _set_temp_path(monkeypatch, tmp_path)

    result = Path(await provider.get_audio("hello"))

    assert result.read_bytes() == b"alias-audio"


@pytest.mark.asyncio
async def test_volcengine_v3_downloads_url_with_proxy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_v3_provider(
        {
            "proxy": "http://proxy.example:8080",
            "volcengine_v3_format": "ogg_opus",
        }
    )
    session = _install_fake_session(
        provider,
        _FakeResponse(text='{"url": "https://audio.example/result"}'),
        _FakeResponse(body=b"downloaded-audio"),
    )
    _set_temp_path(monkeypatch, tmp_path)

    result = Path(await provider.get_audio("hello"))

    assert result.suffix == ".ogg"
    assert result.read_bytes() == b"downloaded-audio"
    assert session.get_calls == [
        (
            "https://audio.example/result",
            {
                "timeout": session.post_calls[0][1]["timeout"],
                "proxy": "http://proxy.example:8080",
            },
        )
    ]


@pytest.mark.parametrize(
    ("audio_format", "expected_suffix"),
    [("wav", ".wav"), ("mp3", ".mp3"), ("pcm", ".pcm"), ("ogg_opus", ".ogg")],
)
@pytest.mark.asyncio
async def test_volcengine_v3_file_suffix_follows_format(
    audio_format: str,
    expected_suffix: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_v3_provider({"volcengine_v3_format": audio_format})
    encoded_audio = base64.b64encode(b"audio").decode()
    _install_fake_session(
        provider,
        _FakeResponse(text=f'{{"audio": "{encoded_audio}"}}'),
    )
    _set_temp_path(monkeypatch, tmp_path)

    result = Path(await provider.get_audio("hello"))

    assert result.suffix == expected_suffix


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"volcengine_v3_format": "flac"}, "audio format"),
        ({"volcengine_v3_sample_rate": 40000}, "sample rate"),
        ({"volcengine_v3_speech_rate": -51}, "speech rate"),
        ({"volcengine_v3_speech_rate": 101}, "speech rate"),
        ({"volcengine_v3_loudness_rate": -51}, "loudness rate"),
        ({"volcengine_v3_loudness_rate": 101}, "loudness rate"),
        ({"volcengine_v3_pitch_rate": -13}, "pitch rate"),
        ({"volcengine_v3_pitch_rate": 13}, "pitch rate"),
        ({"timeout": 0}, "timeout"),
        ({"timeout": -1}, "timeout"),
        ({"volcengine_v3_sample_rate": "invalid"}, "must be integers"),
        ({"volcengine_v3_speech_rate": None}, "must be integers"),
        ({"timeout": "invalid"}, "must be integers"),
    ],
)
def test_volcengine_v3_rejects_invalid_audio_config(
    overrides: dict[str, Any],
    message: str,
):
    with pytest.raises(ValueError, match=message):
        _make_v3_provider(overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"volcengine_v3_speech_rate": -50},
        {"volcengine_v3_speech_rate": 100},
        {"volcengine_v3_loudness_rate": -50},
        {"volcengine_v3_loudness_rate": 100},
        {"volcengine_v3_pitch_rate": -12},
        {"volcengine_v3_pitch_rate": 12},
    ],
)
def test_volcengine_v3_accepts_audio_config_boundaries(overrides: dict[str, Any]):
    _make_v3_provider(overrides)


@pytest.mark.parametrize(
    ("overrides", "text", "message"),
    [
        ({"api_key": ""}, "hello", "API key is required"),
        ({}, "", "cannot be empty"),
        ({}, "   ", "cannot be empty"),
        ({}, 123, "must be a string"),
        ({}, "x" * 3001, "cannot exceed 3000"),
    ],
)
@pytest.mark.asyncio
async def test_volcengine_v3_validates_credentials_and_text(
    overrides: dict[str, Any],
    text: Any,
    message: str,
):
    provider = _make_v3_provider(overrides)

    with pytest.raises(ValueError, match=message):
        await provider.get_audio(text)


@pytest.mark.asyncio
async def test_volcengine_v3_raises_redacted_http_error():
    provider = _make_v3_provider()
    _install_fake_session(
        provider,
        _FakeResponse(
            status=401,
            text="invalid key test-secret-key",
            headers={"X-Tt-Logid": "log-401"},
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await provider.get_audio("hello")

    message = str(exc_info.value)
    assert "status 401" in message
    assert "log-401" in message
    assert "test-secret-key" not in message
    assert "***" in message


@pytest.mark.asyncio
async def test_volcengine_v3_raises_redacted_api_error():
    provider = _make_v3_provider()
    _install_fake_session(
        provider,
        _FakeResponse(
            text='{"code": 1001, "message": "bad test-secret-key"}',
            headers={"X-Tt-Logid": "log-api"},
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await provider.get_audio("hello")

    message = str(exc_info.value)
    assert "API error 1001" in message
    assert "log-api" in message
    assert "test-secret-key" not in message


@pytest.mark.asyncio
async def test_volcengine_v3_raises_redacted_invalid_json_error():
    provider = _make_v3_provider()
    _install_fake_session(
        provider,
        _FakeResponse(text="not-json test-secret-key"),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await provider.get_audio("hello")

    message = str(exc_info.value)
    assert "invalid JSON" in message
    assert "test-secret-key" not in message


@pytest.mark.parametrize("response_text", ["[]", '"audio"', "null"])
@pytest.mark.asyncio
async def test_volcengine_v3_rejects_non_object_json(response_text: str):
    provider = _make_v3_provider()
    _install_fake_session(provider, _FakeResponse(text=response_text))

    with pytest.raises(RuntimeError, match="non-object JSON response"):
        await provider.get_audio("hello")


@pytest.mark.parametrize(
    ("response_text", "message"),
    [
        ('{"audio": 123}', "non-string audio payload"),
        ('{"audio": "not-base64"}', "invalid Base64 audio data"),
        ("{}", "no audio payload or URL"),
    ],
)
@pytest.mark.asyncio
async def test_volcengine_v3_rejects_malformed_success_response(
    response_text: str,
    message: str,
):
    provider = _make_v3_provider()
    _install_fake_session(provider, _FakeResponse(text=response_text))

    with pytest.raises(RuntimeError, match=message):
        await provider.get_audio("hello")


@pytest.mark.parametrize(
    ("response_text", "message"),
    [
        ('{"audio": ""}', "empty audio"),
        ('{"audio": null}', "empty audio"),
    ],
)
@pytest.mark.asyncio
async def test_volcengine_v3_rejects_empty_audio(
    response_text: str,
    message: str,
):
    provider = _make_v3_provider()
    _install_fake_session(provider, _FakeResponse(text=response_text))

    with pytest.raises(RuntimeError, match=message):
        await provider.get_audio("hello")


@pytest.mark.asyncio
async def test_volcengine_v3_falls_back_from_empty_audio_to_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_v3_provider()
    encoded_audio = base64.b64encode(b"fallback-audio").decode()
    _install_fake_session(
        provider,
        _FakeResponse(text=f'{{"audio": "", "data": "{encoded_audio}"}}'),
    )
    _set_temp_path(monkeypatch, tmp_path)

    result = Path(await provider.get_audio("hello"))

    assert result.read_bytes() == b"fallback-audio"


@pytest.mark.asyncio
async def test_volcengine_v3_falls_back_from_empty_audio_to_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_v3_provider()
    session = _install_fake_session(
        provider,
        _FakeResponse(text='{"audio": "", "url": "https://audio.example/result"}'),
        _FakeResponse(body=b"fallback-download"),
    )
    _set_temp_path(monkeypatch, tmp_path)

    result = Path(await provider.get_audio("hello"))

    assert result.read_bytes() == b"fallback-download"
    assert session.get_calls[0][0] == "https://audio.example/result"


@pytest.mark.asyncio
async def test_volcengine_v3_raises_redacted_download_error():
    provider = _make_v3_provider()
    _install_fake_session(
        provider,
        _FakeResponse(text='{"url": "https://audio.example/result"}'),
        _FakeResponse(status=403, text="denied test-secret-key"),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await provider.get_audio("hello")

    message = str(exc_info.value)
    assert "download failed with status 403" in message
    assert "test-secret-key" not in message


@pytest.mark.asyncio
async def test_volcengine_v3_rejects_empty_downloaded_audio():
    provider = _make_v3_provider()
    _install_fake_session(
        provider,
        _FakeResponse(text='{"url": "https://audio.example/result"}'),
        _FakeResponse(body=b""),
    )

    with pytest.raises(RuntimeError, match="empty audio"):
        await provider.get_audio("hello")


class _FailingSession:
    async def __aenter__(self) -> "_FailingSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def post(self, *_args: object, **_kwargs: object) -> _FakeResponse:
        raise aiohttp.ClientConnectionError("connection failed")


@pytest.mark.asyncio
async def test_volcengine_v3_wraps_network_errors():
    provider = _make_v3_provider()
    provider._session_factory = _FailingSession

    with pytest.raises(RuntimeError, match="network request failed"):
        await provider.get_audio("hello")


class _SecretFailingSession(_FailingSession):
    def post(self, *_args: object, **_kwargs: object) -> _FakeResponse:
        raise aiohttp.ClientConnectionError("failed with test-secret-key")


@pytest.mark.asyncio
async def test_volcengine_v3_redacts_network_errors():
    provider = _make_v3_provider()
    provider._session_factory = _SecretFailingSession

    with pytest.raises(RuntimeError) as exc_info:
        await provider.get_audio("hello")

    message = str(exc_info.value)
    assert "network request failed" in message
    assert "test-secret-key" not in message


@pytest.mark.asyncio
async def test_volcengine_v3_wraps_file_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _make_v3_provider()
    encoded_audio = base64.b64encode(b"audio").decode()
    _install_fake_session(
        provider,
        _FakeResponse(text=f'{{"audio": "{encoded_audio}"}}'),
    )
    _set_temp_path(monkeypatch, tmp_path)

    def fail_write_bytes(_path: Path, _data: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", fail_write_bytes)

    with pytest.raises(RuntimeError, match="failed to write the audio file"):
        await provider.get_audio("hello")
