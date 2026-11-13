import asyncio
import copy
import io
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.sources import deepseek_stt_api_source
from astrbot.core.provider.sources.deepseek_stt_api_source import (
    DeepSeekSTTError,
    ProviderDeepSeekSTTAPI,
)


def _write_wav(
    path: Path,
    *,
    duration: float = 0.01,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        frame_count = int(duration * sample_rate)
        wav_file.writeframes(b"\x00" * sample_width * channels * frame_count)


def _temp_files(tmp_path: Path) -> list[Path]:
    return list((tmp_path / "data" / "temp").glob("deepseek_stt_api_*.wav"))


async def _use_mock_transport(provider: ProviderDeepSeekSTTAPI, handler) -> None:
    headers = provider.client.headers
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=headers,
    )


@pytest.fixture
def mock_ensure_wav(monkeypatch):
    """Simulate conversion while preserving real WAV validation and cleanup.

    Args:
        monkeypatch: Fixture used to replace the provider's audio converter.

    Returns:
        Mock recording conversion calls and writing valid PCM WAV output.
    """

    async def convert(audio_path, output_path, *, sample_rate, channels):
        _write_wav(Path(output_path), sample_rate=sample_rate, channels=channels)
        return output_path

    converter = AsyncMock(side_effect=convert)
    monkeypatch.setattr(deepseek_stt_api_source, "ensure_wav", converter)
    return converter


@pytest_asyncio.fixture
async def provider_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    providers = []

    def make_provider(overrides=None):
        config = {
            "id": "test-deepseek-stt",
            "type": "deepseek_stt_api",
            "provider": "deepseek",
            "provider_type": "speech_to_text",
            "enable": True,
            "api_key": "secret-key",
            "api_base": "https://api.deepseek.com/v1",
            "timeout": "120",
            "proxy": "",
            "custom_headers": {},
        }
        config.update(overrides or {})
        provider = ProviderDeepSeekSTTAPI(config, {})
        providers.append(provider)
        return provider

    yield make_provider
    for provider in providers:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "api_base",
    [
        "https://api.deepseek.com/v1/",
        "https://api.deepseek.com/v1/tools/asr",
    ],
)
async def test_deepseek_stt_request_uses_bearer_auth_and_only_multipart_file(
    provider_factory, tmp_path, api_base
):
    captured = {}

    async def handle_request(request: httpx.Request):
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["body"] = await request.aread()
        return httpx.Response(
            200,
            json={"request_id": "request-1", "text": "转写结果", "duration_ms": 10},
        )

    provider = provider_factory(
        {
            "api_base": api_base,
            "custom_headers": {
                "X-Trace-Id": "trace-123",
                "Content-Type": "application/json",
                "Authorization": "Bearer wrong-key",
            },
        }
    )
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "voice.wav"
    _write_wav(audio_path)

    assert await provider.get_text(str(audio_path)) == "转写结果"
    assert captured["url"] == "https://api.deepseek.com/v1/tools/asr"
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["headers"]["X-Trace-Id"] == "trace-123"
    assert captured["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert captured["body"].count(b'name="file"') == 1
    assert b'filename="audio.wav"' in captured["body"]
    assert b"Content-Type: audio/wav" in captured["body"]
    assert b'name="model"' not in captured["body"]
    assert b'name="language"' not in captured["body"]
    assert b"application/json" not in captured["body"]


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["", "  \n"])
async def test_deepseek_stt_returns_empty_transcription_without_placeholder(
    provider_factory, tmp_path, text
):
    async def handle_request(_request):
        return httpx.Response(200, json={"text": text})

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "voice.wav"
    _write_wav(audio_path)

    assert await provider.get_text(str(audio_path)) == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"text": None},
        {"text": 123},
        [],
    ],
)
async def test_deepseek_stt_rejects_malformed_success_responses(
    provider_factory, tmp_path, payload
):
    async def handle_request(_request):
        return httpx.Response(200, json=payload)

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "voice.wav"
    _write_wav(audio_path)

    with pytest.raises(DeepSeekSTTError, match="missing a string text field"):
        await provider.get_text(str(audio_path))


@pytest.mark.asyncio
async def test_deepseek_stt_rejects_non_json_response(provider_factory, tmp_path):
    async def handle_request(_request):
        return httpx.Response(200, text="not JSON secret-key")

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "voice.wav"
    _write_wav(audio_path)

    with pytest.raises(DeepSeekSTTError, match="non-JSON") as exc_info:
        await provider.get_text(str(audio_path))
    assert "secret-key" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 503])
