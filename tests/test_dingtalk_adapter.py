import asyncio
import threading
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Plain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.dingtalk import dingtalk_adapter
from astrbot.core.platform.sources.dingtalk.dingtalk_adapter import (
    DINGTALK_RECONNECT_INITIAL_DELAY,
    DINGTALK_RECONNECT_MAX_DELAY,
    DingtalkPlatformAdapter,
    _dingtalk_reconnect_delay,
)


def test_dingtalk_reconnect_delay_uses_exponential_backoff():
    assert [_dingtalk_reconnect_delay(i) for i in range(1, 5)] == [
        10,
        20,
        40,
        80,
    ]


def test_dingtalk_reconnect_delay_has_minimum_delay():
    assert _dingtalk_reconnect_delay(0) == DINGTALK_RECONNECT_INITIAL_DELAY
    assert _dingtalk_reconnect_delay(-1) == DINGTALK_RECONNECT_INITIAL_DELAY


def test_dingtalk_reconnect_delay_is_capped():
    assert _dingtalk_reconnect_delay(20) == DINGTALK_RECONNECT_MAX_DELAY


def test_message_chain_plain_text_extracts_text_only():
    assert (
        DingtalkPlatformAdapter._message_chain_plain_text(
            MessageChain([Plain("hello"), Plain(" world")])
        )
        == "hello world"
    )
    assert (
        DingtalkPlatformAdapter._message_chain_plain_text(
            MessageChain([Plain("hello"), At(qq="user-id")])
        )
        is None
    )
    assert DingtalkPlatformAdapter._message_chain_plain_text(MessageChain()) is None


@pytest.mark.asyncio
async def test_send_by_session_prefers_card_for_plain_text(monkeypatch):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_id = "robot-code"
    adapter.config = {"id": "dingtalk"}
    adapter.send_plain_text_as_card = True
    adapter.send_text_card_by_session = AsyncMock(return_value=True)
    adapter.send_message_chain_to_group = AsyncMock()
    base_send_calls = []

    async def base_send(self, session, message_chain):
        base_send_calls.append((self, session, message_chain))

    monkeypatch.setattr(dingtalk_adapter.Platform, "send_by_session", base_send)

    session = MessageSession("dingtalk", MessageType.GROUP_MESSAGE, "conversation-id")
    message = MessageChain([Plain("card content")])

    await adapter.send_by_session(session, message)

    adapter.send_text_card_by_session.assert_awaited_once_with(session, "card content")
    adapter.send_message_chain_to_group.assert_not_awaited()
    assert base_send_calls == [(adapter, session, message)]


@pytest.mark.asyncio
async def test_send_by_session_falls_back_when_card_send_fails(monkeypatch):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_id = "robot-code"
    adapter.config = {"id": "dingtalk"}
    adapter.send_plain_text_as_card = True
    adapter.send_text_card_by_session = AsyncMock(return_value=False)
    adapter.send_message_chain_to_group = AsyncMock()
    base_send_calls = []

    async def base_send(self, session, message_chain):
        base_send_calls.append((self, session, message_chain))

    monkeypatch.setattr(dingtalk_adapter.Platform, "send_by_session", base_send)

    session = MessageSession("dingtalk", MessageType.GROUP_MESSAGE, "conversation-id")
    message = MessageChain([Plain("fallback content")])

    await adapter.send_by_session(session, message)

    adapter.send_text_card_by_session.assert_awaited_once_with(
        session,
        "fallback content",
    )
    adapter.send_message_chain_to_group.assert_awaited_once_with(
        open_conversation_id="conversation-id",
        robot_code="robot-code",
        message_chain=message,
    )
    assert base_send_calls == [(adapter, session, message)]


@pytest.mark.asyncio
async def test_send_by_session_keeps_plain_text_normal_when_card_toggle_is_off(
    monkeypatch,
):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_id = "robot-code"
    adapter.config = {"id": "dingtalk"}
    adapter.send_plain_text_as_card = False
    adapter.send_text_card_by_session = AsyncMock()
    adapter.send_message_chain_to_group = AsyncMock()
    base_send_calls = []

    async def base_send(self, session, message_chain):
        base_send_calls.append((self, session, message_chain))

    monkeypatch.setattr(dingtalk_adapter.Platform, "send_by_session", base_send)

    session = MessageSession("dingtalk", MessageType.GROUP_MESSAGE, "conversation-id")
    message = MessageChain([Plain("normal content")])

    await adapter.send_by_session(session, message)

    adapter.send_text_card_by_session.assert_not_awaited()
    adapter.send_message_chain_to_group.assert_awaited_once_with(
        open_conversation_id="conversation-id",
        robot_code="robot-code",
        message_chain=message,
    )
    assert base_send_calls == [(adapter, session, message)]


@pytest.mark.asyncio
async def test_send_by_session_keeps_mixed_messages_on_normal_path(monkeypatch):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_id = "robot-code"
    adapter.config = {"id": "dingtalk"}
    adapter.send_plain_text_as_card = True
    adapter.send_text_card_by_session = AsyncMock()
    adapter.send_message_chain_to_group = AsyncMock()
    base_send_calls = []

    async def base_send(self, session, message_chain):
        base_send_calls.append((self, session, message_chain))

    monkeypatch.setattr(dingtalk_adapter.Platform, "send_by_session", base_send)

    session = MessageSession("dingtalk", MessageType.GROUP_MESSAGE, "conversation-id")
    message = MessageChain([Plain("hello"), At(qq="user-id")])

    await adapter.send_by_session(session, message)

    adapter.send_text_card_by_session.assert_not_awaited()
    adapter.send_message_chain_to_group.assert_awaited_once_with(
        open_conversation_id="conversation-id",
        robot_code="robot-code",
        message_chain=message,
    )
    assert base_send_calls == [(adapter, session, message)]


@pytest.mark.asyncio
async def test_dingtalk_reconnect_delay_wakes_on_terminate(monkeypatch):
    class ObservedEvent:
        def __init__(self) -> None:
            self._event = threading.Event()
            self.wait_started = threading.Event()
            self.wait_timeout: float | None = None

        def is_set(self) -> bool:
            return self._event.is_set()

        def set(self) -> None:
            self._event.set()

        def wait(self, timeout: float | None = None) -> bool:
            self.wait_timeout = timeout
            self.wait_started.set()
            return self._event.wait(timeout)

    class FailingClient:
        websocket = None

        async def start(self) -> None:
            raise RuntimeError("connect failed")

    terminated_event = ObservedEvent()
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_ = FailingClient()
    adapter._shutdown_event = threading.Event()
    adapter._terminated_event = terminated_event

    monkeypatch.setattr(dingtalk_adapter, "_dingtalk_reconnect_delay", lambda _: 60)

    run_task = asyncio.create_task(adapter.run())
    try:
        wait_started = await asyncio.to_thread(terminated_event.wait_started.wait, 1)
        assert wait_started
        assert terminated_event.wait_timeout == 60

        await adapter.terminate()
        await asyncio.wait_for(run_task, timeout=1)
    finally:
        if not run_task.done():
            await adapter.terminate()
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)
