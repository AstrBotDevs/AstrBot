import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core import conversation_mgr
from astrbot.core.agent.message import Message
from astrbot.core.astr_agent_runtime.history import save_agent_history
from astrbot.core.astr_agent_runtime.main_session import MainAgentSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.dashboard.services import chat_service, conversation_service
from astrbot.dashboard.services.chat_service import (
    ChatService,
    ChatServiceError,
    build_webchat_unified_msg_origin,
)
from astrbot.dashboard.services.conversation_service import (
    ConversationService,
    ConversationServiceError,
)


@pytest_asyncio.fixture
async def history_service(temp_db, monkeypatch):
    """Use real conversation storage and the built-in group context buffer.

    Args:
        temp_db: Isolated SQLite database.
        monkeypatch: Fixture restoring shared preference storage after the test.

    Yields:
        Dashboard service, conversation manager, and group context buffer.
    """
    preferences = SharedPreferences(db_helper=temp_db)
    monkeypatch.setattr(conversation_mgr, "sp", preferences)
    manager = conversation_mgr.ConversationManager(temp_db)
    context = SimpleNamespace(
        astrbot_config_mgr=None,
        conversation_manager=manager,
    )
    plugin = Main(context)
    group = plugin.group_chat_context
    group.cfg = Mock(return_value={"group_message_max_cnt": 1000})
    group._format_message = AsyncMock(side_effect=lambda event, cfg: event.text)
    lifecycle = SimpleNamespace(
        conversation_manager=manager,
        plugin_manager=SimpleNamespace(
            context=SimpleNamespace(
                get_registered_star=Mock(return_value=SimpleNamespace(star_cls=plugin))
            )
        ),
    )
    try:
        yield ConversationService(temp_db, lifecycle), manager, group
    finally:
        await preferences.close()