async def test_deepseek_stt_http_errors_do_not_leak_response_content(
    provider_factory, tmp_path, status
):
    async def handle_request(_request):
        return httpx.Response(status, json={"error": "secret-key private text"})

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "voice.wav"
    _write_wav(audio_path)

    with pytest.raises(DeepSeekSTTError, match=f"HTTP {status}") as exc_info:
        await provider.get_text(str(audio_path))
    assert "secret-key" not in str(exc_info.value)
    assert "private text" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_deepseek_stt_timeout_is_reported_without_sensitive_details(
    provider_factory, tmp_path
):
    async def handle_request(_request):
        raise httpx.ReadTimeout("secret-key timed out")

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "voice.wav"
    _write_wav(audio_path)

    with pytest.raises(DeepSeekSTTError, match="request failed") as exc_info:
        await provider.get_text(str(audio_path))
    assert "secret-key" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_deepseek_stt_missing_and_empty_files_do_not_send_requests(
    provider_factory, tmp_path
):
    request_count = 0

    async def handle_request(_request):
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={"text": "unexpected"})

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    missing_path = tmp_path / "missing.wav"
    empty_path = tmp_path / "empty.wav"
    empty_path.write_bytes(b"")

    with pytest.raises(FileNotFoundError):
        await provider.get_text(str(missing_path))
    with pytest.raises(ValueError, match="input audio is empty"):
        await provider.get_text(str(empty_path))
    assert request_count == 0
    assert empty_path.exists()


@pytest.mark.asyncio
async def test_deepseek_stt_conversion_failure_cleans_temp_and_preserves_original(
    provider_factory, tmp_path, monkeypatch
):
    async def fail_conversion(*_args, **_kwargs):
        raise RuntimeError("ffmpeg conversion failed")

    monkeypatch.setattr(deepseek_stt_api_source, "ensure_wav", fail_conversion)
    provider = provider_factory()
    request_count = 0

    async def handle_request(_request):
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={"text": "unexpected"})

    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "eight-bit.wav"
    _write_wav(audio_path, sample_width=1)
    original_bytes = audio_path.read_bytes()

    with pytest.raises(RuntimeError, match="ffmpeg conversion failed"):
        await provider.get_text(str(audio_path))
    assert request_count == 0
    assert audio_path.read_bytes() == original_bytes
    assert _temp_files(tmp_path) == []


@pytest.mark.asyncio
async def test_deepseek_stt_converts_to_mono_16khz_16bit_pcm_before_upload(
    provider_factory, tmp_path, mock_ensure_wav
):
    captured = {}

    async def handle_request(request: httpx.Request):
        captured["body"] = await request.aread()
        return httpx.Response(200, json={"text": "converted"})

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "stereo.wav"
    _write_wav(
        audio_path,
        sample_rate=44100,
        channels=2,
        sample_width=1,
    )
    original_bytes = audio_path.read_bytes()

    assert await provider.get_text(str(audio_path)) == "converted"
    mock_ensure_wav.assert_awaited_once_with(
        str(audio_path),
        mock_ensure_wav.await_args.args[1],
        sample_rate=16000,
        channels=1,
    )
    uploaded_wav = captured["body"][
        captured["body"].index(b"RIFF") : captured["body"].rindex(b"\r\n--")
    ]
    with wave.open(io.BytesIO(uploaded_wav), "rb") as wav_file:
        assert wav_file.getframerate() == 16000
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getcomptype() == "NONE"
    assert audio_path.read_bytes() == original_bytes
    assert _temp_files(tmp_path) == []


@pytest.mark.asyncio
async def test_deepseek_stt_rejects_audio_over_size_limit_without_request(
    provider_factory, tmp_path
):
    request_count = 0

    async def handle_request(_request):
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={"text": "unexpected"})

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "oversized.wav"
    _write_wav(audio_path)
    with audio_path.open("ab") as audio_file:
        audio_file.truncate(8 * 1024 * 1024 + 1)

    with pytest.raises(ValueError, match="8 MiB"):
        await provider.get_text(str(audio_path))
    assert request_count == 0
    assert audio_path.exists()


@pytest.mark.asyncio
async def test_deepseek_stt_allows_exact_size_limit(provider_factory, tmp_path):
    request_count = 0

    async def handle_request(request: httpx.Request):
        nonlocal request_count
        request_count += 1
        assert len(await request.aread()) > 8 * 1024 * 1024
        return httpx.Response(200, json={"text": "boundary"})

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "size-boundary.wav"
    _write_wav(audio_path)
    with audio_path.open("ab") as audio_file:
        audio_file.truncate(8 * 1024 * 1024)

    assert await provider.get_text(str(audio_path)) == "boundary"
    assert request_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("duration", "should_request"),
    [(120, True), (120.01, False)],
)
async def test_deepseek_stt_enforces_duration_boundary(
    provider_factory, tmp_path, duration, should_request
):
    request_count = 0

    async def handle_request(_request):
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={"text": "boundary"})

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / f"duration-{duration}.wav"
    _write_wav(audio_path, duration=duration)

    if should_request:
        assert await provider.get_text(str(audio_path)) == "boundary"
    else:
        with pytest.raises(ValueError, match="120 second"):
            await provider.get_text(str(audio_path))
    assert (request_count == 1) is should_request


