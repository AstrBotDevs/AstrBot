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
from astrbot.core.agent.message import ImageRefPart, ImageURLPart, Message, TextPart
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.image_context import ImageTurnContext
from astrbot.core.image_request_budget import ImageRequestBudget, charge_image_attempt
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.provider import Provider


@pytest.fixture
def managed(tmp_path):
    preview = tmp_path / "preview.png"
    Image.new("RGB", (16, 8), "red").save(preview)
    ref = ImageRefPart(occurrence_id="occ-current", asset_id="asset-private")
    state = ImageTurnContext(MagicMock(), "conversation", "checkpoint")
    state.pending_visuals = {"occ-current": str(preview)}
    state.references["occ-current"] = SimpleNamespace(asset_id="asset-private")
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
    provider.image_request_budget_supported = True
    provider.get_model.return_value = "primary-model"
    provider.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="seen")
    )
    state.configure(
        user_id="user",
        platform_id="platform",
        event=MagicMock(),
        max_size=1280,
        provider=provider,
        model="primary-model",
        budget=ImageRequestBudget(),
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
async def test_reset_projects_current_reference_once_without_mutating_history(managed):
    request, provider, state = managed
    history_preview = Path(state.pending_visuals["occ-current"]).with_name(
        "history.png"
    )
    Image.new("RGB", (8, 8), "green").save(history_preview)
    history_occurrence = "occ-history"
    history_reference = ImageRefPart(
        occurrence_id=history_occurrence, asset_id="asset-history"
    )
    state.references[history_occurrence] = SimpleNamespace(asset_id="asset-history")
    state.preview_cache[history_occurrence] = str(history_preview)
    request.contexts = [
        Message(
            role="user",
            content=[TextPart(text="Earlier"), history_reference],
        ).model_dump()
    ]
    runner = await make_runner(request, provider)
    current_preview = state.pending_visuals["occ-current"]
    before = [m.model_dump() for m in runner.run_context.messages]
    for _ in range(2):
        async for _ in runner._iter_llm_responses_with_fallback():
            pass
    payloads = [c.kwargs for c in provider.text_chat.call_args_list]
    first, second = [p["contexts"] for p in payloads]
    for contexts in (first, second):
        image_parts = [
            part
            for message in contexts
            if isinstance(message.get("content"), list)
            for part in message["content"]
            if part.get("type") == "image_url"
        ]
        assert [part["image_url"]["id"] for part in image_parts] == [
            history_occurrence,
            "occ-current",
        ]
        assert [part["image_url"]["url"] for part in image_parts] == [
            str(history_preview),
            current_preview,
        ]
    first, second = json.dumps(first), json.dumps(second)
    assert first.count(current_preview) == second.count(current_preview) == 1
    assert first.count('"type": "image_url"') == 2
    assert second.count('"type": "image_url"') == 2
    assert "data:image" not in first + second
    assert "asset-private" not in first + second
    assert "occ-current" in first + second
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
    preview = state.pending_visuals["occ-current"]
    if isinstance(failure, Exception):
        primary.text_chat.side_effect = failure
    else:
        primary.text_chat.return_value = failure
    fallback = MagicMock(spec=Provider)
    fallback.provider_config = {"id": "fallback"}
    fallback.image_request_budget_supported = True
    fallback.get_model.return_value = "fallback-model"
    fallback.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="seen")
    )
    runner = await make_runner(request, primary, fallback_providers=[fallback])
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    for provider in (primary, fallback):
        payload = json.dumps(provider.text_chat.call_args.kwargs["contexts"])
        assert preview in payload
        assert '"type": "image_url"' in payload
    assert not state.pending_visuals