@pytest.mark.asyncio
async def test_history_edit_survives_inflight_commit_and_next_turn(history_service):
    service, manager, _ = history_service
    umo = "qq:GroupMessage:history-edit"
    original = [
        {"role": "user", "content": "deleted message"},
        {"role": "assistant", "content": "retained answer"},
    ]
    cid = await manager.new_conversation(umo, content=original)
    session = MainAgentSession(
        SimpleNamespace(context=SimpleNamespace(conversation_manager=manager)), cid, umo
    )
    edit = None
    try:
        # Hold the real native execution scope while an earlier reply is pending.
        async with session._execution_scope():
            snapshot = await manager.get_conversation(umo, cid)
            edit = asyncio.create_task(
                service.update_history(
                    {"user_id": umo, "cid": cid, "history": original[1:]}
                )
            )
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(edit), timeout=0.1)
            await save_agent_history(
                req=ProviderRequest(conversation=snapshot),
                llm_response=LLMResponse(
                    role="assistant", completion_text="late reply"
                ),
                all_messages=[
                    *[Message.model_validate(item) for item in original],
                    Message(role="assistant", content="late reply"),
                ],
                runner_stats=None,
                commit=session._commit_history,
            )
        await asyncio.wait_for(edit, timeout=5)
        edited = await manager.get_conversation(umo, cid)
        assert json.loads(edited.history) == original[1:]

        async with session._execution_scope():
            await save_agent_history(
                req=ProviderRequest(conversation=edited),
                llm_response=LLMResponse(role="assistant", completion_text="new reply"),
                all_messages=[
                    *[
                        Message.model_validate(item)
                        for item in json.loads(edited.history)
                    ],
                    Message(role="user", content="next group message"),
                    Message(role="assistant", content="new reply"),
                ],
                runner_stats=None,
                commit=session._commit_history,
            )
        final = await manager.get_conversation(umo, cid)
        assert json.loads(final.history) == [
            *original[1:],
            {"role": "user", "content": "next group message"},
            {"role": "assistant", "content": "new reply"},
        ]
    finally:
        if edit is not None and not edit.done():
            edit.cancel()
            await asyncio.gather(edit, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("delete_current", [False, True])
async def test_delete_clears_only_current_conversation_group_context(
    history_service, batch, delete_current
):
    service, manager, group = history_service
    umo = "qq:GroupMessage:deleted-group"
    other = "qq:GroupMessage:other-group"
    archived = await manager.new_conversation(umo)
    current = await manager.new_conversation(umo)
    cid = current if delete_current else archived
    group.raw_records[umo].append("old buffered message")
    group._record_ids[umo].append("old-record")
    group.raw_records[other].append("other group message")
    group._record_ids[other].append("other-record")
    payload = {"user_id": umo, "cid": cid}

    result = await service.delete_conversation(
        {"conversations": [payload]} if batch else payload
    )

    if batch:
        assert result["deleted_count"] == 1
        assert result["failed_count"] == 0
    assert await manager.get_conversation(umo, cid) is None
    assert await manager.get_curr_conversation_id(umo) == (
        None if delete_current else current
    )
    assert list(group.raw_records[other]) == ["other group message"]
    assert list(group._record_ids[other]) == ["other-record"]
    if delete_current:
        assert umo not in group.raw_records
        assert umo not in group._record_ids
    else:
        assert list(group.raw_records[umo]) == ["old buffered message"]

    extras = {}
    event = SimpleNamespace(
        unified_msg_origin=umo,
        text="next group message",
        get_message_type=lambda: MessageType.GROUP_MESSAGE,
        set_extra=extras.__setitem__,
        get_extra=extras.get,
    )
    await group.handle_message(event)
    request = ProviderRequest(prompt=event.text)
    await group.on_req_llm(event, request)
    if delete_current:
        assert request.extra_user_content_parts == []
    else:
        assert "old buffered message" in request.extra_user_content_parts[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("new_message_arrives", [False, True])
async def test_delete_discards_group_message_still_being_formatted(
    history_service, new_message_arrives
):
    service, manager, group = history_service
    umo = "qq:GroupMessage:pending-caption"
    cid = await manager.new_conversation(umo)
    formatting = asyncio.Event()
    resume = asyncio.Event()

    async def format_message(event, cfg):
        formatting.set()
        await resume.wait()
        return "old image caption"

    group._format_message = format_message
    event = SimpleNamespace(
        unified_msg_origin=umo,
        get_message_type=lambda: MessageType.GROUP_MESSAGE,
        set_extra=Mock(),
    )
    pending = asyncio.create_task(group.handle_message(event))
    try:
        await asyncio.wait_for(formatting.wait(), timeout=5)
        await service.delete_conversation({"user_id": umo, "cid": cid})
        if new_message_arrives:
            group._format_message = AsyncMock(return_value="new group message")
            await group.handle_message(
                SimpleNamespace(
                    unified_msg_origin=umo,
                    get_message_type=lambda: MessageType.GROUP_MESSAGE,
                    set_extra=Mock(),
                )
            )
        resume.set()
        await asyncio.wait_for(pending, timeout=5)
        if new_message_arrives:
            assert list(group.raw_records[umo]) == ["new group message"]
            assert len(group._record_ids[umo]) == 1
        else:
            assert umo not in group.raw_records
            assert umo not in group._record_ids
        event.set_extra.assert_not_called()
    finally:
        resume.set()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["delete", "batch_delete", "edit"])
async def test_mutation_rejects_conversation_from_another_session(
    history_service, operation
):
    service, manager, group = history_service
    owner = "qq:GroupMessage:owner"
    other = "qq:GroupMessage:other"
    original = [{"role": "user", "content": "keep this history"}]
    cid = await manager.new_conversation(owner, content=original)
    other_cid = await manager.new_conversation(other)
    group.raw_records[owner].append("owner observation")
    group.raw_records[other].append("other observation")
    payload = {"user_id": other, "cid": cid, "history": []}

    if operation == "batch_delete":
        result = await service.delete_conversation({"conversations": [payload]})
        assert result["deleted_count"] == 0
        assert result["failed_count"] == 1
    else:
        with pytest.raises(ConversationServiceError):
            if operation == "delete":
                await service.delete_conversation(payload)
            else:
                await service.update_history(payload)

    conversation = await manager.get_conversation(owner, cid)
    assert json.loads(conversation.history) == original
    assert await manager.get_curr_conversation_id(owner) == cid
    assert await manager.get_curr_conversation_id(other) == other_cid
    assert list(group.raw_records[owner]) == ["owner observation"]
    assert list(group.raw_records[other]) == ["other observation"]


@pytest.mark.asyncio
@pytest.mark.parametrize("old_index", [0, 1])
async def test_cleared_event_cannot_consume_new_group_observations(
    history_service, old_index
):
    service, manager, group = history_service
    umo = "qq:GroupMessage:stale-event"
    cid = await manager.new_conversation(umo)
    group.raw_records[umo].extend(["old observation"] * old_index)
    group._record_ids[umo].extend(["old-id"] * old_index)
    extras = {}
    old_event = SimpleNamespace(
        unified_msg_origin=umo,
        text="old trigger",
        get_message_type=lambda: MessageType.GROUP_MESSAGE,
        set_extra=extras.__setitem__,
        get_extra=extras.get,
    )
    await group.handle_message(old_event)
    await service.delete_conversation({"user_id": umo, "cid": cid})
    group.raw_records[umo].extend(["new observation", "new trigger"])
    group._record_ids[umo].extend(["new-id", "new-trigger-id"])

    request = ProviderRequest(prompt=old_event.text)
    await group.on_req_llm(old_event, request)

    assert request.extra_user_content_parts == []
    assert list(group.raw_records[umo]) == ["new observation", "new trigger"]
    assert list(group._record_ids[umo]) == ["new-id", "new-trigger-id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["new", "switch"])
async def test_deletion_preserves_observations_after_conversation_selection(
    history_service, monkeypatch, operation
):
    service, manager, group = history_service
    umo = "qq:GroupMessage:selection-race"
    archived = await manager.new_conversation(umo)
    current = await manager.new_conversation(umo)
    group.raw_records[umo].append("old observation")
    group._record_ids[umo].append("old-id")
    deleting = asyncio.Event()
    resume = asyncio.Event()
    original_delete = manager.db.delete_conversation

    async def delayed_delete(*args, **kwargs):
        deleting.set()
        await resume.wait()
        await original_delete(*args, **kwargs)

    monkeypatch.setattr(manager.db, "delete_conversation", delayed_delete)

    async def select_and_receive():
        if operation == "new":
            selected = await manager.new_conversation(umo)
        else:
            await manager.switch_conversation(umo, archived)
            selected = archived
        await group.handle_message(
            SimpleNamespace(
                unified_msg_origin=umo,
                text="new conversation observation",
                get_message_type=lambda: MessageType.GROUP_MESSAGE,
                set_extra=Mock(),
            )
        )
        return selected

    deletion = asyncio.create_task(
        service.delete_conversation({"user_id": umo, "cid": current})
    )
    selection = None
    try:
        await asyncio.wait_for(deleting.wait(), timeout=5)
        selection = asyncio.create_task(select_and_receive())
        # A correct implementation queues selection until deletion and cleanup finish.
        try:
            await asyncio.wait_for(asyncio.shield(selection), timeout=0.1)
        except TimeoutError:
            pass
        resume.set()
        await asyncio.wait_for(deletion, timeout=5)
        selected = await asyncio.wait_for(selection, timeout=5)
        assert await manager.get_curr_conversation_id(umo) == selected
        assert list(group.raw_records[umo]) == ["new conversation observation"]
    finally:
        resume.set()
        tasks = [deletion, *([selection] if selection is not None else [])]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["delete", "edit"])
async def test_busy_conversation_mutation_times_out_without_changes(
    history_service, monkeypatch, operation
):
    service, manager, group = history_service
    monkeypatch.setattr(
        conversation_service, "HISTORY_MUTATION_TIMEOUT", 0.01, raising=False
    )
    umo = "qq:GroupMessage:busy-mutation"
    original = [{"role": "user", "content": "unchanged"}]
    cid = await manager.new_conversation(umo, content=original)
    group.raw_records[umo].append("pending observation")
    session = MainAgentSession(
        SimpleNamespace(context=SimpleNamespace(conversation_manager=manager)), cid, umo
    )
    payload = {"user_id": umo, "cid": cid, "history": []}
    mutate = (
        service.delete_conversation if operation == "delete" else service.update_history
    )
    async with session._execution_scope():
        with pytest.raises(ConversationServiceError, match="busy.*retry"):
            await asyncio.wait_for(mutate(payload), timeout=1)
        conversation = await manager.get_conversation(umo, cid)
        assert json.loads(conversation.history) == original
        assert list(group.raw_records[umo]) == ["pending observation"]
    # A timed-out waiter must neither run later nor leave the session locked.
    await asyncio.wait_for(mutate(payload), timeout=1)
    conversation = await manager.get_conversation(umo, cid)
    if operation == "delete":
        assert conversation is None
    else:
        assert json.loads(conversation.history) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [False, True])