@pytest.mark.asyncio
async def test_deepseek_stt_request_failure_cleans_converted_temp_and_preserves_original(
    provider_factory, tmp_path, mock_ensure_wav
):
    async def handle_request(request: httpx.Request):
        await request.aread()
        return httpx.Response(400, json={"error": "invalid audio"})

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "request-failure.wav"
    _write_wav(audio_path, sample_width=1)
    original_bytes = audio_path.read_bytes()

    with pytest.raises(DeepSeekSTTError, match="HTTP 400"):
        await provider.get_text(str(audio_path))
    mock_ensure_wav.assert_awaited_once()
    assert audio_path.read_bytes() == original_bytes
    assert _temp_files(tmp_path) == []


@pytest.mark.asyncio
async def test_deepseek_stt_cancellation_cleans_temp_and_preserves_original(
    provider_factory, tmp_path, mock_ensure_wav
):
    request_started = asyncio.Event()

    async def handle_request(_request):
        request_started.set()
        await asyncio.Event().wait()
        return httpx.Response(200, json={"text": "unreachable"})

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "cancel.wav"
    _write_wav(audio_path, sample_width=1)
    original_bytes = audio_path.read_bytes()
    task = asyncio.create_task(provider.get_text(str(audio_path)))
    await asyncio.wait_for(request_started.wait(), timeout=5)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    mock_ensure_wav.assert_awaited_once()
    assert audio_path.read_bytes() == original_bytes
    assert _temp_files(tmp_path) == []


@pytest.mark.asyncio
async def test_deepseek_stt_cancellation_during_conversion_kills_ffmpeg_and_cleans(
    provider_factory, tmp_path, monkeypatch
):
    conversion_started = asyncio.Event()

    class FakeProcess:
        def __init__(self, output_path):
            self.output_path = output_path
            self.returncode = None
            self.killed = False

        async def communicate(self):
            if self.killed:
                return b"", b""
            conversion_started.set()
            await asyncio.Event().wait()

        def kill(self):
            self.killed = True
            self.returncode = -9
            self.output_path.write_bytes(b"partial WAV")

    process = None

    async def fake_create_subprocess_exec(*args, **_kwargs):
        nonlocal process
        process = FakeProcess(Path(args[-1]))
        return process

    monkeypatch.setattr(
        "astrbot.core.utils.media_utils.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    provider = provider_factory()
    audio_path = tmp_path / "cancel-conversion.wav"
    _write_wav(audio_path, sample_width=1)
    original_bytes = audio_path.read_bytes()
    task = asyncio.create_task(provider.get_text(str(audio_path)))
    await asyncio.wait_for(conversion_started.wait(), timeout=2)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed
    assert audio_path.read_bytes() == original_bytes
    assert _temp_files(tmp_path) == []


@pytest.mark.asyncio
async def test_deepseek_stt_concurrent_conversions_use_unique_temp_files(
    provider_factory, tmp_path, mock_ensure_wav
):
    async def handle_request(request: httpx.Request):
        await request.aread()
        await asyncio.sleep(0.01)
        return httpx.Response(200, json={"text": "concurrent"})

    provider = provider_factory()
    await _use_mock_transport(provider, handle_request)
    audio_path = tmp_path / "concurrent.wav"
    _write_wav(audio_path, sample_width=1)

    results = await asyncio.gather(
        *(provider.get_text(str(audio_path)) for _ in range(4))
    )

    assert results == ["concurrent"] * 4
    assert mock_ensure_wav.await_count == 4
    conversion_paths = [call.args[1] for call in mock_ensure_wav.await_args_list]
    assert len(set(conversion_paths)) == 4
    assert audio_path.exists()
    assert _temp_files(tmp_path) == []


@pytest.mark.asyncio
async def test_deepseek_stt_terminate_closes_client(provider_factory):
    provider = provider_factory()

    await provider.terminate()

    assert provider.client.is_closed


@pytest.mark.asyncio
async def test_deepseek_stt_manager_loads_template_and_selects_provider():
    provider_metadata = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]
    template = provider_metadata["config_template"]["DeepSeek STT(API)"]
    assert template["api_base"] == "https://api.deepseek.com/v1"
    assert template["provider_type"] == "speech_to_text"
    assert "model" not in template

    provider_config = copy.deepcopy(template)
    provider_config["enable"] = True
    provider_config["api_key"] = "test-key"
    config = {
        "provider": [provider_config],
        "provider_sources": [],
        "provider_settings": {},
        "provider_stt_settings": {
            "enable": True,
            "provider_id": "deepseek_stt",
        },
        "provider_tts_settings": {},
        "agent": {
            "runtime": "astrbot",
            "config": {"model": {"provider_id": ""}},
        },
    }
    acm = SimpleNamespace(confs={"default": config}, get_conf=lambda _umo=None: config)
    manager = ProviderManager(acm, None, SimpleNamespace(default_persona="default"))

    await manager.load_provider(copy.deepcopy(provider_config))

    provider = manager.inst_map["deepseek_stt"]
    assert isinstance(provider, ProviderDeepSeekSTTAPI)
    assert manager.stt_provider_insts == [provider]
    assert (
        await manager.get_using_provider_async(ProviderType.SPEECH_TO_TEXT) is provider
    )
    await provider.terminate()
