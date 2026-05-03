from types import SimpleNamespace

import pytest

import astrbot.core.provider.sources.gemini_source as gemini_source_module
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI


def _make_provider_config(overrides: dict | None = None) -> dict:
    config = {
        "id": "test-gemini",
        "type": "googlegenai_chat_completion",
        "model": "gemini-2.5-pro",
        "key": ["test-key"],
        "timeout": 180,
        "gm_safety_settings": {},
    }
    if overrides:
        config.update(overrides)
    return config


class _FakeGeminiClient:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


def test_gemini_client_forces_httpx_client_and_keeps_env_proxy(monkeypatch):
    captured: dict[str, object] = {}
    httpx_client = _FakeGeminiClient()

    def fake_httpx_client(**kwargs):
        captured["httpx_client_kwargs"] = kwargs
        return httpx_client

    def fake_client(api_key, http_options):
        captured["api_key"] = api_key
        captured["http_options"] = http_options
        return SimpleNamespace(aio=SimpleNamespace())

    monkeypatch.setenv("HTTPS_PROXY", "http://global-proxy.example:8080")
    monkeypatch.setattr(gemini_source_module.httpx, "AsyncClient", fake_httpx_client)
    monkeypatch.setattr(gemini_source_module.genai, "Client", fake_client)

    ProviderGoogleGenAI(_make_provider_config(), {})

    http_options = captured["http_options"]
    assert captured["api_key"] == "test-key"
    assert captured["httpx_client_kwargs"] == {"timeout": 180, "trust_env": True}
    assert http_options.httpx_async_client is httpx_client


def test_gemini_client_passes_proxy_to_httpx_client_without_logging_it(monkeypatch):
    captured: dict[str, object] = {}
    httpx_client = _FakeGeminiClient()
    proxy = "socks5://user:secret@127.0.0.1:1080"

    def fake_httpx_client(**kwargs):
        captured["httpx_client_kwargs"] = kwargs
        return httpx_client

    def fake_client(api_key, http_options):
        captured["http_options"] = http_options
        return SimpleNamespace(aio=SimpleNamespace())

    def fake_log(message):
        captured["log_message"] = message

    monkeypatch.setattr(gemini_source_module.httpx, "AsyncClient", fake_httpx_client)
    monkeypatch.setattr(gemini_source_module.genai, "Client", fake_client)
    monkeypatch.setattr(gemini_source_module.logger, "info", fake_log)

    ProviderGoogleGenAI(_make_provider_config({"proxy": proxy}), {})

    http_options = captured["http_options"]
    assert captured["httpx_client_kwargs"] == {
        "timeout": 180,
        "trust_env": True,
        "proxy": proxy,
    }
    assert http_options.httpx_async_client is httpx_client
    assert "secret" not in captured["log_message"]
    assert proxy not in captured["log_message"]


@pytest.mark.asyncio
async def test_gemini_api_key_error_log_does_not_include_key(monkeypatch):
    captured: dict[str, str] = {}
    api_key = "sensitive-api-key-value"

    def fake_log(message):
        captured["message"] = message

    monkeypatch.setattr(gemini_source_module.logger, "error", fake_log)

    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.chosen_api_key = api_key
    error = SimpleNamespace(code=429, message="quota exceeded")

    with pytest.raises(Exception, match="Gemini"):
        await provider._handle_api_error(error, [api_key])

    assert api_key not in captured["message"]
    assert api_key[:12] not in captured["message"]


def test_gemini_empty_output_raises_empty_model_output_error():
    llm_response = LLMResponse(role="assistant")

    with pytest.raises(EmptyModelOutputError):
        ProviderGoogleGenAI._ensure_usable_response(
            llm_response,
            response_id="resp_empty",
            finish_reason="STOP",
        )


def test_gemini_reasoning_only_output_is_allowed():
    llm_response = LLMResponse(
        role="assistant",
        reasoning_content="chain of thought placeholder",
    )

    ProviderGoogleGenAI._ensure_usable_response(
        llm_response,
        response_id="resp_reasoning",
        finish_reason="STOP",
    )
