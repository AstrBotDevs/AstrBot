from pathlib import Path

import pytest

import astrbot.core.provider.sources.fishaudio_tts_api_source as fishaudio_source
from astrbot.core.config.default import CONFIG_METADATA_2


def test_fishaudio_tts_template_exposes_stable_model_default():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]

    assert templates["FishAudio TTS(API)"]["model"] == "s1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_model", "expected_model"),
    [
        ("s2.1-pro-free", "s2.1-pro-free"),
        (None, "s1"),
        ("", "s1"),
    ],
)
async def test_fishaudio_tts_sends_configured_model_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    configured_model: str | None,
    expected_model: str,
):
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        headers = {"content-type": "audio/wav"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def aiter_bytes(self):
            yield b"test-audio"

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def stream(self, method, url, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = dict(kwargs["headers"])
            return _FakeResponse()

    monkeypatch.setattr(fishaudio_source, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(fishaudio_source, "get_astrbot_temp_path", lambda: tmp_path)

    provider_config = {
        "id": "test-fishaudio-tts",
        "type": "fishaudio_tts_api",
        "api_key": "test-key",
        "fishaudio-tts-reference-id": "a" * 32,
    }
    if configured_model is not None:
        provider_config["model"] = configured_model

    provider = fishaudio_source.ProviderFishAudioTTSAPI(
        provider_config=provider_config,
        provider_settings={},
    )

    audio_path = await provider.get_audio("hello")

    assert provider.get_model() == expected_model
    assert captured["method"] == "POST"
    assert captured["url"] == "/tts"
    assert captured["headers"] == {
        "Authorization": "Bearer test-key",
        "content-type": "application/msgpack",
        "model": expected_model,
    }
    assert provider.headers == {"Authorization": "Bearer test-key"}
    assert Path(audio_path).read_bytes() == b"test-audio"
