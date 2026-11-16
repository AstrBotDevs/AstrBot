from unittest.mock import AsyncMock

import pytest

import astrbot.core.provider.sources.dashscope_tts as mod


@pytest.fixture(autouse=True)
def isolate_sdk_and_output(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.dashscope, "api_key", "sk-global")
    monkeypatch.setattr(
        mod.dashscope,
        "base_websocket_api_url",
        "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
    )
    monkeypatch.setattr(mod, "get_astrbot_temp_path", lambda: str(tmp_path))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "uses_speech_synthesizer"),
    [
        ("qwen-audio-3.0-tts-plus", True),
        ("QWEN-AUDIO-3.0-TTS-PLUS", True),
        ("qwen3-tts-flash", False),
        ("cosyvoice-v1", True),
    ],
)
async def test_model_routing(monkeypatch, model, uses_speech_synthesizer):
    provider = mod.ProviderDashscopeTTSAPI(
        {"api_key": "sk-test", "model": model}, {}
    )
    speech = AsyncMock(return_value=(b"audio", ".wav"))
    multimodal = AsyncMock(return_value=(b"audio", ".wav"))
    monkeypatch.setattr(provider, "_synthesize_with_cosyvoice", speech)
    monkeypatch.setattr(provider, "_synthesize_with_qwen_tts", multimodal)

    await provider.get_audio("Hello")

    selected, unused = (
        (speech, multimodal) if uses_speech_synthesizer else (multimodal, speech)
    )
    selected.assert_awaited_once_with(model, "Hello")
    unused.assert_not_called()


@pytest.mark.asyncio
async def test_sdk_instances_keep_their_endpoint_and_api_key(monkeypatch):
    default_url = mod.dashscope.base_websocket_api_url
    custom_url = "wss://custom.example/api-ws/v1/inference"
    first = mod.ProviderDashscopeTTSAPI(
        {
            "api_key": "sk-A",
            "model": "qwen-audio-3.0-tts-plus",
            "dashscope_tts_websocket_url": f" {custom_url} ",
            "custom_headers": {
                "authorization": "Bearer wrong",
                "AUTHORIZATION": "Bearer also-wrong",
                "X-Test": "retained",
            },
        },
        {},
    )
    second = mod.ProviderDashscopeTTSAPI(
        {"api_key": "sk-B", "model": "cosyvoice-v1"}, {}
    )
    captured = {}

    def capture_request(instance, text, timeout):
        captured[text] = (
            instance.url,
            instance.request.get_websocket_headers(
                instance.headers, instance.workspace
            ),
        )
        return b"audio"

    # Keep real SDK construction and header merging; stop before network I/O.
    monkeypatch.setattr(mod.SpeechSynthesizer, "call", capture_request)

    # B's initialization overwrites the SDK global key before A synthesizes.
    assert mod.dashscope.api_key == "sk-B"
    await first.get_audio("A")
    await second.get_audio("B")

    for label, expected_url in [("A", custom_url), ("B", default_url)]:
        actual_url, headers = captured[label]
        assert actual_url == expected_url
        assert [
            value
            for name, value in headers.items()
            if name.lower() == "authorization"
        ] == [f"Bearer sk-{label}"]

    assert captured["A"][1]["x-test"] == "retained"
    assert mod.dashscope.base_websocket_api_url == default_url
    assert mod.dashscope.api_key == "sk-B"
