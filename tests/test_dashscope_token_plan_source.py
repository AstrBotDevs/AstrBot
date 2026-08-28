"""Unit tests for the DashScope Token Plan chat completion provider."""

import astrbot.core.provider.sources.anthropic_source as anthropic_source
import astrbot.core.provider.sources.dashscope_token_plan_source as dashscope_token_plan_source


class _FakeAsyncAnthropic:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def close(self):
        return None


def test_sets_defaults_and_preserves_custom_headers(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = dashscope_token_plan_source.ProviderDashScopeTokenPlan(
        provider_config={
            "id": "dashscope-token-plan-test",
            "type": "dashscope_token_plan_chat_completion",
            "key": ["test-key"],
            "custom_headers": {"X-Trace-Id": "trace-1"},
        },
        provider_settings={},
    )

    assert provider.base_url == dashscope_token_plan_source.DASHSCOPE_API_BASE
    assert provider.get_model() == dashscope_token_plan_source.DASHSCOPE_DEFAULT_MODEL
    assert provider.custom_headers == {
        "User-Agent": dashscope_token_plan_source.DASHSCOPE_USER_AGENT,
        "X-Trace-Id": "trace-1",
    }
    assert provider.client.kwargs["default_headers"] == {
        "User-Agent": dashscope_token_plan_source.DASHSCOPE_USER_AGENT,
        "X-Trace-Id": "trace-1",
    }


def test_restores_required_user_agent_when_blank(monkeypatch):
    """A blank User-Agent is restored to the required Claude Code value."""
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = dashscope_token_plan_source.ProviderDashScopeTokenPlan(
        provider_config={
            "id": "dashscope-token-plan-test",
            "type": "dashscope_token_plan_chat_completion",
            "key": ["test-key"],
            "custom_headers": {"User-Agent": "   "},
        },
        provider_settings={},
    )

    assert provider.custom_headers == {
        "User-Agent": dashscope_token_plan_source.DASHSCOPE_USER_AGENT,
    }


def test_custom_api_base_preserved(monkeypatch):
    """User-configured api_base is preserved (setdefault, not forced)."""
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = dashscope_token_plan_source.ProviderDashScopeTokenPlan(
        provider_config={
            "id": "dashscope-token-plan-test",
            "type": "dashscope_token_plan_chat_completion",
            "key": ["test-key"],
            "api_base": "https://custom.example.com/anthropic",
        },
        provider_settings={},
    )

    assert provider.base_url == "https://custom.example.com/anthropic"


def test_custom_model_preserved(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = dashscope_token_plan_source.ProviderDashScopeTokenPlan(
        provider_config={
            "id": "dashscope-token-plan-test",
            "type": "dashscope_token_plan_chat_completion",
            "key": ["test-key"],
            "model": "qwen3.7-plus",
        },
        provider_settings={},
    )

    assert provider.get_model() == "qwen3.7-plus"


def test_default_model_when_unset(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = dashscope_token_plan_source.ProviderDashScopeTokenPlan(
        provider_config={
            "id": "dashscope-token-plan-test",
            "type": "dashscope_token_plan_chat_completion",
            "key": ["test-key"],
        },
        provider_settings={},
    )

    assert provider.get_model() == dashscope_token_plan_source.DASHSCOPE_DEFAULT_MODEL
