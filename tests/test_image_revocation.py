"""Exercise image revocation using real SQLite and deterministic async barriers."""

import asyncio
import gc
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.exc import SQLAlchemyError

from astrbot.core import image_asset_store as storage
from astrbot.core import image_context as images
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.image_description import describe_images
from astrbot.core.image_request_budget import ImageRequestBudget, charge_image_attempt
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.provider import Provider


@pytest_asyncio.fixture(autouse=True)
async def reject_unhandled_async_errors():
    """Fail even when background generator cleanup escapes business assertions."""
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    errors = []
    loop.set_exception_handler(lambda loop, context: errors.append(context))
    try:
        yield
        gc.collect()
        # Drain callbacks scheduled by generator finalization without timed sleeps.
        for _ in range(3):
            drained = loop.create_future()
            loop.call_soon(drained.set_result, None)
            await drained
        assert not errors, repr(errors)
    finally:
        loop.set_exception_handler(previous)


@pytest_asyncio.fixture
async def revocation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage, "get_astrbot_data_path", lambda: str(tmp_path / "data")
    )
    monkeypatch.setattr(images, "get_astrbot_temp_path", lambda: str(tmp_path / "temp"))
    db = SQLiteDatabase(str(tmp_path / "test.db"))
    await db.initialize()
    db.inited = True
    source = tmp_path / "source.png"
    Image.new("RGB", (80, 40), "orange").save(source)
    provider = MagicMock(spec=Provider)
    provider.provider_config = {"id": "test", "modalities": ["image", "tool_use"]}
    provider.image_request_budget_supported = True
    provider.get_model.return_value = "vision"

    async def respond(**payload):
        charge_image_attempt(payload)
        return LLMResponse(role="assistant", completion_text="seen")

    provider.text_chat = AsyncMock(side_effect=respond)

    async def create_turn(cid="conversation", owner="owner", database=None):
        selected_db = database or db
        await selected_db.create_conversation(owner, "test", cid=cid)
        event = SimpleNamespace(
            unified_msg_origin=owner,
            track_temporary_local_file=lambda path: None,
        )
        turn = images.ImageTurnContext(selected_db, cid, "cp1")
        turn.configure(
            user_id=owner,
            platform_id="test",
            event=event,
            max_size=64,
            provider=provider,
            budget=ImageRequestBudget(),
            caption_explicit=True,
        )
        return turn

    yield SimpleNamespace(
        db=db, source=source, provider=provider, create_turn=create_turn, path=tmp_path
    )
    await db.engine.dispose()


async def capture(turn, source, *, temporary=False):
    return await turn.capture(
        str(source), max_size=64, event=turn.event, temporary=temporary
    )


async def run_visual(turn, provider, part, **kwargs):
    request = ProviderRequest(
        prompt="Inspect this image", extra_user_content_parts=[part], image_context=turn
    )
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=MagicMock(),
        agent_hooks=BaseAgentRunHooks(),
        **kwargs,
    )
    runner.EMPTY_OUTPUT_RETRY_WAIT_MIN_S = runner.EMPTY_OUTPUT_RETRY_WAIT_MAX_S = 0
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    return runner


async def persist(turn, part):
    history = [
        {"role": "user", "content": [part.model_dump()]},
        {"role": "assistant", "content": "seen"},
        {"role": "_checkpoint", "content": {"id": turn.checkpoint_id}},
    ]
    await turn.db.update_conversation(
        turn.conversation_id, content=history, image_refs=list(turn.references.values())
    )
    return history


@pytest.mark.asyncio
@pytest.mark.parametrize("temporary", [False, True])
async def test_unsaved_new_image_is_not_falsely_rejected(revocation, temporary):
    turn = await revocation.create_turn()
    part = await capture(turn, revocation.source, temporary=temporary)
    assert not await turn.db.get_conversation_images(
        turn.conversation_id,
        list(turn.pending_visuals),
        user_id="owner",
        platform_id="test",
    )
    await run_visual(turn, revocation.provider, part)
    assert "data:image" in str(revocation.provider.text_chat.call_args.kwargs)
    assert turn.budget.image_submissions == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("temporary", [False, True])
