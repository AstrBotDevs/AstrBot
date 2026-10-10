import asyncio
import base64
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.core.provider.sources.dashscope_tts as mod


@pytest.fixture(autouse=True)
def isolate_sdk_and_output(monkeypatch, tmp_path):
    """Isolate SDK globals and audio output for each test.

    Args:
        monkeypatch: Fixture that restores patched attributes after each test.
        tmp_path: Temporary directory for synthesized audio files.
    """
    monkeypatch.setattr(mod.dashscope, "api_key", "sk-test")
    monkeypatch.setattr(
        mod.dashscope,
        "base_websocket_api_url",
        "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
    )
    monkeypatch.setattr(mod, "get_astrbot_temp_path", lambda: str(tmp_path))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model",
    [
        "qwen-audio-3.0-tts-plus",
        "qwen-audio-3.0-tts-flash",
        "QWEN-AUDIO-3.0-TTS-PLUS",
        "cosyvoice-v1",
        "cosyvoice-v2",
        "cosyvoice-v3-plus",
    ],
)
async def test_speech_synthesizer_route_preserves_parameters(monkeypatch, model):
    voice = (
        "qwen-audio-3.0-tts-plus-bailian-test"
        if model.lower().startswith("qwen-audio-")
        else "loongstella"
    )
    provider = mod.ProviderDashscopeTTSAPI(
        {
            "api_key": "sk-test",
            "model": model,
            "dashscope_tts_voice": voice,
            "timeout": "12",
            "custom_headers": {"X-Test": "test"},
        },
        {},
    )
    sdk = MagicMock()
    sdk.return_value.call.return_value = b"speech audio"
    multimodal = MagicMock()
    monkeypatch.setattr(mod, "SpeechSynthesizer", sdk)
    monkeypatch.setattr(mod, "MultiModalConversation", multimodal)

    path = Path(await provider.get_audio("Hello"))

    assert path.suffix == ".wav"
    assert path.read_bytes() == b"speech audio"
    sdk.assert_called_once_with(
        headers={
            **{name.lower(): value for name, value in provider.request_headers.items()},
            "Authorization": "Bearer sk-test",
        },
        model=model,
        voice=voice,
        format=mod.AudioFormat.WAV_24000HZ_MONO_16BIT,
        url=None,
    )
    sdk.return_value.call.assert_called_once_with("Hello", 12000.0)
    multimodal.call.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["qwen3-tts-flash", "qwen-tts", "QWEN3-TTS-FLASH"])
