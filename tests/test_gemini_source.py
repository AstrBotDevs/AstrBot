from types import SimpleNamespace

import httpx
import pytest

import astrbot.core.provider.sources.request_retry as request_retry
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
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


_FAKE_TOOL_CALL_CONTEXTS = [
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "fake_recall_abc",
                "type": "function",
                "function": {
                    "name": "recall_long_term_memory",
                    "arguments": '{"query": "我的名字是？", "k": 5}',
                },
            }
        ],
    },
    {"role": "tool", "tool_call_id": "fake_recall_abc", "content": "memory json"},
]


def _make_provider() -> ProviderGoogleGenAI:
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.api_keys = [""]
    provider.model_name = ""
    return provider


def _assert_reordered_tail(messages: list[dict]) -> None:
    assert messages[-3]["role"] == "user"
    assert messages[-3]["content"] == "我的名字是？"
    assert messages[-2]["role"] == "assistant"
    assert messages[-2]["tool_calls"][0]["id"] == "fake_recall_abc"
    assert (
        messages[-2]["tool_calls"][0]["function"]["name"] == "recall_long_term_memory"
    )
    assert messages[-1]["role"] == "tool"
    assert messages[-1]["tool_call_id"] == "fake_recall_abc"


@pytest.mark.asyncio
async def test_text_chat_reorders_fake_tool_call_pair(monkeypatch):
    captured = {}

    async def fake_query(payloads, tools, *, request_max_retries=None):
        captured["payloads"] = payloads
        return LLMResponse(role="assistant")

    provider = _make_provider()
    monkeypatch.setattr(provider, "_query", fake_query)

    await provider.text_chat(prompt="我的名字是？", contexts=_FAKE_TOOL_CALL_CONTEXTS)

    messages = captured["payloads"]["messages"]
    _assert_reordered_tail(messages)

    # 转换后的 contents 应为 user → model(functionCall) → user(functionResponse)
    contents = provider._prepare_conversation(captured["payloads"])
    assert [content.role for content in contents] == ["user", "model", "user"]
    assert contents[0].parts[0].text == "我的名字是？"
    assert contents[1].parts[0].function_call.name == "recall_long_term_memory"
    assert contents[2].parts[0].function_response.name == "fake_recall_abc"


@pytest.mark.asyncio
async def test_text_chat_stream_reorders_fake_tool_call_pair(monkeypatch):
    captured = {}

    async def fake_query_stream(payloads, tools, *, request_max_retries=None):
        captured["payloads"] = payloads
        return
        yield  # pragma: no cover

    provider = _make_provider()
    monkeypatch.setattr(provider, "_query_stream", fake_query_stream)

    async for _ in provider.text_chat_stream(
        prompt="我的名字是？",
        contexts=_FAKE_TOOL_CALL_CONTEXTS,
    ):
        pass

    messages = captured["payloads"]["messages"]
    _assert_reordered_tail(messages)


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
