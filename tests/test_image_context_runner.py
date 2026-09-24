"""Verify durable image references and request-only visual payloads."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from astrbot.core.agent.context.compressor import LLMSummaryCompressor
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.message import ImageRefPart, ImageURLPart, Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.image_context import ImageTurnContext
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.provider import Provider


@pytest.fixture
def managed(tmp_path):
    preview = tmp_path / "preview.png"
    Image.new("RGB", (16, 8), "red").save(preview)
    ref = ImageRefPart(occurrence_id="occ-current", asset_id="asset-private")
    state = ImageTurnContext(MagicMock(), "conversation", "checkpoint")
    state.pending_visuals = {"occ-current": str(preview)}
    request = ProviderRequest(
        prompt="Look at this",
        system_prompt="You are a cheerful cat.",
        extra_user_content_parts=[ref],
        image_context=state,
    )
    provider = MagicMock(spec=Provider)
    provider.provider_config = {
        "id": "primary",
        "modalities": ["text", "image", "tool_use"],
    }
    provider.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="seen")
    )
    return request, provider, state


async def make_runner(request, provider, **kwargs):
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=MagicMock(),
        agent_hooks=BaseAgentRunHooks(),
        **kwargs,
    )
    return runner


@pytest.mark.asyncio
async def test_current_image_once_and_history_stays_reference(managed):
    request, provider, state = managed
    request.contexts = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,OLD"}}
            ],
        }
    ]
    runner = await make_runner(request, provider)
    before = [m.model_dump() for m in runner.run_context.messages]
    for _ in range(2):
        async for _ in runner._iter_llm_responses_with_fallback():
            pass
    payloads = [c.kwargs for c in provider.text_chat.call_args_list]
    first, second = [json.dumps(p["contexts"]) for p in payloads]
    assert first.count("data:image/png;base64,") == 1
    assert "OLD" not in first and "asset-private" not in first
    assert "image_ref" not in first and "occ-current" in first
    assert "data:image" not in second
    assert all(p["extra_user_content_parts"] == [] for p in payloads)
    assert before == [m.model_dump() for m in runner.run_context.messages]
    assert not state.pending_visuals


@pytest.mark.asyncio
async def test_revoked_new_capture_is_not_submitted(managed):
    request, provider, state = managed
    state.revoked_occurrences = {"occ-current"}
    runner = await make_runner(request, provider)
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    payload = json.dumps(provider.text_chat.call_args.kwargs["contexts"])
    assert "data:image" not in payload
    assert "no longer available" in payload
    assert not state.pending_visuals


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [RuntimeError("offline"), LLMResponse(role="err", completion_text="offline")],
)
async def test_failed_primary_keeps_image_for_fallback(managed, failure):
    request, primary, state = managed
    if isinstance(failure, Exception):
        primary.text_chat.side_effect = failure
    else:
        primary.text_chat.return_value = failure
    fallback = MagicMock(spec=Provider)
    fallback.provider_config = {"id": "fallback"}
    fallback.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="seen")
    )
    runner = await make_runner(request, primary, fallback_providers=[fallback])
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    for provider in (primary, fallback):
        assert "data:image/png;base64," in json.dumps(
            provider.text_chat.call_args.kwargs["contexts"]
        )
    assert not state.pending_visuals


@pytest.mark.asyncio
async def test_empty_response_retries_keep_pending(managed):
    request, provider, state = managed
    provider.text_chat.side_effect = [
        EmptyModelOutputError("empty"),
        LLMResponse(role="assistant", completion_text="ok"),
    ]
    runner = await make_runner(request, provider)
    runner.EMPTY_OUTPUT_RETRY_WAIT_MIN_S = runner.EMPTY_OUTPUT_RETRY_WAIT_MAX_S = 0
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    assert len(provider.text_chat.call_args_list) == 2
    assert all(
        "data:image" in json.dumps(c.kwargs["contexts"])
        for c in provider.text_chat.call_args_list
    )
    assert not state.pending_visuals


@pytest.mark.asyncio
async def test_error_preserves_pending_and_notice(managed):
    request, provider, state = managed
    state.notices.append(
        "This image could not be saved and is available only in this turn."
    )
    provider.text_chat.return_value = LLMResponse(role="err", completion_text="offline")
    runner = await make_runner(request, provider)
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    assert state.pending_visuals and state.notices


@pytest.mark.asyncio
async def test_persona_notice_survives_tool_response_without_extra_call(managed):
    request, provider, state = managed
    state.notices.append(
        "This image could not be saved, but remains available this turn."
    )
    provider.text_chat.side_effect = [
        LLMResponse(
            role="assistant",
            tools_call_name=["lookup"],
            tools_call_ids=["call-1"],
            tools_call_args=[{}],
        ),
        LLMResponse(
            role="assistant", completion_text="Meow, this image could not be saved!"
        ),
    ]
    runner = await make_runner(request, provider)
    before = copy.deepcopy(runner.run_context.messages)
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    assert state.notices and not state.pending_visuals
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    assert not state.notices
    assert provider.text_chat.call_count == 2
    for call in provider.text_chat.call_args_list:
        payload = json.dumps(call.kwargs["contexts"])
        assert "cheerful cat" in payload and "could not be saved" in payload
        assert "established persona" in payload and "not a fixed" in payload
    assert runner.run_context.messages == before


@pytest.mark.asyncio
async def test_nonvisual_model_gets_truthful_notice_not_bytes(managed):
    request, provider, state = managed
    provider.provider_config["modalities"] = ["text"]
    runner = await make_runner(request, provider)
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    payload = json.dumps(provider.text_chat.call_args.kwargs["contexts"])
    assert "data:image" not in payload and "cannot inspect" in payload


@pytest.mark.asyncio
async def test_summary_omits_old_inline_bytes_without_mutating_history(managed):
    _, provider, _ = managed
    image = ImageURLPart(
        image_url=ImageURLPart.ImageURL(url="data:image/png;base64,OLD")
    )
    messages = [
        Message(role="user", content=[image]),
        Message(role="assistant", content="old answer"),
        Message(role="user", content="now"),
    ]
    before = [m.model_dump() for m in messages]
    compressor = LLMSummaryCompressor(provider, keep_recent_ratio=0, strip_images=True)
    await compressor(messages)
    assert provider.text_chat.call_count == 1
    assert "data:image" not in json.dumps(
        provider.text_chat.call_args.kwargs["contexts"]
    )
    assert before == [m.model_dump() for m in messages]


@pytest.mark.asyncio
async def test_tool_picture_visible_on_next_step_only(managed, tmp_path, monkeypatch):
    import base64

    from mcp.types import CallToolResult, ImageContent, TextContent

    from astrbot.core.agent.tool import FunctionTool, ToolSet
    from astrbot.core.agent.tool_image_cache import tool_image_cache

    request, provider, state = managed
    preview = next(iter(state.pending_visuals.values()))
    raw = base64.b64encode(Path(preview).read_bytes()).decode()
    tool = FunctionTool(
        name="draw",
        description="Draw",
        parameters={"type": "object", "properties": {}},
        handler=AsyncMock(),
    )
    request.func_tool = ToolSet(tools=[tool])
    provider.text_chat.side_effect = [
        LLMResponse(
            role="assistant",
            tools_call_name=["draw"],
            tools_call_args=[{}],
            tools_call_ids=["c1"],
        ),
        LLMResponse(
            role="assistant",
            tools_call_name=["draw"],
            tools_call_args=[{}],
            tools_call_ids=["c2"],
        ),
        LLMResponse(role="assistant", completion_text="done"),
    ]
    calls = 0

    async def execute(**kwargs):
        nonlocal calls
        calls += 1
        yield CallToolResult(
            content=[ImageContent(type="image", data=raw, mimeType="image/png")]
            if calls == 1
            else [TextContent(type="text", text="ok")]
        )

    async def capture(path, **kwargs):
        assert kwargs["source_message_id"] == "c1"
        state.pending_visuals["occ-tool"] = path
        return ImageRefPart(occurrence_id="occ-tool", asset_id="asset-tool")

    state.capture = AsyncMock(side_effect=capture)
    monkeypatch.setattr(tool_image_cache, "_cache_dir", str(tmp_path / "cache"))
    runner = await make_runner(request, provider)
    runner.tool_executor = SimpleNamespace(execute=execute)
    config = MagicMock()
    config.get_config.return_value = {
        "provider_settings": {"image_compress_options": {"max_size": 1280}}
    }
    runner.run_context.context = SimpleNamespace(
        context=config, event=SimpleNamespace(unified_msg_origin="test")
    )
    for _ in range(3):
        async for _ in runner.step():
            pass
    payloads = [
        json.dumps(c.kwargs["contexts"]) for c in provider.text_chat.call_args_list
    ]
    assert [p.count("data:image/png;base64,") for p in payloads] == [1, 1, 0]
    assert state.capture.call_count == 1
    history = json.dumps([m.model_dump() for m in runner.run_context.messages])
    assert "image_url" not in history and "occ-tool" in history


@pytest.mark.asyncio
async def test_stream_chunks_do_not_consume_before_final(managed):
    request, provider, state = managed
    seen_pending = []

    async def stream(**kwargs):
        yield LLMResponse(role="assistant", completion_text="partial", is_chunk=True)
        seen_pending.append(bool(state.pending_visuals))
        yield LLMResponse(role="assistant", completion_text="complete")

    provider.text_chat_stream = stream
    runner = await make_runner(request, provider, streaming=True)
    results = [
        response async for response in runner._iter_llm_responses_with_fallback()
    ]
    assert len(results) == 2 and seen_pending == [True]
    assert not state.pending_visuals


@pytest.mark.asyncio
async def test_interrupted_stream_retains_pending(managed):
    request, provider, state = managed

    async def stream(**kwargs):
        yield LLMResponse(role="assistant", completion_text="partial", is_chunk=True)

    provider.text_chat_stream = stream
    runner = await make_runner(request, provider, streaming=True)
    results = [
        response async for response in runner._iter_llm_responses_with_fallback()
    ]
    assert len(results) == 1 and state.pending_visuals


@pytest.mark.asyncio
async def test_failed_nonvisual_candidate_notice_does_not_taint_visual_fallback(
    managed,
):
    request, primary, state = managed
    primary.provider_config["modalities"] = ["text"]
    primary.text_chat.side_effect = RuntimeError("offline")
    fallback = MagicMock(spec=Provider)
    fallback.provider_config = {"id": "visual", "modalities": ["text", "image"]}
    fallback.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="seen")
    )
    runner = await make_runner(request, primary, fallback_providers=[fallback])
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    payload = json.dumps(fallback.text_chat.call_args.kwargs["contexts"])
    assert "data:image" in payload and "cannot inspect" not in payload
    assert not state.pending_visuals


@pytest.mark.asyncio
async def test_managed_small_images_have_no_default_count_limit(managed):
    from astrbot.core.image_request_budget import (
        ImageRequestBudget,
        charge_image_attempt,
    )

    request, provider, state = managed
    preview = next(iter(state.pending_visuals.values()))
    state.configured = True
    state.budget = ImageRequestBudget()
    state.retrieval_visuals = set()
    state.pending_visuals = {str(i): preview for i in range(9)}
    state.prepare_step = AsyncMock()
    state.project_messages = AsyncMock(side_effect=lambda messages: messages)
    provider.image_request_budget_supported = True
    provider.get_model.return_value = "test-model"
    calls = []

    async def respond(**payload):
        charge_image_attempt(payload)
        calls.append(payload)
        return LLMResponse(role="assistant", completion_text="done")

    provider.text_chat.side_effect = respond
    runner = await make_runner(request, provider)
    responses = [resp async for resp in runner._iter_llm_responses_with_fallback()]
    assert responses[-1].completion_text == "done"
    assert state.budget.image_submissions == 9
    assert len(calls) == 1
    assert not state.pending_visuals
    assert state.budget.to_dict()["groups"][0]["unknown_calls"] == 1


@pytest.mark.asyncio
async def test_managed_retry_exhaustion_allows_one_text_pass(managed):
    from astrbot.core.image_request_budget import (
        ImageRequestBudget,
        charge_image_attempt,
    )

    request, provider, state = managed
    state.configured = True
    state.budget = ImageRequestBudget(max_image_submissions=1)
    state.retrieval_visuals = set()
    state.prepare_step = AsyncMock()
    state.project_messages = AsyncMock(side_effect=lambda messages: messages)
    provider.image_request_budget_supported = True
    provider.get_model.return_value = "test-model"
    calls = []

    async def respond(**payload):
        charge_image_attempt(payload)
        calls.append(payload)
        if len(calls) == 1:
            charge_image_attempt(
                payload
            )  # A real provider retry would be blocked here.
        return LLMResponse(role="assistant", completion_text="limited")

    provider.text_chat.side_effect = respond
    runner = await make_runner(request, provider)
    responses = [resp async for resp in runner._iter_llm_responses_with_fallback()]
    assert responses[-1].completion_text == "limited"
    assert state.budget.image_submissions == 1
    assert len(calls) == 2
    assert "data:image" not in str(calls[-1])
    assert state.budget.to_dict()["groups"][0]["attempts"] == 2


@pytest.mark.asyncio
async def test_managed_unknown_adapter_cannot_send_images(managed):
    from astrbot.core.image_request_budget import ImageRequestBudget

    request, provider, state = managed
    state.configured = True
    state.budget = ImageRequestBudget()
    state.retrieval_visuals = set()
    state.prepare_step = AsyncMock()
    state.project_messages = AsyncMock(side_effect=lambda messages: messages)
    provider.image_request_budget_supported = False
    provider.get_model.return_value = "custom"
    runner = await make_runner(request, provider)
    [resp async for resp in runner._iter_llm_responses_with_fallback()]
    payload = provider.text_chat.call_args.kwargs
    assert "data:image" not in str(payload)
    assert "cannot verify image authorization" in str(payload)
    assert state.budget.image_submissions == 0
