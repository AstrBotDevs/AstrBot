"""Final-request pairing checks with an entirely in-memory SDK substitute."""

import copy
import json
from types import SimpleNamespace

import pytest
from openai import AsyncAzureOpenAI, AsyncOpenAI
from openai import _base_client as openai_base_client
from openai._models import FinalRequestOptions
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from astrbot.core.agent.context.compressor import LLMSummaryCompressor
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.sources.groq_source import ProviderGroq
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


def _calls(*ids):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": cid,
                "type": "function",
                "function": {"name": "f", "arguments": "{}"},
            }
            for cid in ids
        ],
    }


def _result(cid):
    return {"role": "tool", "tool_call_id": cid, "content": "synthetic result"}


def _provider(extra_body=None, provider_cls=ProviderOpenAIOfficial):
    requests = []

    async def create(**kwargs):
        requests.append(copy.deepcopy(kwargs))
        if kwargs["stream"]:

            async def chunks():
                yield ChatCompletionChunk.model_validate(
                    {
                        "id": "synthetic",
                        "created": 0,
                        "model": "synthetic",
                        "object": "chat.completion.chunk",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": "ok"},
                                "finish_reason": "stop",
                            }
                        ],
                    }
                )

            return chunks()
        return ChatCompletion.model_validate(
            {
                "id": "synthetic",
                "created": 0,
                "model": "synthetic",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            }
        )

    provider = provider_cls.__new__(provider_cls)
    provider.provider_config = {
        "id": "synthetic",
        "type": "openai_chat_completion",
        "custom_extra_body": copy.deepcopy(extra_body or {}),
    }
    provider.api_keys = ["synthetic-key-a", "synthetic-key-b"]
    provider.default_params = {"messages", "model", "tools", "tool_choice"}
    provider.reasoning_key = "reasoning_content"
    provider.set_model("synthetic")
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        base_url=SimpleNamespace(host="synthetic.invalid"),
        api_key=None,
    )
    return provider, requests


async def _query(provider, messages, streaming):
    payload = {"messages": copy.deepcopy(messages), "model": "synthetic"}
    if streaming:
        return [response async for response in provider._query_stream(payload, None)]
    return [await provider._query(payload, None)]


INVALID_FINAL_MESSAGES = [
    pytest.param([_calls("a")], id="missing-result"),
    pytest.param([_calls("a", "b"), _result("a")], id="partial-parallel-results"),
    pytest.param([_calls("a"), _result("b")], id="wrong-id"),
    pytest.param([_result("a")], id="orphan-result"),
    pytest.param([_calls("a"), _result("a"), _result("a")], id="duplicate-result"),
    pytest.param([_calls("a", "a"), _result("a")], id="duplicate-declared-id"),
    pytest.param([_calls(None), _result("a")], id="missing-declared-id"),
    pytest.param([_calls("a", None), _result("a")], id="mixed-missing-id"),
    pytest.param([_calls(" "), _result(" ")], id="blank-id"),
    pytest.param([_calls(["a"]), _result("a")], id="unhashable-declared-id"),
    pytest.param([_calls("a"), _result(["a"])], id="unhashable-result-id"),
    pytest.param([_calls("a"), {"role": "user", "content": "next"}], id="interrupted"),
    pytest.param([{"role": "assistant", "tool_calls": "invalid"}], id="invalid-calls"),
    pytest.param([{"role": "user", "tool_calls": []}], id="calls-on-user"),
    pytest.param(
        [{"role": "assistant", "content": "x", "tool_call_id": "a"}],
        id="id-on-assistant",
    ),
    pytest.param([None], id="invalid-message"),
    pytest.param(None, id="null-override"),
    pytest.param({}, id="object-override"),
]


@pytest.mark.parametrize("messages", INVALID_FINAL_MESSAGES)
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_final_extra_body_messages_rejected_before_sdk(messages, streaming):
    provider, requests = _provider({"messages": messages})
    with pytest.raises(ValueError, match="tool_message_protocol") as caught:
        await _query(provider, [{"role": "user", "content": "valid base"}], streaming)
    assert type(caught.value).__name__ == "ToolMessageProtocolError"
    assert requests == []


