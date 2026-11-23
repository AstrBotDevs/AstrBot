"""Keep provider tool payloads compatible with the installed SDK models."""

import json

import pytest
from anthropic import _base_client as anthropic_base_client
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionMessageCustomToolCall,
    ChatCompletionMessageFunctionToolCall,
)
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_message_function_tool_call import Function
from openai.types.completion_usage import CompletionUsage
from pydantic import ValidationError

from astrbot.core.agent.tool import ToolSet
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial

sdk_httpx = getattr(
    anthropic_base_client, "httpx", getattr(anthropic_base_client, "httpx2", None)
)


def _function_call(
    arguments: object = '{"city":"Shenzhen"}',
) -> ChatCompletionMessageFunctionToolCall:
    return ChatCompletionMessageFunctionToolCall.model_construct(
        id="call-weather",
        type="function",
        function=Function.model_construct(name="lookup_weather", arguments=arguments),
        extra_content={"google": {"thought_signature": "test-signature"}},
    )


def _openai_completion(
    tool_calls: list[object], content: str | None = None
) -> ChatCompletion:
    # SDK response construction can preserve nonconforming compatible-provider data.
    message = ChatCompletionMessage.model_construct(
        role="assistant", content=content, tool_calls=tool_calls
    )
    return ChatCompletion.model_construct(
        id="chatcmpl-tools",
        object="chat.completion",
        created=0,
        model="test-model",
        choices=[
            Choice.model_construct(index=0, message=message, finish_reason="tool_calls")
        ],
        usage=CompletionUsage(prompt_tokens=7, completion_tokens=3, total_tokens=10),
    )


def _openai_provider() -> ProviderOpenAIOfficial:
    provider = ProviderOpenAIOfficial.__new__(ProviderOpenAIOfficial)
    provider.reasoning_key = "reasoning_content"
    return provider


@pytest.mark.asyncio
@pytest.mark.parametrize("serialized", [False, True], ids=["sdk-object", "json-string"])
async def test_openai_function_call_preserves_arguments_identity_and_metadata(
    serialized: bool,
) -> None:
    call = _function_call()
    tool_call = call.model_dump_json() if serialized else call
    response = await _openai_provider()._parse_openai_completion(
        _openai_completion([tool_call]), ToolSet()
    )

    assert response.tools_call_args == [{"city": "Shenzhen"}]
    assert response.tools_call_name == ["lookup_weather"]
    assert response.tools_call_ids == ["call-weather"]
    assert response.tools_call_extra_content == {
        "call-weather": {"google": {"thought_signature": "test-signature"}}
    }
    assert response.id == "chatcmpl-tools"
    assert response.usage is not None
    assert response.usage.input_other == 7
    assert response.usage.output == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ["{}", "null", None, {}, "{"])
async def test_openai_parameterless_and_malformed_argument_fallback_is_preserved(
    arguments: object,
) -> None:
    response = await _openai_provider()._parse_openai_completion(
        _openai_completion([_function_call(arguments)]), ToolSet()
    )

    assert response.tools_call_args == [{}]
    assert response.tools_call_name == ["lookup_weather"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_call",
    [
        "{",
        "{}",
        "[]",
        "null",
        '{"id":"call-bad","type":"function","function":{"name":"lookup_weather"}}',
        '{"id":"call-custom","type":"custom","custom":{"name":"runner","input":"x"}}',
    ],
)
async def test_openai_malformed_serialized_tool_call_uses_sdk_validation(
    tool_call: str,
) -> None:
    with pytest.raises(ValidationError):
        await _openai_provider()._parse_openai_completion(
            _openai_completion([tool_call]), ToolSet()
        )


@pytest.mark.asyncio
async def test_openai_custom_tool_is_skipped_without_hiding_function_calls() -> None:
    custom = ChatCompletionMessageCustomToolCall.model_validate(
        {
            "id": "call-custom",
            "type": "custom",
            "custom": {"name": "runner", "input": "not-function-arguments"},
        }
    )
    response = await _openai_provider()._parse_openai_completion(
        _openai_completion([custom, _function_call()]), ToolSet()
    )

    assert response.tools_call_name == ["lookup_weather"]
    assert response.tools_call_ids == ["call-weather"]

    with pytest.raises(EmptyModelOutputError):
        await _openai_provider()._parse_openai_completion(
            _openai_completion([custom]), ToolSet()
        )


@pytest.mark.asyncio
async def test_openai_without_tools_does_not_parse_tool_payloads() -> None:
    response = await _openai_provider()._parse_openai_completion(
        _openai_completion(["not-json"], content="Text remains available"), None
    )

    assert response.completion_text == "Text remains available"
    assert response.tools_call_args == []


async def _query_anthropic(
    tool_input: object, monkeypatch: pytest.MonkeyPatch
) -> LLMResponse:
    requests: list[bytes] = []

    def handle(request: object) -> object:
        content = getattr(request, "content")
        assert isinstance(content, bytes)
        requests.append(content)
        assert json.loads(content)["model"] == "claude-test"
        return sdk_httpx.Response(
            200,
            json={
                "id": "msg-tools",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call-weather",
                        "name": "lookup_weather",
                        "input": tool_input,
                    }
                ],
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 7, "output_tokens": 3},
            },
        )

    async with sdk_httpx.AsyncClient(
        transport=sdk_httpx.MockTransport(handle)
    ) as http_client:
        monkeypatch.setattr(
            ProviderAnthropic, "_create_http_client", lambda self, config: http_client
        )
        provider = ProviderAnthropic(
            provider_config={
                "id": "test-anthropic",
                "type": "anthropic_chat_completion",
                "model": "claude-test",
                "api_base": "https://provider.test",
                "key": ["test-key"],
            },
            provider_settings={},
        )
        provider.client.max_retries = 0
        try:
            return await provider._query(
                {
                    "model": "claude-test",
                    "messages": [{"role": "user", "content": "Use the tool"}],
                },
                tools=None,
                request_max_retries=1,
            )
        finally:
            await provider.terminate()
            assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_input", [None, [], ["unexpected"], "{}", 42, True])
async def test_anthropic_rejects_non_object_tool_input_without_retry(
    tool_input: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="tool call input must be a JSON object"):
        await _query_anthropic(tool_input, monkeypatch)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_input", [{}, {"city": "Shenzhen", "options": {"days": [1, 2]}}]
)
async def test_anthropic_preserves_valid_and_empty_tool_input(
    tool_input: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    response = await _query_anthropic(tool_input, monkeypatch)

    assert response.tools_call_args == [tool_input]
    assert response.tools_call_name == ["lookup_weather"]
    assert response.tools_call_ids == ["call-weather"]
    assert response.id == "msg-tools"
    assert response.usage is not None
    assert response.usage.input_other == 7
    assert response.usage.output == 3
