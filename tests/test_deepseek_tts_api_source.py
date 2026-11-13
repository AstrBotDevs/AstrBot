import asyncio
import copy
import io
import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.sources.deepseek_tts_api_source import (
    DeepSeekTTSError,
    ProviderDeepSeekTTSAPI,
)

_wav_buffer = io.BytesIO()
with wave.open(_wav_buffer, "wb") as _wav_file:
    _wav_file.setnchannels(1)
    _wav_file.setsampwidth(2)
    _wav_file.setframerate(24000)
    _wav_file.writeframes(b"\x00\x00" * 24)
TEST_WAV = _wav_buffer.getvalue()


@pytest_asyncio.fixture
async def provider_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    providers = []

    def make_provider(overrides=None):
        config = {
            "id": "test-deepseek-tts",
            "type": "deepseek_tts_api",
            "provider": "deepseek",
            "provider_type": "text_to_speech",
            "enable": True,
            "api_key": "secret-key",
            "api_base": "https://api.deepseek.com/v1",
            "deepseek-tts-voice": "stella",
            "deepseek-tts-filter-markdown": True,
            "timeout": "20",
            "proxy": "",
            "custom_headers": {},
        }
        config.update(overrides or {})
        provider = ProviderDeepSeekTTSAPI(config, {})
        providers.append(provider)
        return provider

    yield make_provider
    for provider in providers:
        await provider.terminate()


@pytest_asyncio.fixture
async def tts_server_factory():
    servers = []

    async def start_server(handler):
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", handler)
        server = TestServer(app)
        await server.start_server()
        servers.append(server)
        return str(server.make_url("/v1")).rstrip("/")

    yield start_server
    for server in reversed(servers):
        await server.close()


def _temp_files(tmp_path):
    return list((tmp_path / "data" / "temp").glob("deepseek_tts_api_*.wav"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "expected_voice", "expected_filter"),
    [
        ({}, "stella", True),
        (
            {
                "deepseek-tts-voice": "tide",
                "deepseek-tts-filter-markdown": False,
            },
            "tide",
            False,
        ),
    ],
)
async def test_deepseek_tts_request_and_chunked_wav_response(
    provider_factory,
    tts_server_factory,
    overrides,
    expected_voice,
    expected_filter,
):
    captured = {}

    async def handle_tts(request):
        captured["path"] = request.path
        captured["headers"] = request.headers
        captured["body"] = json.loads(await request.read())
        return web.Response(
            status=200,
            headers={"Content-Type": "audio/wav; charset=binary"},
            body=TEST_WAV,
        )

    api_base = await tts_server_factory(handle_tts)
    provider = provider_factory(
        {
            "api_base": f"{api_base}/",
            "custom_headers": {"X-Trace-Id": "trace-123"},
            **overrides,
        }
    )

    audio_path = Path(await provider.get_audio("你好，DeepSeek"))

    assert captured["path"] == "/v1/tools/tts"
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["headers"]["X-Trace-Id"] == "trace-123"
    assert captured["body"] == {
        "text": "你好，DeepSeek",
        "voice_id": expected_voice,
        "format": "wav",
        "filter_markdown": expected_filter,
    }
    assert "model" not in captured["body"]
    assert audio_path.read_bytes() == TEST_WAV


@pytest.mark.asyncio
async def test_deepseek_tts_reads_audio_across_small_chunks(
    provider_factory, tts_server_factory
):
    async def handle_tts(request):
        response = web.StreamResponse(status=200, headers={"Content-Type": "audio/wav"})
        await response.prepare(request)
        for index in range(0, len(TEST_WAV), 3):
            await response.write(TEST_WAV[index : index + 3])
        await response.write_eof()
        return response

    api_base = await tts_server_factory(handle_tts)
    provider = provider_factory({"api_base": api_base})

    audio_path = await provider.get_audio("chunked audio")

    assert Path(audio_path).read_bytes() == TEST_WAV


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["", " ", "\n\t"])
async def test_deepseek_tts_rejects_blank_text_without_request(
    provider_factory, tts_server_factory, text
):
    request_count = 0

    async def handle_tts(request):
        nonlocal request_count
        request_count += 1
        return web.Response(body=TEST_WAV, content_type="audio/wav")

    api_base = await tts_server_factory(handle_tts)
    provider = provider_factory({"api_base": api_base})

    with pytest.raises(ValueError, match="must not be blank"):
        await provider.get_audio(text)
    assert request_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "billable_count"),
    [("你" * 5001, 10002), ("a" * 10001, 10001)],
)
async def test_deepseek_tts_rejects_billable_character_overflow_without_request(
    provider_factory, tts_server_factory, text, billable_count
):
    request_count = 0

    async def handle_tts(request):
        nonlocal request_count
        request_count += 1
        return web.Response(body=TEST_WAV, content_type="audio/wav")

    api_base = await tts_server_factory(handle_tts)
    provider = provider_factory({"api_base": api_base})

    with pytest.raises(ValueError, match=f"{billable_count} billable characters"):
        await provider.get_audio(text)
    assert request_count == 0


@pytest.mark.asyncio
async def test_deepseek_tts_rejects_oversized_json_request_body(provider_factory):
    provider = provider_factory({"deepseek-tts-voice": "x" * (64 * 1024)})

    with pytest.raises(ValueError, match="request body.*maximum is 65536 bytes"):
        await provider.get_audio("hello")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 429, 503, 504])
