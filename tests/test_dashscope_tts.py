from astrbot.core.provider.sources import dashscope_tts
from astrbot.core.provider.sources.dashscope_tts import ProviderDashscopeTTSAPI


def make_provider(model: str) -> ProviderDashscopeTTSAPI:
    return ProviderDashscopeTTSAPI(
        {
            "id": "dashscope_tts",
            "type": "dashscope_tts",
            "model": model,
            "api_key": "test-key",
            "dashscope_tts_voice": "test-voice",
        },
        {},
    )


def test_realtime_qwen_vc_models_raise_clear_error(monkeypatch):
    provider = make_provider("qwen3-tts-vc-realtime-2026-01-15")
    called = False

    class FakeMultiModalConversation:
        @staticmethod
        def call(**kwargs):
            nonlocal called
            called = True
            return kwargs

    monkeypatch.setattr(
        dashscope_tts, "MultiModalConversation", FakeMultiModalConversation
    )

    try:
        provider._call_qwen_tts(provider.get_model(), "hello")
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive branch for clearer assertion failure
        raise AssertionError("Expected realtime Qwen VC model to raise RuntimeError")

    assert "realtime voice-clone model" in message
    assert "astrbot_plugin_qwen_tts" in message
    assert not called


def test_regular_qwen_tts_models_still_use_multimodal_conversation(monkeypatch):
    provider = make_provider("qwen-tts-latest")
    captured = {}

    class FakeMultiModalConversation:
        @staticmethod
        def call(**kwargs):
            captured.update(kwargs)
            return {"ok": True}

    monkeypatch.setattr(
        dashscope_tts, "MultiModalConversation", FakeMultiModalConversation
    )

    result = provider._call_qwen_tts(provider.get_model(), "hello")

    assert result == {"ok": True}
    assert captured["model"] == "qwen-tts-latest"
    assert captured["messages"] is None
    assert captured["voice"] == "test-voice"
    assert captured["text"] == "hello"