@pytest.mark.parametrize("when", ["before_capture", "during_capture", "after_capture"])
async def test_deleted_conversation_blocks_new_capture(
    revocation, monkeypatch, temporary, when
):
    turn = await revocation.create_turn()
    if when == "before_capture":
        await turn.db.delete_conversation(turn.conversation_id)
        part = await capture(turn, revocation.source, temporary=temporary)
    elif when == "during_capture":
        entered, release = asyncio.Event(), asyncio.Event()
        original = images.prepare_model_image

        async def blocked_preview(*args, **kwargs):
            entered.set()
            await release.wait()
            return await original(*args, **kwargs)

        monkeypatch.setattr(images, "prepare_model_image", blocked_preview)
        task = asyncio.create_task(
            capture(turn, revocation.source, temporary=temporary)
        )
        await asyncio.wait_for(entered.wait(), 5)
        try:
            await turn.db.delete_conversation(turn.conversation_id)
        finally:
            release.set()
        part = await asyncio.wait_for(task, 5)
    else:
        part = await capture(turn, revocation.source, temporary=temporary)
        await turn.db.delete_conversation(turn.conversation_id)
    await run_visual(turn, revocation.provider, part)
    assert "data:image" not in str(revocation.provider.text_chat.call_args.kwargs)
    assert turn.budget.image_submissions == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("all_owner", [False, True])
async def test_deletion_is_scoped_to_conversation_and_owner(revocation, all_owner):
    turns = [
        await revocation.create_turn("a"),
        await revocation.create_turn("b"),
        await revocation.create_turn("c", "other"),
    ]
    parts = [await capture(turn, revocation.source) for turn in turns]
    if all_owner:
        await revocation.db.delete_conversations_by_user_id("owner")
    else:
        await revocation.db.delete_conversation("a")
    for index, (turn, part) in enumerate(zip(turns, parts)):
        await run_visual(turn, revocation.provider, part)
        actual = "data:image" in str(revocation.provider.text_chat.call_args.kwargs)
        assert actual is (index == 2 or (index == 1 and not all_owner))


@pytest.mark.asyncio
async def test_identical_ids_in_different_databases_are_isolated(revocation):
    other_db = SQLiteDatabase(str(revocation.path / "other.db"))
    await other_db.initialize()
    other_db.inited = True
    try:
        deleted = await revocation.create_turn()
        surviving = await revocation.create_turn(database=other_db)
        deleted_part = await capture(deleted, revocation.source)
        surviving_part = await capture(surviving, revocation.source)
        await deleted.db.delete_conversation(deleted.conversation_id)
        await run_visual(deleted, revocation.provider, deleted_part)
        assert "data:image" not in str(revocation.provider.text_chat.call_args.kwargs)
        await run_visual(surviving, revocation.provider, surviving_part)
        assert "data:image" in str(revocation.provider.text_chat.call_args.kwargs)
    finally:
        await other_db.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("all_owner", [False, True])