async def test_deepseek_tts_http_errors_do_not_save_error_body(
    provider_factory, tts_server_factory, tmp_path, status
):
    async def handle_tts(request):
        return web.json_response({"error": "secret-key private input"}, status=status)

    api_base = await tts_server_factory(handle_tts)
    provider = provider_factory({"api_base": api_base})

    with pytest.raises(DeepSeekTTSError, match=f"HTTP {status}") as exc_info:
        await provider.get_audio("private input")

    assert "secret-key" not in str(exc_info.value)
    assert "private input" not in str(exc_info.value)
    assert _temp_files(tmp_path) == []


@pytest.mark.asyncio
async def test_deepseek_tts_rejects_empty_response_and_cleans_file(
    provider_factory, tts_server_factory, tmp_path
):
    async def handle_tts(request):
        return web.Response(body=b"", content_type="audio/wav")

    api_base = await tts_server_factory(handle_tts)
    provider = provider_factory({"api_base": api_base})

    with pytest.raises(DeepSeekTTSError, match="empty response"):
        await provider.get_audio("hello")
    assert _temp_files(tmp_path) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "content_type", "error_match"),
    [
        (b'{"error":"not audio"}', "application/json", "non-audio response"),
        (b'{"error":"not audio"}', "audio/wav", "invalid WAV audio"),
    ],
)
async def test_deepseek_tts_rejects_non_audio_response_and_cleans_file(
    provider_factory,
    tts_server_factory,
    tmp_path,
    body,
    content_type,
    error_match,
):
    async def handle_tts(request):
        return web.Response(body=body, content_type=content_type)

    api_base = await tts_server_factory(handle_tts)
    provider = provider_factory({"api_base": api_base})

    with pytest.raises(DeepSeekTTSError, match=error_match):
        await provider.get_audio("hello")
    assert _temp_files(tmp_path) == []


@pytest.mark.asyncio
async def test_deepseek_tts_interrupted_stream_cleans_file(
    provider_factory, tts_server_factory, tmp_path
):
    async def handle_tts(request):
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "audio/wav",
                "Content-Length": str(len(TEST_WAV)),
            },
        )
        await response.prepare(request)
        await response.write(TEST_WAV[:16])
        request.transport.close()
        await asyncio.sleep(0)
        return response

    api_base = await tts_server_factory(handle_tts)
    provider = provider_factory({"api_base": api_base})

    with pytest.raises(DeepSeekTTSError, match="transfer failed"):
        await provider.get_audio("hello")
    assert _temp_files(tmp_path) == []


@pytest.mark.asyncio
async def test_deepseek_tts_cancellation_cleans_file_and_propagates(
    provider_factory, tts_server_factory, tmp_path
):
    response_started = asyncio.Event()

    async def handle_tts(request):
        response = web.StreamResponse(status=200, headers={"Content-Type": "audio/wav"})
        await response.prepare(request)
        await response.write(TEST_WAV)
        response_started.set()
        await asyncio.Event().wait()
        return response

    api_base = await tts_server_factory(handle_tts)
    provider = provider_factory({"api_base": api_base})
    task = asyncio.create_task(provider.get_audio("hello"))
    await asyncio.wait_for(response_started.wait(), timeout=2)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _temp_files(tmp_path) == []


@pytest.mark.asyncio
async def test_deepseek_tts_concurrent_calls_use_distinct_files(
    provider_factory, tts_server_factory
):
    async def handle_tts(request):
        await asyncio.sleep(0.01)
        return web.Response(body=TEST_WAV, content_type="audio/wav")

    api_base = await tts_server_factory(handle_tts)
    provider = provider_factory({"api_base": api_base})

    paths = await asyncio.gather(
        *(provider.get_audio(f"request {index}") for index in range(8))
    )

    assert len(set(paths)) == 8
    assert all(Path(path).read_bytes() == TEST_WAV for path in paths)


@pytest.mark.asyncio
async def test_deepseek_tts_terminate_closes_client(provider_factory):
    provider = provider_factory()

    await provider.terminate()

    assert provider.client.is_closed


@pytest.mark.asyncio
async def test_deepseek_tts_manager_loads_template_and_selects_provider():
    provider_metadata = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]
    template = provider_metadata["config_template"]["DeepSeek TTS(API)"]
    assert template["api_base"] == "https://api.deepseek.com/v1"
    assert template["deepseek-tts-voice"] == "stella"
    assert template["deepseek-tts-filter-markdown"] is True
    assert "model" not in template
    voice_metadata = provider_metadata["items"]["deepseek-tts-voice"]
    assert voice_metadata["options"] == ["stella", "tide"]
    assert len(voice_metadata["labels"]) == 2

    provider_config = copy.deepcopy(template)
    provider_config["enable"] = True
    provider_config["api_key"] = "test-key"
    config = {
        "provider": [provider_config],
        "provider_sources": [],
        "provider_settings": {},
        "provider_stt_settings": {},
        "provider_tts_settings": {
            "enable": True,
            "provider_id": "deepseek_tts",
        },
        "agent": {
            "runtime": "astrbot",
            "config": {"model": {"provider_id": ""}},
        },
    }
    acm = SimpleNamespace(confs={"default": config}, get_conf=lambda _umo=None: config)
    manager = ProviderManager(acm, None, SimpleNamespace(default_persona="default"))

    await manager.load_provider(copy.deepcopy(provider_config))

    provider = manager.inst_map["deepseek_tts"]
    assert isinstance(provider, ProviderDeepSeekTTSAPI)
    assert manager.tts_provider_insts == [provider]
    assert (
        await manager.get_using_provider_async(ProviderType.TEXT_TO_SPEECH) is provider
    )
    await provider.terminate()
