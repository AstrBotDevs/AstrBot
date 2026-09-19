import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.core.platform.sources.webchat import webchat_adapter
from astrbot.core.platform.sources.webchat.webchat_queue_mgr import WebChatQueueMgr
from astrbot.dashboard.services import chat_service
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError


@pytest.mark.asyncio
async def test_idle_proactive_send_persists_once_and_notifies_viewers(
    monkeypatch, tmp_path
):
    manager = WebChatQueueMgr()
    adapter = object.__new__(webchat_adapter.WebChatAdapter)
    adapter._webchat_queue_mgr = manager
    adapter.attachments_dir = tmp_path
    saved = AsyncMock()
    monkeypatch.setattr(
        webchat_adapter.db_helper, "insert_platform_message_history", saved
    )
    monkeypatch.setattr(webchat_adapter.Platform, "send_by_session", AsyncMock())
    streams = [manager.subscribe_history("session") for _ in range(2)]
    for stream in streams:
        await anext(stream)
    try:
        await adapter.send_by_session(
            SimpleNamespace(session_id="webchat!alice!session"),
            MessageChain([Plain("scheduled reminder")]),
        )
        saved.assert_awaited_once()
        assert saved.call_args.kwargs["user_id"] == "session"
        for stream in streams:
            assert "history_updated" in await asyncio.wait_for(anext(stream), 1)
        assert manager.back_queues == {}
    finally:
        for stream in streams:
            await stream.aclose()


@pytest.mark.asyncio
async def test_history_notifications_are_isolated_coalesced_and_cleaned_up():
    manager = WebChatQueueMgr()
    first = manager.subscribe_history("one")
    second = manager.subscribe_history("one")
    other = manager.subscribe_history("two")
    for stream in (first, second, other):
        assert "history_updated" in await anext(stream)
    try:
        for _ in range(100):
            manager.notify_history_updated("one")
        assert all(q.qsize() == 1 for q in manager._history_subscribers["one"])
        assert all(q.empty() for q in manager._history_subscribers["two"])
        assert "history_updated" in await anext(first)
        assert "history_updated" in await anext(second)
        assert manager.back_queues == {}
        await first.aclose()
        manager.notify_history_updated("one")
        assert "history_updated" in await anext(second)
    finally:
        for stream in (first, second, other):
            await stream.aclose()
    assert manager._history_subscribers == {}


@pytest.mark.asyncio
async def test_cancelled_history_subscription_releases_queue():
    manager = WebChatQueueMgr()
    stream = manager.subscribe_history("session")
    await anext(stream)
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert manager._history_subscribers == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_proactive_history_notifies_only_after_persistence(
    monkeypatch, tmp_path, failure
):
    manager = WebChatQueueMgr()
    adapter = object.__new__(webchat_adapter.WebChatAdapter)
    adapter._webchat_queue_mgr = manager
    adapter.attachments_dir = tmp_path
    saved = AsyncMock(
        side_effect=RuntimeError("storage unavailable") if failure else None
    )
    monkeypatch.setattr(
        webchat_adapter.db_helper, "insert_platform_message_history", saved
    )
    stream = manager.subscribe_history("session")
    await anext(stream)
    try:
        if failure:
            with pytest.raises(RuntimeError, match="storage unavailable"):
                await adapter._save_proactive_message(
                    "session", MessageChain([Plain("reminder")])
                )
            assert all(q.empty() for q in manager._history_subscribers["session"])
        else:
            await adapter._save_proactive_message(
                "session", MessageChain([Plain("reminder")])
            )
            saved.assert_awaited_once()
            assert "history_updated" in await asyncio.wait_for(anext(stream), 1)
    finally:
        await stream.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session", "allowed"),
    [
        (None, False),
        (SimpleNamespace(creator="bob", platform_id="webchat"), False),
        (SimpleNamespace(creator="alice", platform_id="telegram"), False),
        (SimpleNamespace(creator="alice", platform_id="webchat"), True),
    ],
)
async def test_history_subscription_requires_owned_webchat_session(
    monkeypatch, session, allowed
):
    manager = WebChatQueueMgr()
    monkeypatch.setattr(chat_service, "webchat_queue_mgr", manager)
    service = object.__new__(ChatService)
    service.db = SimpleNamespace(
        get_platform_session_by_id=AsyncMock(return_value=session)
    )
    if not allowed:
        with pytest.raises(ChatServiceError):
            await service.subscribe_session_history("alice", "session")
        assert manager._history_subscribers == {}
    else:
        stream = await service.subscribe_session_history("alice", "session")
        assert "history_updated" in await anext(stream)
        await stream.aclose()
