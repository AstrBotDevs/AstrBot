import asyncio

import dashscope
import pytest

import astrbot.api  # noqa: F401
from astrbot.core.provider.sources import dashscope_tts


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_header", [None, "authorization", "Authorization"])
async def test_cosyvoice_uses_own_key_after_other_provider_initializes(
    monkeypatch, auth_header
):
    monkeypatch.setattr(dashscope, "api_key", "initial-key")
    providers = [
        dashscope_tts.ProviderDashscopeTTSAPI(
            {
                "api_key": key,
                "model": "cosyvoice-v2",
                "custom_headers": {auth_header: "Bearer stale"} if auth_header else {},
            },
            {},
        )
        for key in ("provider-a", "provider-b")
    ]
    observed = {}

    def capture_request(synthesizer, text, timeout):
        headers = synthesizer.request.get_websocket_headers(
            synthesizer.headers, synthesizer.workspace
        )
        observed[text] = [
            value for name, value in headers.items() if name.lower() == "authorization"
        ]
        return b"audio"

    monkeypatch.setattr(dashscope_tts.SpeechSynthesizer, "call", capture_request)
    await asyncio.gather(
        *(
            p._synthesize_with_cosyvoice(p.get_model(), str(i))
            for i, p in enumerate(providers)
        )
    )

    assert observed == {"0": ["Bearer provider-a"], "1": ["Bearer provider-b"]}


def test_qwen_passes_own_key_after_other_provider_initializes(monkeypatch):
    monkeypatch.setattr(dashscope, "api_key", "initial-key")
    provider = dashscope_tts.ProviderDashscopeTTSAPI(
        {"api_key": "provider-a", "model": "qwen-tts"}, {}
    )
    dashscope_tts.ProviderDashscopeTTSAPI(
        {"api_key": "provider-b", "model": "cosyvoice-v2"}, {}
    )
    observed = {}

    def capture_request(**kwargs):
        observed.update(kwargs)

    monkeypatch.setattr(dashscope_tts.MultiModalConversation, "call", capture_request)
    provider._call_qwen_tts(provider.get_model(), "hello")

    assert observed["api_key"] == "provider-a"
