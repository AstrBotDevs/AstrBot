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
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.dashboard.services.conversation_service import ConversationService


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