@pytest.mark.parametrize(
    "messages",
    [
        [_calls("a")],
        [_calls("a", "b"), _result("a")],
        [_calls("a"), _result("b")],
        [_calls("a", "a"), _result("a")],
        [_calls(None), _result("a")],
        [_calls(["a"]), _result("a")],
        [_calls("a"), _result(["a"])],
        [{"role": "assistant", "tool_calls": "invalid"}],
    ],
)
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_unrepaired_payload_rejected_before_sdk(messages, streaming):
    provider, requests = _provider()
    with pytest.raises(ValueError, match="tool_message_protocol"):
        await _query(provider, messages, streaming)
    assert requests == []


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "user", "content": "hello"}],
        [_calls("a"), _result("a")],
        [_calls("a", "b"), _result("b"), _result("a")],
        [_calls("a"), _result("a"), _calls("a"), _result("a")],
        [
            {
                "role": "assistant",
                "content": "legacy",
                "function_call": {"name": "f", "arguments": "{}"},
            },
            {"role": "function", "name": "f", "content": "legacy result"},
        ],
    ],
    ids=[
        "plain",
        "single",
        "parallel-reversed",
        "reused-id-next-group",
        "legacy-function",
    ],
)
@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_valid_messages_reach_sdk_unchanged(messages, override, streaming):
    original = copy.deepcopy(messages)
    provider, requests = _provider({"messages": messages} if override else {})
    base = [{"role": "user", "content": "base"}] if override else messages
    responses = await _query(provider, base, streaming)
    assert len(requests) == 1
    effective = requests[0]["extra_body"].get("messages", requests[0]["messages"])
    assert effective == original
    assert messages == original
    assert responses[-1].completion_text == "ok"


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_existing_orphan_and_duplicate_cleanup_is_preserved(streaming):
    provider, requests = _provider()
    await _query(
        provider,
        [_result("old"), _calls("a"), _result("a"), _result("a")],
        streaming,
    )
    assert requests[0]["messages"] == [_calls("a"), _result("a")]


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_valid_override_replaces_invalid_base(streaming):
    valid = [_calls("a"), _result("a")]
    provider, requests = _provider({"messages": valid})
    await _query(provider, [_calls("missing")], streaming)
    assert requests[0]["extra_body"]["messages"] == valid


@pytest.mark.parametrize("diagnostic", ["index=429", "pending_count=429"])
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_public_chat_local_error_index_429_does_not_rotate_keys(
    monkeypatch, streaming, diagnostic
):
    provider, requests = _provider()
    messages = [{"role": "user", "content": "synthetic"}] * 428 + [_calls("a")]
    if diagnostic == "pending_count=429":
        messages = [_calls(*(str(index) for index in range(429)))]
    recoveries = []
    original_handler = provider._handle_api_error

    async def capture_recovery(*args, **kwargs):
        recoveries.append(args[5])
        return await original_handler(*args, **kwargs)

    async def unexpected_sleep(*args, **kwargs):
        pytest.fail("A local validation failure must not sleep or rotate keys")

    monkeypatch.setattr(provider, "_handle_api_error", capture_recovery)
    monkeypatch.setattr(
        "astrbot.core.provider.sources.openai_source.asyncio.sleep", unexpected_sleep
    )
    with pytest.raises(ValueError, match=diagnostic) as caught:
        if streaming:
            _ = [
                response
                async for response in provider.text_chat_stream(contexts=messages)
            ]
        else:
            await provider.text_chat(contexts=messages)
    assert type(caught.value).__name__ == "ToolMessageProtocolError"
    assert len(recoveries) == 1
    assert recoveries[0] == ["synthetic-key-a", "synthetic-key-b"]
    assert requests == []


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_runner_local_pairing_error_stops_before_fallback(streaming):
    primary, primary_requests = _provider({"messages": [_calls("a")]})
    fallback, fallback_requests = _provider()
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=primary,
        request=ProviderRequest(contexts=[{"role": "user", "content": "synthetic"}]),
        run_context=ContextWrapper(context=None),
        tool_executor=SimpleNamespace(),
        agent_hooks=BaseAgentRunHooks(),
        streaming=streaming,
        fallback_providers=[fallback],
    )
    responses = [
        response async for response in runner._iter_llm_responses_with_fallback()
    ]
    assert responses[-1].role == "err"
    assert runner.provider is primary
    assert primary_requests == []
    assert fallback_requests == []