@pytest.mark.parametrize("audio_source", ["base64", "url"])
async def test_multimodal_route_and_audio_output(monkeypatch, model, audio_source):
    provider = mod.ProviderDashscopeTTSAPI(
        {
            "api_key": "sk-test",
            "model": model,
            "dashscope_tts_voice": "Cherry",
            "dashscope_tts_websocket_url": "wss://custom.example/api-ws/v1/inference",
        },
        {},
    )
    audio_url = "https://audio.example/test.wav"
    audio = SimpleNamespace(
        data=base64.b64encode(b"qwen audio").decode()
        if audio_source == "base64"
        else "",
        url=audio_url,
    )
    multimodal = MagicMock()
    multimodal.call.return_value = SimpleNamespace(output=SimpleNamespace(audio=audio))
    sdk = MagicMock()
    download = AsyncMock(return_value=b"qwen audio")
    monkeypatch.setattr(mod, "MultiModalConversation", multimodal)
    monkeypatch.setattr(mod, "SpeechSynthesizer", sdk)
    monkeypatch.setattr(provider, "_download_audio_from_url", download)

    path = Path(await provider.get_audio("Hello"))

    assert path.suffix == ".wav"
    assert path.read_bytes() == b"qwen audio"
    multimodal.call.assert_called_once_with(
        model=model,
        headers=provider.request_headers,
        messages=None,
        api_key="sk-test",
        voice="Cherry",
        text="Hello",
    )
    sdk.assert_not_called()
    if audio_source == "url":
        download.assert_awaited_once_with(audio_url)
    else:
        download.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    ["missing", None, "", "  ", " wss://custom.example/api-ws/v1/inference "],
)
async def test_endpoint_resolution_is_instance_local(monkeypatch, endpoint):
    config = {"api_key": "sk-test", "model": "qwen-audio-3.0-tts-plus"}
    if endpoint != "missing":
        config["dashscope_tts_websocket_url"] = endpoint
    provider = mod.ProviderDashscopeTTSAPI(config, {})
    other = mod.ProviderDashscopeTTSAPI(
        {"api_key": "sk-test", "model": "cosyvoice-v1"}, {}
    )
    default_url = mod.dashscope.base_websocket_api_url
    instances = []
    sdk = mod.SpeechSynthesizer

    def record_call(instance, text, timeout):
        """Capture the real SDK instance without opening a network connection.

        Args:
            instance: SDK synthesizer constructed by the provider.
            text: Text supplied to the synthesis call.
            timeout: Synthesis timeout in milliseconds.

        Returns:
            Dummy audio bytes for the provider to save.
        """
        instances.append(instance)
        return b"audio"

    monkeypatch.setattr(sdk, "call", record_call)
    await provider.get_audio("First")
    await other.get_audio("Second")

    expected_url = endpoint.strip() if endpoint and endpoint != "missing" else ""
    assert instances[0].url == (expected_url or default_url)
    assert instances[1].url == default_url
    assert mod.dashscope.base_websocket_api_url == default_url


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["qwen-audio-3.0-tts-plus", "cosyvoice-v1"])
@pytest.mark.parametrize("concurrent", [False, True])
@pytest.mark.parametrize(
    "custom_auth",
    [
        {},
        {"Authorization": "Bearer wrong"},
        {"authorization": "Bearer wrong", "AUTHORIZATION": "Bearer also-wrong"},
    ],
)
async def test_instance_api_keys_override_global_and_custom_auth(
    monkeypatch, model, concurrent, custom_auth
):
    providers = [
        mod.ProviderDashscopeTTSAPI(
            {
                "api_key": key,
                "model": model,
                "custom_headers": {
                    **custom_auth,
                    "X-Test": "retained",
                    "User-Agent": "custom-agent",
                },
            },
            {},
        )
        for key in ["sk-provider-A", "sk-provider-B"]
    ]
    assert mod.dashscope.api_key == "sk-provider-B"
    barrier = threading.Barrier(2, timeout=5) if concurrent else None
    captured_headers = {}

    def capture_headers(instance, text, timeout):
        """Generate real SDK headers without opening a WebSocket connection.

        Args:
            instance: Real SDK synthesizer created by the provider.
            text: Unique text identifying the provider invocation.
            timeout: Synthesis timeout passed by the provider.

        Returns:
            Dummy audio bytes for the synthesis result.
        """
        if barrier is not None:
            barrier.wait()
        captured_headers[text] = instance.request.get_websocket_headers(
            instance.headers, instance.workspace
        )
        return b"audio"

    monkeypatch.setattr(mod.SpeechSynthesizer, "call", capture_headers)
    if concurrent:
        await asyncio.gather(
            providers[0]._synthesize_with_cosyvoice(model, "A"),
            providers[1]._synthesize_with_cosyvoice(model, "B"),
        )
    else:
        await providers[0]._synthesize_with_cosyvoice(model, "A")
        await providers[1]._synthesize_with_cosyvoice(model, "B")

    for label, provider in zip(["A", "B"], providers):
        headers = captured_headers[label]
        auth_headers = [
            (name, value)
            for name, value in headers.items()
            if name.lower() == "authorization"
        ]
        assert auth_headers == [("Authorization", f"Bearer sk-provider-{label}")]
        assert headers["x-test"] == "retained"
        assert headers["user-agent"] == "custom-agent"
        assert provider.request_headers == {
            "User-Agent": "custom-agent",
            "X-Test": "retained",
            **custom_auth,
        }
    assert mod.dashscope.api_key == "sk-provider-B"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model", ["qwen-audio-3.0-tts-plus", "cosyvoice-v1", "qwen3-tts-flash"]
)
@pytest.mark.parametrize("outcome", ["empty", "response_error", "sdk_error"])
async def test_synthesis_failures_do_not_write_audio(
    monkeypatch, tmp_path, model, outcome
):
    provider = mod.ProviderDashscopeTTSAPI({"api_key": "sk-test", "model": model}, {})
    sdk = MagicMock()
    multimodal = MagicMock()
    monkeypatch.setattr(mod, "SpeechSynthesizer", sdk)
    monkeypatch.setattr(mod, "MultiModalConversation", multimodal)
    sdk.return_value.call.return_value = b""
    sdk.return_value.get_response.return_value = (
        {"code": "InvalidParameter", "message": "bad voice"}
        if outcome == "response_error"
        else None
    )
    multimodal.call.return_value = SimpleNamespace(output=None, code="InvalidParameter")
    if outcome == "sdk_error":
        sdk.return_value.call.side_effect = ValueError("SDK failure")
        multimodal.call.side_effect = ValueError("SDK failure")

    with pytest.raises(
        ValueError if outcome == "sdk_error" else RuntimeError,
        match="SDK failure" if outcome == "sdk_error" else "Audio synthesis failed",
    ):
        await provider.get_audio("Hello")

    assert not list(tmp_path.glob("*.wav"))