@pytest.mark.asyncio
async def test_empty_response_retries_keep_pending(managed):
    request, provider, state = managed
    preview = state.pending_visuals["occ-current"]
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
        str(preview) in json.dumps(c.kwargs["contexts"])
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
    assert '"type": "image_url"' not in payload
    assert "cannot view images" in payload


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
async def test_tool_picture_becomes_gallery_reference_for_following_steps(
    managed, tmp_path, monkeypatch
):
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
        state.references["occ-tool"] = SimpleNamespace(asset_id="asset-tool")
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
    assert [p.count('"type": "image_url"') for p in payloads] == [1, 2, 2]
    assert "data:image" not in "".join(payloads)
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
    preview = state.pending_visuals["occ-current"]
    primary.provider_config["modalities"] = ["text"]
    primary.text_chat.side_effect = RuntimeError("offline")
    fallback = MagicMock(spec=Provider)
    fallback.provider_config = {"id": "visual", "modalities": ["text", "image"]}
    fallback.image_request_budget_supported = True
    fallback.get_model.return_value = "fallback-model"
    fallback.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="seen")
    )
    runner = await make_runner(request, primary, fallback_providers=[fallback])
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    payload = json.dumps(fallback.text_chat.call_args.kwargs["contexts"])
    assert preview in payload and '"type": "image_url"' in payload
    assert "cannot view images" not in payload
    assert not state.pending_visuals


@pytest.mark.asyncio
async def test_managed_small_images_have_no_default_count_limit(managed):
    from astrbot.core.image_request_budget import (
        ImageRequestBudget,
        charge_image_attempt,
    )

    request, provider, state = managed
    preview = next(iter(state.pending_visuals.values()))
    state.budget = ImageRequestBudget()
    request.prompt = "Inspect these images"
    request.extra_user_content_parts = []
    request.contexts = []
    state.references.clear()
    state.pending_visuals = {str(i): preview for i in range(9)}
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
    state.budget = ImageRequestBudget(max_image_submissions=1)
    request.extra_user_content_parts = []
    request.contexts = []
    state.references.clear()
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
    assert '"type": "image_url"' not in str(calls[-1])
    assert state.budget.to_dict()["groups"][0]["attempts"] == 2


@pytest.mark.asyncio
async def test_managed_unknown_adapter_cannot_send_images(managed):
    request, provider, state = managed
    provider.image_request_budget_supported = False
    provider.get_model.return_value = "custom"
    runner = await make_runner(request, provider)
    [resp async for resp in runner._iter_llm_responses_with_fallback()]
    payload = provider.text_chat.call_args.kwargs
    assert '"type": "image_url"' not in str(payload)
    assert "cannot verify image access for each request attempt" in str(payload)
    assert state.budget.image_submissions == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("modalities", [None, []])