@pytest.mark.parametrize("messages", [None, [], [_calls("a")]])
@pytest.mark.parametrize("azure", [False, True])
@pytest.mark.asyncio
async def test_sdk_build_request_confirms_messages_override_without_io(messages, azure):
    sdk_httpx = getattr(openai_base_client, "httpx2", None) or openai_base_client.httpx

    def unexpected_transport(request):
        pytest.fail("Building a request must not send it")

    http_client = sdk_httpx.AsyncClient(
        transport=sdk_httpx.MockTransport(unexpected_transport)
    )
    kwargs = {"api_key": "synthetic", "http_client": http_client, "max_retries": 0}
    if azure:
        client = AsyncAzureOpenAI(
            **kwargs,
            api_version="2024-02-01",
            azure_endpoint="https://synthetic.invalid",
        )
    else:
        client = AsyncOpenAI(**kwargs, base_url="https://synthetic.invalid/v1")
    try:
        request = client._build_request(
            FinalRequestOptions.construct(
                method="post",
                url="/chat/completions",
                json_data={
                    "model": "synthetic",
                    "messages": [{"role": "user", "content": "base"}],
                },
                extra_json={"messages": copy.deepcopy(messages)},
            )
        )
        assert json.loads(request.content)["messages"] == messages
    finally:
        await client.close()


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_empty_override_is_allowed_by_pairing_only_validator(streaming):
    provider, requests = _provider({"messages": []})
    await _query(provider, [_calls("missing")], streaming)
    assert requests[0]["extra_body"]["messages"] == []


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("override", [False, True])
@pytest.mark.asyncio
async def test_final_guard_preserves_multimodal_reasoning_and_metadata(
    streaming, override
):
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "synthetic"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,c3ludGhldGlj"},
                },
            ],
        },
        {
            **_calls("a"),
            "reasoning_content": "synthetic reasoning",
            "name": "assistant",
        },
        {**_result("a"), "name": "f"},
    ]
    original = copy.deepcopy(messages)
    provider, requests = _provider({"messages": messages} if override else {})
    await _query(provider, messages, streaming)
    effective = requests[0]["extra_body"].get("messages", requests[0]["messages"])
    assert effective == original
    assert messages == original


@pytest.mark.parametrize("provider_cls", [ProviderOpenAIOfficial, ProviderGroq])
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_public_provider_paths_block_missing_results(provider_cls, streaming):
    provider, requests = _provider(provider_cls=provider_cls)
    messages = [_calls("a", "b"), _result("a")]
    with pytest.raises(ValueError, match="missing_tool_response"):
        if streaming:
            _ = [
                response
                async for response in provider.text_chat_stream(contexts=messages)
            ]
        else:
            await provider.text_chat(contexts=messages)
    assert requests == []


@pytest.mark.asyncio
async def test_summary_provider_is_guarded_before_context_manager_exit(monkeypatch):
    provider, requests = _provider()
    messages = [
        Message(role="user", content="synthetic old round"),
        Message(**_calls("a", "b")),
        Message(**_result("a")),
        Message(role="user", content="synthetic latest round"),
    ]
    attempts = []
    original_text_chat = provider.text_chat

    async def capture_summary_request(**kwargs):
        attempts.append(kwargs)
        return await original_text_chat(**kwargs)

    monkeypatch.setattr(provider, "text_chat", capture_summary_request)
    result = await LLMSummaryCompressor(provider, keep_recent_ratio=0)(messages)
    assert len(attempts) == 1
    assert requests == []
    assert result == messages