async def test_webchat_edit_coordinates_with_native_history_commit(
    history_service, monkeypatch, tmp_path, timeout
):
    service, manager, _ = history_service
    db = service.db_helper
    monkeypatch.setattr(chat_service, "get_astrbot_data_path", lambda: str(tmp_path))
    if timeout:
        monkeypatch.setattr(
            chat_service, "HISTORY_MUTATION_TIMEOUT", 0.01, raising=False
        )
    chat = ChatService(
        db,
        SimpleNamespace(
            conversation_manager=manager,
            platform_message_history_manager=PlatformMessageHistoryManager(db),
            umop_config_router=None,
        ),
    )
    platform_session = await db.create_platform_session(creator="alice")
    umo = build_webchat_unified_msg_origin(platform_session)
    original = [
        {"role": "user", "content": "old message"},
        {"role": "assistant", "content": "old reply"},
        {"role": "_checkpoint", "content": {"id": "checkpoint"}},
    ]
    cid = await manager.new_conversation(umo, content=original)
    content = {"type": "user", "message": [{"type": "plain", "text": "old message"}]}
    record = await db.insert_platform_message_history(
        "webchat", platform_session.session_id, content, llm_checkpoint_id="checkpoint"
    )
    native = MainAgentSession(
        SimpleNamespace(context=SimpleNamespace(conversation_manager=manager)), cid, umo
    )
    payload = {
        "session_id": platform_session.session_id,
        "message_id": record.id,
        "content": {"type": "user", "message": [{"type": "plain", "text": "edited"}]},
    }
    edit = None
    try:
        async with native._execution_scope():
            edit = asyncio.create_task(chat.update_message("alice", payload))
            if timeout:
                with pytest.raises(ChatServiceError, match="busy.*retry"):
                    await asyncio.wait_for(edit, timeout=1)
                untouched = await db.get_platform_message_history_by_id(record.id)
                assert untouched.content == content
                assert untouched.llm_checkpoint_id == "checkpoint"
            else:
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(edit), timeout=0.1)
            await native._commit_history(original, None)
        if timeout:
            updated = await manager.get_conversation(umo, cid)
            assert json.loads(updated.history) == original
            result = await asyncio.wait_for(chat.update_message("alice", payload), 5)
        else:
            result = await asyncio.wait_for(edit, timeout=5)
        updated = await manager.get_conversation(umo, cid)
        assert json.loads(updated.history) == []
        assert result["needs_regenerate"] is True
        updated_record = await db.get_platform_message_history_by_id(record.id)
        assert updated_record.content["message"] == payload["content"]["message"]
        assert updated_record.llm_checkpoint_id != "checkpoint"
    finally:
        if edit is not None and not edit.done():
            edit.cancel()
            await asyncio.gather(edit, return_exceptions=True)