async def test_unconfigured_modalities_preserve_managed_visual_context(
    managed, modalities
):
    request, provider, state = managed
    provider.provider_config["modalities"] = modalities
    runner = await make_runner(request, provider)
    responses = [resp async for resp in runner._iter_llm_responses_with_fallback()]

    payload = provider.text_chat.call_args.kwargs
    user_messages = [
        message for message in payload["contexts"] if message["role"] == "user"
    ]
    image_parts = [
        part
        for message in user_messages
        if isinstance(message.get("content"), list)
        for part in message["content"]
        if part.get("type") == "image_url"
    ]
    assert responses[-1].completion_text == "seen"
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"] == state.preview_cache["occ-current"]
    assert payload["extra_user_content_parts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("colliding_inline", [False, True])
async def test_configured_current_reference_is_projected_once(
    tmp_path, colliding_inline
):
    preview = tmp_path / "preview.png"
    Image.new("RGB", (16, 8), "blue").save(preview)
    occurrence_id = "current-occurrence"
    reference = ImageRefPart(occurrence_id=occurrence_id, asset_id="asset")
    state = ImageTurnContext(MagicMock(), "conversation", "checkpoint")
    provider = MagicMock(spec=Provider)
    provider.provider_config = {
        "id": "vision",
        "modalities": ["text", "image", "tool_use"],
    }
    provider.image_request_budget_supported = True
    provider.get_model.return_value = "vision-model"
    state.references[occurrence_id] = SimpleNamespace(asset_id="asset")
    state.pending_visuals[occurrence_id] = str(preview)
    state.configure(
        user_id="user",
        platform_id="platform",
        event=MagicMock(),
        max_size=1280,
        provider=provider,
        model="vision-model",
        budget=ImageRequestBudget(),
    )
    request = ProviderRequest(
        prompt="Look at the picture",
        extra_user_content_parts=[reference],
        image_context=state,
    )
    calls = []

    async def respond(**payload):
        calls.append(payload)
        charge_image_attempt(payload)
        return LLMResponse(role="assistant", completion_text="I see it.")

    provider.text_chat = AsyncMock(side_effect=respond)
    runner = await make_runner(request, provider)
    if colliding_inline:
        runner.run_context.messages[-1].content.append(
            ImageURLPart(
                image_url=ImageURLPart.ImageURL(
                    id=occurrence_id, url="data:image/png;base64,UNAUTHORIZED"
                )
            )
        )
    [resp async for resp in runner._iter_llm_responses_with_fallback()]

    user_contents = [
        message["content"]
        for message in calls[0]["contexts"]
        if message.get("role") == "user"
    ]
    image_parts = [
        part
        for content in user_contents
        if isinstance(content, list)
        for part in content
        if part.get("type") == "image_url"
    ]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"] == str(preview)
    assert image_parts[0]["image_url"]["id"] == occurrence_id
    assert calls[0]["extra_user_content_parts"] == []
    assert state.budget.image_submissions == 1
    assert not state.pending_visuals


@pytest.mark.asyncio
async def test_configured_history_reference_keeps_position_and_revocation_blocks(
    tmp_path,
):
    preview = tmp_path / "history.png"
    Image.new("RGB", (16, 8), "green").save(preview)
    occurrence_id = "history-occurrence"
    reference = ImageRefPart(occurrence_id=occurrence_id, asset_id="asset")
    state = ImageTurnContext(MagicMock(), "conversation", "checkpoint")
    provider = MagicMock(spec=Provider)
    provider.provider_config = {
        "id": "vision",
        "modalities": ["text", "image", "tool_use"],
    }
    provider.image_request_budget_supported = True
    provider.get_model.return_value = "vision-model"
    state.references[occurrence_id] = SimpleNamespace(asset_id="asset")
    state.preview_cache[occurrence_id] = str(preview)
    state.configure(
        user_id="user",
        platform_id="platform",
        event=MagicMock(),
        max_size=1280,
        provider=provider,
        model="vision-model",
        budget=ImageRequestBudget(),
    )
    request = ProviderRequest(
        prompt="Continue",
        contexts=[
            Message(
                role="user",
                content=[TextPart(text="before"), reference, TextPart(text="after")],
            ).model_dump()
        ],
        image_context=state,
    )
    calls = []

    async def respond(**payload):
        calls.append(payload)
        charge_image_attempt(payload)
        return LLMResponse(role="assistant", completion_text="I remember it.")

    provider.text_chat = AsyncMock(side_effect=respond)
    runner = await make_runner(request, provider)
    [resp async for resp in runner._iter_llm_responses_with_fallback()]

    history_user = calls[0]["contexts"][0]["content"]
    assert [part["type"] for part in history_user] == [
        "text",
        "text",
        "image_url",
        "text",
    ]
    assert history_user[1]["text"] == "[Image reference: history-occurrence]"
    assert history_user[2]["image_url"]["url"] == str(preview)
    assert state.budget.image_submissions == 1

    state.revoked_occurrences.add(occurrence_id)
    provider.text_chat.reset_mock()
    [resp async for resp in runner._iter_llm_responses_with_fallback()]
    revoked_payload = provider.text_chat.call_args.kwargs
    assert "image_url" not in json.dumps(revoked_payload["contexts"])
    assert "unavailable in this conversation" in json.dumps(revoked_payload["contexts"])
