import base64
import io
import json
import wave

import pytest
import pytest_asyncio
from aiohttp import web

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.register import provider_cls_map
from astrbot.core.provider.sources.modelbest_voxcpm_tts_source import (
    MAX_AUDIO_BYTES,
    ModelBestVoxCPMError,
    ProviderModelBestVoxCPMTTSAPI,
)


def _wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(48_000)
        wav_file.writeframes(b"\x00\x00" * 480)
    audio = bytearray(buffer.getvalue())
    audio[4:8] = b"\xff\xff\xff\xff"
    audio[40:44] = b"\xff\xff\xff\xff"
    return bytes(audio)


def _event(event_type: str, **payload: object) -> bytes:
    data = json.dumps({"type": event_type, **payload})
    return f"data: {data}\r\n\r\n".encode()


def _provider(base_url: str, **overrides: object) -> ProviderModelBestVoxCPMTTSAPI:
    config = {
        "id": "test-modelbest-voxcpm",
        "type": "modelbest_voxcpm_tts_api",
        "api_key": "test-key",
        "api_base": base_url,
        "model": "VoxCPM2-test",
        "timeout": 20,
        "custom_headers": {"X-Test-Header": "astrbot"},
    }
    config.update(overrides)
    return ProviderModelBestVoxCPMTTSAPI(config, {})


@pytest_asyncio.fixture
async def modelbest_server(unused_tcp_port):
    state = {"status": 200, "body": b"", "request": None}

    async def speech(request):
        state["request"] = {
            "headers": dict(request.headers),
            "json": await request.json(),
        }
        if state["status"] != 200:
            return web.Response(status=state["status"], text=state["body"].decode())

        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        body = state["body"]
        for offset in range(0, len(body), 7):
            await response.write(body[offset : offset + 7])
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_post("/v1/audio/speech", speech)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
    try:
        yield f"http://127.0.0.1:{unused_tcp_port}/v1", state
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_get_audio_decodes_split_sse_and_repairs_wav(
    modelbest_server,
    tmp_path,
    monkeypatch,
):
    base_url, state = modelbest_server
    wav_audio = _wav_bytes()
    split_at = 31
    state["body"] = b"".join(
        [
            _event(
                "speech.audio.delta",
                audio=base64.b64encode(wav_audio[:split_at]).decode(),
            ),
            _event(
                "speech.audio.delta",
                audio=base64.b64encode(wav_audio[split_at:]).decode(),
            ),
            _event("speech.audio.done"),
        ]
    )
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    provider = _provider(base_url)

    output_path = await provider.get_audio("你好，欢迎使用 VoxCPM。")

    with wave.open(output_path, "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getframerate() == 48_000
        assert wav_file.getnframes() == 480
    assert state["request"]["json"] == {
        "model": "VoxCPM2-test",
        "input": "你好，欢迎使用 VoxCPM。",
        "voice": "default",
        "response_format": "wav",
        "stream": True,
    }
    assert state["request"]["headers"]["Authorization"] == "Bearer test-key"
    assert state["request"]["headers"]["Accept"] == "text/event-stream"
    assert state["request"]["headers"]["X-Test-Header"] == "astrbot"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"data: not-json\r\n\r\n", "invalid SSE event data"),
        (_event("speech.audio.delta", audio="not-base64"), "invalid Base64"),
        (_event("speech.audio.delta", audio=""), "empty audio chunk"),
        (_event("speech.audio.done"), "returned no audio"),
        (_event("error", error="quota exceeded"), "quota exceeded"),
        (
            _event(
                "speech.audio.delta",
                audio=base64.b64encode(b"not a wav").decode(),
            )
            + _event("speech.audio.done"),
            "RIFF/WAVE",
        ),
        (
            _event(
                "speech.audio.delta",
                audio=base64.b64encode(_wav_bytes()).decode(),
            ),
            "before speech.audio.done",
        ),
    ],
)
async def test_get_audio_rejects_invalid_streams(modelbest_server, body, message):
    base_url, state = modelbest_server
    state["body"] = body
    provider = _provider(base_url)

    with pytest.raises(ModelBestVoxCPMError, match=message):
        await provider.get_audio("Hello")


@pytest.mark.asyncio
async def test_get_audio_surfaces_http_error(modelbest_server):
    base_url, state = modelbest_server
    state["status"] = 401
    state["body"] = b"invalid key"
    provider = _provider(base_url)

    with pytest.raises(ModelBestVoxCPMError, match="HTTP 401.*invalid key"):
        await provider.get_audio("Hello")


@pytest.mark.asyncio
async def test_get_audio_rejects_oversized_response(
    modelbest_server,
    monkeypatch,
):
    base_url, state = modelbest_server
    state["body"] = _event(
        "speech.audio.delta",
        audio=base64.b64encode(b"x" * 32).decode(),
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.modelbest_voxcpm_tts_source.MAX_AUDIO_BYTES",
        16,
    )
    provider = _provider(base_url)

    with pytest.raises(ModelBestVoxCPMError, match="exceeds 100 MiB"):
        await provider.get_audio("Hello")


@pytest.mark.asyncio
async def test_provider_validates_required_configuration():
    with pytest.raises(ValueError, match="API key"):
        await _provider(
            "https://api.modelbest.cn/v1",
            api_key="",
        ).get_audio("Hello")

    with pytest.raises(ValueError, match="model ID"):
        await _provider(
            "https://api.modelbest.cn/v1",
            model="",
        ).get_audio("Hello")

    with pytest.raises(ValueError, match="positive integer"):
        _provider("https://api.modelbest.cn/v1", timeout=0)


def test_modelbest_voxcpm_adapter_is_registered():
    metadata = provider_cls_map["modelbest_voxcpm_tts_api"]
    assert metadata.cls_type is ProviderModelBestVoxCPMTTSAPI


def test_default_config_exposes_modelbest_voxcpm_provider():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    config = templates["ModelBest TTS(API)"]
    assert config["id"] == "modelbest_tts"
    assert config["type"] == "modelbest_voxcpm_tts_api"
    assert config["provider_type"] == "text_to_speech"
    assert config["api_base"] == "https://api.modelbest.cn/v1"
    assert config["enable"] is False


def test_audio_size_limit_remains_bounded():
    assert MAX_AUDIO_BYTES == 100 * 1024 * 1024
