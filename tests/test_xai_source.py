from types import SimpleNamespace

import pytest

from astrbot.core.agent.message import AssistantMessageSegment, ToolCallMessageSegment
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.entities import ToolCallsResult
from astrbot.core.provider.sources.xai_source import ProviderXAIResponses


class _FakeResponsesClient:
    def __init__(self, response=None, stream=None):
        self.calls = []
        self._response = response
        self._stream = stream

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return self._stream
        return self._response


class _FakeAsyncStream:
    def __init__(self, events):
        self._events = events

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for event in self._events:
            yield event


def _event(event_type: str, **kwargs):
    return SimpleNamespace(type=event_type, **kwargs)


def _make_xai_responses_provider(
    overrides: dict | None = None,
) -> ProviderXAIResponses:
    provider_config = {
        "id": "test-xai-responses",
        "type": "xai_responses",
        "provider": "xai",
        "model": "grok-4.20-reasoning",
        "key": ["test-key"],
        "api_base": "https://api.x.ai/v1",
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderXAIResponses(
        provider_config=provider_config,
        provider_settings={},
    )


@pytest.mark.asyncio
async def test_xai_responses_native_search_injects_web_search_tool_with_filters():
    provider = _make_xai_responses_provider(
        {
            "xai_web_search_config": {
                "enabled": True,
                "allowed_domains": ["example.com"],
                "enable_image_understanding": True,
            },
        }
    )
    provider.client.responses = _FakeResponsesClient(
        response=SimpleNamespace(id="resp_1", output_text="ok", usage=None)
    )
    try:
        await provider.text_chat(prompt="search")

        assert provider.client.responses.calls[0]["tools"] == [
            {
                "type": "web_search",
                "filters": {"allowed_domains": ["example.com"]},
                "enable_image_understanding": True,
            }
        ]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_xai_responses_search_rejects_mutually_exclusive_domain_filters():
    provider = _make_xai_responses_provider(
        {
            "xai_web_search_config": {
                "enabled": True,
                "allowed_domains": ["example.com"],
                "excluded_domains": ["blocked.example"],
            },
        }
    )
    try:
        with pytest.raises(ValueError, match="allowed_domains.*excluded_domains"):
            await provider.text_chat(prompt="search")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_xai_responses_combines_native_and_function_tools():
    provider = _make_xai_responses_provider(
        {
            "xai_web_search_config": {"enabled": True},
        }
    )
    provider.client.responses = _FakeResponsesClient(
        response=SimpleNamespace(id="resp_1", output_text="ok", usage=None)
    )
    tool_set = ToolSet(
        [
            FunctionTool(
                name="lookup",
                description="Lookup an item",
                parameters={"type": "object", "properties": {}},
                handler=None,
            )
        ]
    )
    try:
        await provider.text_chat(prompt="use tools", func_tool=tool_set)

        assert provider.client.responses.calls[0]["tools"] == [
            {"type": "web_search"},
            {
                "type": "function",
                "name": "lookup",
                "description": "Lookup an item",
                "parameters": {"type": "object", "properties": {}},
            },
        ]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_xai_responses_builds_web_search_and_x_search_from_grouped_config():
    provider = _make_xai_responses_provider(
        {
            "xai_web_search_config": {
                "enabled": True,
                "excluded_domains": ["blocked.example"],
                "enable_image_understanding": True,
            },
            "xai_x_search_config": {
                "enabled": True,
                "allowed_x_handles": ["grok"],
                "enable_image_understanding": True,
                "enable_video_understanding": True,
            },
        }
    )
    provider.client.responses = _FakeResponsesClient(
        response=SimpleNamespace(id="resp_1", output_text="ok", usage=None)
    )
    try:
        await provider.text_chat(prompt="search")

        assert provider.client.responses.calls[0]["tools"] == [
            {
                "type": "web_search",
                "filters": {"excluded_domains": ["blocked.example"]},
                "enable_image_understanding": True,
            },
            {
                "type": "x_search",
                "allowed_x_handles": ["grok"],
                "enable_image_understanding": True,
                "enable_video_understanding": True,
            },
        ]
    finally:
        await provider.terminate()


def test_xai_responses_template_exposes_separate_tool_config_groups():
    provider_meta = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]
    template = provider_meta["config_template"]["xAI Responses"]
    items = provider_meta["items"]

    assert template["xai_web_search_config"] == {
        "enabled": True,
        "allowed_domains": [],
        "excluded_domains": [],
        "enable_image_understanding": False,
    }
    assert template["xai_x_search_config"] == {
        "enabled": False,
        "allowed_x_handles": [],
        "excluded_x_handles": [],
        "enable_image_understanding": False,
        "enable_video_understanding": False,
    }
    assert items["xai_web_search_config"]["type"] == "object"
    assert set(items["xai_web_search_config"]["items"]) == {
        "enabled",
        "allowed_domains",
        "excluded_domains",
        "enable_image_understanding",
    }
    assert items["xai_x_search_config"]["type"] == "object"
    assert set(items["xai_x_search_config"]["items"]) == {
        "enabled",
        "allowed_x_handles",
        "excluded_x_handles",
        "enable_image_understanding",
        "enable_video_understanding",
    }


@pytest.mark.asyncio
async def test_xai_responses_ignores_generic_response_builtin_tools():
    provider = _make_xai_responses_provider(
        {
            "response_builtin_tools": ["code_interpreter"],
        }
    )
    provider.client.responses = _FakeResponsesClient(
        response=SimpleNamespace(id="resp_1", output_text="ok", usage=None)
    )
    try:
        await provider.text_chat(prompt="use tools")

        assert "tools" not in provider.client.responses.calls[0]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_xai_responses_stream_tool_call_history_uses_function_call_items():
    provider = _make_xai_responses_provider()
    provider.client.responses = _FakeResponsesClient(
        stream=_FakeAsyncStream(
            [
                _event(
                    "response.completed",
                    response=SimpleNamespace(id="resp_2", output_text="done"),
                )
            ]
        )
    )
    tool_call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "lookup", "arguments": '{"query":"weather"}'},
    }
    try:
        chunks = [
            chunk
            async for chunk in provider.text_chat_stream(
                prompt="continue",
                tool_calls_result=ToolCallsResult(
                    tool_calls_info=AssistantMessageSegment(
                        content=None,
                        tool_calls=[tool_call],
                    ),
                    tool_calls_result=[
                        ToolCallMessageSegment(
                            content='{"temperature":21}',
                            tool_call_id="call_1",
                        )
                    ],
                ),
            )
        ]

        call = provider.client.responses.calls[0]
        assert chunks[-1].completion_text == "done"
        assert all("tool_calls" not in item for item in call["input"])
        assert call["input"][-2:] == [
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "lookup",
                "arguments": '{"query":"weather"}',
                "status": "completed",
            },
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": '{"temperature":21}',
            },
        ]
    finally:
        await provider.terminate()
