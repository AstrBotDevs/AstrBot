"""TTS payload, redaction, and file output contracts against a loopback server."""

import base64
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from aiohttp import web

from astrbot.core.provider.sources.volcengine_tts import ProviderVolcengineTTS


@pytest_asyncio.fixture
async def tts_server():
    state = SimpleNamespace(
        status=200,
        payload={"data": base64.b64encode(b"ID3-local-audio").decode()},
        requests=[],
    )

    async def handle(request):
        state.requests.append((dict(request.headers), await request.json()))
        return web.json_response(state.payload, status=state.status)

    app = web.Application()
    app.router.add_post("/tts", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    state.url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/tts"
    try:
        yield state
    finally:
        await runner.cleanup()


def test_payload_uses_configured_voice_speed_and_fresh_request_identifiers():
    provider = ProviderVolcengineTTS(
        {
            "api_key": "test-key",
            "appid": "test-app",
            "volcengine_cluster": "volc_tts",
            "volcengine_voice_type": "zh_female_01",
            "volcengine_speed_ratio": 1.25,
        },
        {},
    )
    first = provider._build_request_payload("First")
    second = provider._build_request_payload("Second")

    assert first["app"] == {
        "appid": "test-app",
        "token": "test-key",
        "cluster": "volc_tts",
    }
    assert first["audio"] == {
        "voice_type": "zh_female_01",
        "encoding": "mp3",
        "speed_ratio": 1.25,
        "volume_ratio": 1.0,
        "pitch_ratio": 1.0,
    }
    assert first["request"]["text"] == "First"
    assert second["request"]["text"] == "Second"
    assert first["request"]["operation"] == "query"
    assert first["request"]["reqid"] != second["request"]["reqid"]
    assert first["user"]["uid"] != second["user"]["uid"]


def test_defaults_are_used_in_the_request():
    provider = ProviderVolcengineTTS({}, {})
    payload = provider._build_request_payload("text")

    assert payload["app"] == {"appid": "", "token": "", "cluster": ""}
    assert payload["audio"]["speed_ratio"] == 1.0
    assert provider.api_base == "https://openspeech.bytedance.com/api/v1/tts"
    assert provider.timeout == 20


def test_loggable_payload_redacts_the_token_without_changing_the_request():
    provider = ProviderVolcengineTTS({"api_key": "secret-key"}, {})
    payload = provider._build_request_payload("test")
    original = copy.deepcopy(payload)

    loggable = provider._build_loggable_payload(payload)

    assert loggable["app"]["token"] == "***"
    assert loggable["request"]["text"] == "test"
    assert payload == original
    assert payload["app"]["token"] == "secret-key"


@pytest.mark.parametrize(
    "payload", [{}, {"app": None, "user": None, "audio": None, "request": None}]
)
def test_loggable_payload_accepts_missing_sections(payload):
    assert ProviderVolcengineTTS._build_loggable_payload(payload) == {
        "app": {},
        "user": {},
        "audio": {},
        "request": {},
    }


@pytest.mark.asyncio
async def test_audio_request_decodes_bytes_into_the_isolated_output_directory(
    tts_server, tmp_path, monkeypatch
):
    output = tmp_path / "audio-output"
    monkeypatch.setattr(
        "astrbot.core.provider.sources.volcengine_tts.get_astrbot_temp_path",
        lambda: str(output),
    )
    provider = ProviderVolcengineTTS(
        {"api_base": tts_server.url, "api_key": "local-key", "appid": "local-app"}, {}
    )

    path = Path(await provider.get_audio("local text"))

    assert path.parent == output
    assert path.suffix == ".mp3"
    assert path.read_bytes() == b"ID3-local-audio"
    assert len(tts_server.requests) == 1
    headers, payload = tts_server.requests[0]
    assert headers["Authorization"] == "Bearer; local-key"
    assert payload["request"]["text"] == "local text"
    assert payload["app"]["appid"] == "local-app"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, payload, message",
    [(503, {"message": "offline"}, "503"), (200, {"message": "no audio"}, "no audio")],
)
async def test_failed_audio_requests_do_not_create_output_files(
    tts_server, tmp_path, monkeypatch, status, payload, message
):
    output = tmp_path / "audio-output"
    monkeypatch.setattr(
        "astrbot.core.provider.sources.volcengine_tts.get_astrbot_temp_path",
        lambda: str(output),
    )
    tts_server.status = status
    tts_server.payload = payload
    provider = ProviderVolcengineTTS({"api_base": tts_server.url}, {})

    with pytest.raises(Exception, match=message):
        await provider.get_audio("local text")

    assert len(tts_server.requests) == 1
    assert not output.exists()
