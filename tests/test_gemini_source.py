from types import SimpleNamespace

import httpx
import pytest

import astrbot.core.provider.sources.request_retry as request_retry
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.modalities import sanitize_contexts_by_modalities
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI


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


def test_gemini_drops_empty_media_and_assistant_parts():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    contents = provider._prepare_conversation(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,"},
                        }
                    ],
                },
                {"role": "assistant", "content": ""},
                {
                    "role": "assistant",
                    "content": [{"type": "think", "think": "failed turn"}],
                },
                {"role": "user", "content": "continue"},
            ]
        }
    )

    assert len(contents) == 1
    assert contents[0].role == "user"
    assert [part.text for part in contents[0].parts] == [
        "[Media unavailable]",
        "continue",
    ]


def test_gemini_keeps_non_empty_data_image():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    contents = provider._prepare_conversation(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,AA=="},
                        }
                    ],
                }
            ]
        }
    )

    image_part = contents[0].parts[0]
    assert image_part.inline_data is not None
    assert image_part.inline_data.data == b"\x00"


def test_provider_context_sanitizer_removes_think_only_assistant():
    contexts, stats = sanitize_contexts_by_modalities(
        [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": [{"type": "think", "think": "failed turn"}],
                "reasoning_content": "failed turn",
            },
            {"role": "user", "content": "try again"},
        ],
        ["text", "image", "audio", "tool_use"],
    )

    assert [message["role"] for message in contexts] == ["user", "user"]
    assert stats.removed_empty_assistant_messages == 1


@pytest.mark.asyncio
async def test_gemini_empty_proxy_ignores_process_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
    provider = ProviderGoogleGenAI(
        {
            "key": ["test-key"],
            "model": "gemini-3.1-flash-lite",
            "api_base": "https://api.example.test",
            "proxy": "",
        },
        {},
    )

    assert provider._http_client is not None
    assert provider._http_client._trust_env is False
    await provider.terminate()


@pytest.mark.asyncio
async def test_gemini_get_models_retries_transient_request_error(monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)

    class FakeModels:
        def __init__(self):
            self.calls = 0

        async def list(self):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError("temporary connection failure")
            return [
                SimpleNamespace(
                    name="models/gemini-a",
                    supported_actions=["generateContent"],
                ),
                SimpleNamespace(
                    name="models/gemini-b",
                    supported_actions=["embedContent"],
                ),
            ]

    models = FakeModels()
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.client = SimpleNamespace(models=models)

    assert await provider.get_models() == ["gemini-a"]
    assert models.calls == 2


@pytest.mark.asyncio
async def test_gemini_rate_limit_fails_fast_without_key_rotation():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.chosen_api_key = "rate-limited-key"

    with pytest.raises(Exception, match="rate limit reached"):
        await provider._handle_api_error(
            SimpleNamespace(code=429, message="RESOURCE_EXHAUSTED"),
            ["rate-limited-key", "unused-second-key"],
        )

    assert provider.chosen_api_key == "rate-limited-key"


@pytest.mark.asyncio
async def test_gemini_excludes_native_code_execution_with_function_tools():
    provider = ProviderGoogleGenAI(
        {
            "key": ["test-key"],
            "model": "gemini-2.5-flash",
            "api_base": "https://generativelanguage.googleapis.com",
            "gm_native_coderunner": True,
            "gm_native_search": True,
            "gm_url_context": True,
        },
        {},
    )
    tools = ToolSet(
        [
            FunctionTool(
                name="test_tool",
                description="A test function tool.",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )

    config = await provider._prepare_query_config({}, tools)

    assert config.tools is not None
    assert all(tool.code_execution is None for tool in config.tools)
    assert all(tool.google_search is None for tool in config.tools)
    assert all(tool.url_context is None for tool in config.tools)
    assert any(tool.function_declarations for tool in config.tools)
    await provider.terminate()


@pytest.mark.asyncio
async def test_gemini_forwards_request_level_latency_controls(monkeypatch):
    provider = ProviderGoogleGenAI(
        {
            "key": ["test-key"],
            "model": "gemini-3.5-flash",
            "api_base": "https://generativelanguage.googleapis.com",
            "gm_thinking_config": {"level": "high"},
        },
        {},
    )
    captured = {}

    async def fake_query(payloads, tools, *, request_max_retries=None):
        captured.update(payloads)
        return LLMResponse("assistant", completion_text="ok")

    monkeypatch.setattr(provider, "_query", fake_query)

    await provider.text_chat(
        prompt="classify image",
        max_tokens=160,
        temperature=0.1,
        thinking_level="minimal",
        request_max_retries=0,
    )

    assert captured["max_tokens"] == 160
    assert captured["temperature"] == 0.1
    assert captured["thinking_level"] == "minimal"
    config = await provider._prepare_query_config(captured)
    assert config.max_output_tokens == 160
    assert str(config.thinking_config.thinking_level).endswith("MINIMAL")
    await provider.terminate()