async def test_failed_delete_rolls_back_without_revoking(revocation, all_owner):
    turn = await revocation.create_turn()
    part = await capture(turn, revocation.source)
    await persist(turn, part)

    def fail_delete(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("DELETE FROM CONVERSATIONS"):
            raise SQLAlchemyError("injected transaction failure")

    sqlalchemy_event.listen(
        revocation.db.engine.sync_engine, "before_cursor_execute", fail_delete
    )
    try:
        with pytest.raises(SQLAlchemyError, match="injected transaction failure"):
            if all_owner:
                await turn.db.delete_conversations_by_user_id("owner")
            else:
                await turn.db.delete_conversation(turn.conversation_id)
    finally:
        sqlalchemy_event.remove(
            revocation.db.engine.sync_engine, "before_cursor_execute", fail_delete
        )
    assert await turn.db.get_conversation_images(
        turn.conversation_id, [part.occurrence_id], user_id="owner", platform_id="test"
    )
    await run_visual(turn, revocation.provider, part)
    assert "data:image" in str(revocation.provider.text_chat.call_args.kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("cached_current", [False, True])
async def test_edit_removes_cached_image_authorization(revocation, cached_current):
    original = await revocation.create_turn()
    part = await capture(original, revocation.source)
    history = await persist(original, part)
    if cached_current:
        turn = original
    else:
        turn = images.ImageTurnContext(revocation.db, "conversation", "cp2")
        turn.configure(
            user_id="owner",
            platform_id="test",
            event=original.event,
            max_size=64,
            provider=revocation.provider,
            budget=ImageRequestBudget(),
            caption_explicit=True,
        )
        assert "queued" in await turn.read_existing(part.occurrence_id)
    await revocation.db.update_conversation(
        "conversation", content=[], expected_history=history, prune_image_refs=True
    )
    await run_visual(turn, revocation.provider, part)
    assert "data:image" not in str(revocation.provider.text_chat.call_args.kwargs)
    with pytest.raises(PermissionError):
        await turn.open_preview(part.occurrence_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_kind", ["empty", "fallback"])
async def test_delete_after_started_request_blocks_retry_and_next_step(
    revocation, retry_kind
):
    turn = await revocation.create_turn()
    part = await capture(turn, revocation.source)
    calls = []

    async def respond(**payload):
        charge_image_attempt(payload)
        calls.append(payload)
        if len(calls) == 1:
            await turn.db.delete_conversation(turn.conversation_id)
            if retry_kind == "empty":
                raise EmptyModelOutputError("empty")
            raise RuntimeError("primary unavailable")
        return LLMResponse(role="assistant", completion_text="done")

    revocation.provider.text_chat.side_effect = respond
    fallback = MagicMock(spec=Provider)
    fallback.provider_config = {"id": "fallback", "modalities": ["image", "tool_use"]}
    fallback.image_request_budget_supported = True
    fallback.get_model.return_value = "fallback-model"
    fallback.text_chat = AsyncMock(side_effect=respond)
    runner = await run_visual(
        turn,
        revocation.provider,
        part,
        fallback_providers=[fallback] if retry_kind == "fallback" else None,
    )
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    assert "data:image" in str(calls[0])
    assert len(calls) >= 3
    assert all("data:image" not in str(payload) for payload in calls[1:])
    assert turn.budget.image_submissions == 1


@pytest.mark.asyncio
async def test_delete_before_caption_prevents_provider_call(revocation):
    turn = await revocation.create_turn()
    part = await capture(turn, revocation.source)
    await turn.db.delete_conversation(turn.conversation_id)
    await describe_images(
        turn, revocation.provider, occurrence_ids=[part.occurrence_id]
    )
    revocation.provider.text_chat.assert_not_called()
    assert turn.budget.image_submissions == 0


@pytest.mark.asyncio
async def test_delete_during_caption_does_not_commit_description(revocation):
    turn = await revocation.create_turn()
    part = await capture(turn, revocation.source)
    reference = turn.references[part.occurrence_id]
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked_caption(**payload):
        charge_image_attempt(payload)
        entered.set()
        await release.wait()
        return LLMResponse(
            role="assistant",
            completion_text=json.dumps(
                {
                    "images": [
                        {
                            "image_id": part.occurrence_id,
                            "description": "must not commit",
                        }
                    ],
                    "answer": "must not return",
                }
            ),
        )

    revocation.provider.text_chat.side_effect = blocked_caption
    task = asyncio.create_task(
        describe_images(
            turn,
            revocation.provider,
            occurrence_ids=[part.occurrence_id],
            question="What?",
        )
    )
    await asyncio.wait_for(entered.wait(), 5)
    try:
        await turn.db.delete_conversation(turn.conversation_id)
    finally:
        release.set()
    assert await asyncio.wait_for(task, 5) is None
    assert reference.description_status == "pending"
    assert reference.description_version == 0
    assert "unavailable" in await turn.read_existing(part.occurrence_id)


@pytest.mark.asyncio
async def test_caption_cancellation_propagates_without_updating(revocation):
    turn = await revocation.create_turn()
    part = await capture(turn, revocation.source)
    reference = turn.references[part.occurrence_id]
    entered = asyncio.Event()

    async def cancelled_caption(**payload):
        charge_image_attempt(payload)
        entered.set()
        await asyncio.Event().wait()

    revocation.provider.text_chat.side_effect = cancelled_caption
    task = asyncio.create_task(
        describe_images(turn, revocation.provider, occurrence_ids=[part.occurrence_id])
    )
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert reference.description_status == "pending"
    assert reference.description_version == 0
    assert turn.budget.image_submissions == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("caption", [False, True])
async def test_delete_during_encoding_blocks_factory_submission(
    revocation, monkeypatch, caption
):
    from astrbot.core.utils.media_utils import MediaResolver

    turn = await revocation.create_turn()
    part = await capture(turn, revocation.source)
    entered, release = asyncio.Event(), asyncio.Event()
    method = "to_data_url" if caption else "to_base64_data"
    original = getattr(MediaResolver, method)

    async def blocked_encode(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(MediaResolver, method, blocked_encode)
    operation = (
        describe_images(turn, revocation.provider, occurrence_ids=[part.occurrence_id])
        if caption
        else run_visual(turn, revocation.provider, part)
    )
    task = asyncio.create_task(operation)
    await asyncio.wait_for(entered.wait(), 5)
    try:
        await turn.db.delete_conversation(turn.conversation_id)
    finally:
        release.set()
    try:
        await asyncio.wait_for(task, 5)
    except Exception as exc:
        from astrbot.core.image_request_budget import ImageAuthorizationRevoked

        assert caption and isinstance(exc, ImageAuthorizationRevoked)
    assert turn.budget.image_submissions == 0
    if caption:
        revocation.provider.text_chat.assert_not_called()
    else:
        assert "data:image" not in str(revocation.provider.text_chat.call_args.kwargs)


@pytest.mark.asyncio
async def test_sdk_internal_retry_rechecks_revocation(revocation):
    from astrbot.core.image_request_budget import ImageAuthorizationRevoked

    turn = await revocation.create_turn()
    part = await capture(turn, revocation.source)
    transmitted = []
    rejected_retries = []

    async def retrying_provider(**payload):
        charge_image_attempt(payload)
        transmitted.append(payload)
        if "data:image" in str(payload):
            await turn.db.delete_conversation(turn.conversation_id)
            try:
                charge_image_attempt(payload)
            except ImageAuthorizationRevoked:
                rejected_retries.append(True)
                raise
            transmitted.append(payload)
        return LLMResponse(role="assistant", completion_text="done")

    revocation.provider.text_chat.side_effect = retrying_provider
    await run_visual(turn, revocation.provider, part)
    assert rejected_retries == [True]
    assert len(transmitted) == 2
    assert "data:image" in str(transmitted[0])
    assert "data:image" not in str(transmitted[1])
    assert turn.budget.image_submissions == 1


@pytest.mark.asyncio
async def test_same_database_separate_handles_share_revocation(revocation):
    turn = await revocation.create_turn()
    part = await capture(turn, revocation.source)
    second_handle = SQLiteDatabase(str(revocation.path / "test.db"))
    second_handle.inited = True
    try:
        await second_handle.delete_conversation(turn.conversation_id)
        await run_visual(turn, revocation.provider, part)
        assert "data:image" not in str(revocation.provider.text_chat.call_args.kwargs)
    finally:
        await second_handle.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["asset", "checkpoint", "owner", "platform"])
async def test_persisted_preview_rechecks_metadata_without_broadcast(
    revocation, change
):
    from sqlalchemy import update

    from astrbot.core.db.po import (
        ConversationImageCheckpoint,
        ConversationV2,
        ImageAsset,
    )

    turn = await revocation.create_turn()
    part = await capture(turn, revocation.source)
    await persist(turn, part)
    assert part.occurrence_id in turn.persisted_references
    if change == "asset":
        statement = (
            update(ImageAsset)
            .where(ImageAsset.asset_id == part.asset_id)
            .values(state="pending_delete")
        )
    elif change == "checkpoint":
        statement = (
            update(ConversationImageCheckpoint)
            .where(ConversationImageCheckpoint.conversation_id == turn.conversation_id)
            .values(active=False)
        )
    else:
        statement = (
            update(ConversationV2)
            .where(ConversationV2.conversation_id == turn.conversation_id)
            .values(**{"user_id" if change == "owner" else "platform_id": "changed"})
        )
    async with revocation.db.get_db() as session, session.begin():
        await session.execute(statement)
    assert not turn.revoked and not turn.revoked_occurrences
    await run_visual(turn, revocation.provider, part)
    assert "data:image" not in str(revocation.provider.text_chat.call_args.kwargs)
    assert turn.budget.image_submissions == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_request_scope_does_not_escape_yield_or_cross_task_close(
    revocation, streaming
):
    from astrbot.core.image_request_budget import current_image_request

    turn = await revocation.create_turn()
    part = await capture(turn, revocation.source)
    closed = []

    async def stream(**payload):
        assert current_image_request.get() is not None
        charge_image_attempt(payload)
        try:
            yield LLMResponse(
                role="assistant", completion_text="partial", is_chunk=True
            )
            raise AssertionError("Early close should not request another chunk")
        finally:
            closed.append(current_image_request.get() is not None)

    async def respond(**payload):
        assert current_image_request.get() is not None
        charge_image_attempt(payload)
        return LLMResponse(role="assistant", completion_text="done")

    revocation.provider.text_chat_stream = stream
    revocation.provider.text_chat = AsyncMock(side_effect=respond)
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=revocation.provider,
        request=ProviderRequest(
            prompt="Inspect", extra_user_content_parts=[part], image_context=turn
        ),
        run_context=ContextWrapper(context=None),
        tool_executor=MagicMock(),
        agent_hooks=BaseAgentRunHooks(),
        streaming=streaming,
    )
    iterator = runner._iter_llm_responses()
    assert current_image_request.get() is None
    response = await anext(iterator)
    assert response.completion_text == ("partial" if streaming else "done")
    assert current_image_request.get() is None
    await asyncio.create_task(iterator.aclose())
    assert current_image_request.get() is None
    assert closed == ([True] if streaming else [])
    assert turn.budget.image_submissions == 1
