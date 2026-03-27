from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import (
    TypingSessionState,
    WeixinOCAdapter,
)
from astrbot.core.platform.sources.weixin_oc.weixin_oc_client import WeixinOCClient
from astrbot.core.platform.sources.weixin_oc.weixin_oc_event import WeixinOCMessageEvent


@pytest.fixture
def client():
    return WeixinOCClient(
        adapter_id="wx-1",
        base_url="https://example.com",
        cdn_base_url="https://cdn.example.com",
        api_timeout_ms=15000,
        token="token-1",
    )


@pytest.fixture
def adapter():
    obj = WeixinOCAdapter(
        platform_config={
            "id": "wx-1",
            "type": "weixin_oc",
            "weixin_oc_token": "token-1",
        },
        platform_settings={},
        event_queue=asyncio.Queue(),
    )
    obj._context_tokens["user-1"] = "ctx-1"
    return obj


@pytest.fixture
def weixin_event():
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot123"
    message.session_id = "user-1"
    message.message_id = "msg123"
    message.sender = MessageMember(user_id="user-1", nickname="User")
    message.message = [Plain(text="hello")]
    message.message_str = "hello"
    message.raw_message = None

    platform = MagicMock()
    platform.start_typing = AsyncMock()
    platform.stop_typing = AsyncMock()
    platform.send_by_session = AsyncMock()

    event = WeixinOCMessageEvent(
        message_str="hello",
        message_obj=message,
        platform_meta=PlatformMetadata(
            name="weixin_oc",
            description="个人微信",
            id="wx-1",
            support_streaming_message=False,
        ),
        session_id="user-1",
        platform=platform,
    )
    return event, platform


@pytest.mark.asyncio
async def test_get_typing_config_uses_getconfig(client):
    client.request_json = AsyncMock(return_value={"typing_ticket": "ticket-1"})

    result = await client.get_typing_config("user-1", "ctx-1")

    assert result == {"typing_ticket": "ticket-1"}
    client.request_json.assert_awaited_once_with(
        "POST",
        "ilink/bot/getconfig",
        payload={
            "ilink_user_id": "user-1",
            "context_token": "ctx-1",
            "base_info": {"channel_version": "astrbot"},
        },
        token_required=True,
        timeout_ms=client.api_timeout_ms,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel, status", [(False, 1), (True, 2)])
async def test_send_typing_state_uses_sendtyping(client, cancel, status):
    client.request_json = AsyncMock(return_value={})

    await client.send_typing_state("user-1", "ticket-1", cancel=cancel)

    client.request_json.assert_awaited_once_with(
        "POST",
        "ilink/bot/sendtyping",
        payload={
            "ilink_user_id": "user-1",
            "typing_ticket": "ticket-1",
            "status": status,
            "base_info": {"channel_version": "astrbot"},
        },
        token_required=True,
        timeout_ms=client.api_timeout_ms,
    )


@pytest.mark.asyncio
async def test_event_delegates_typing_calls(weixin_event):
    event, platform = weixin_event

    await event.send_typing()
    await event.stop_typing()

    platform.start_typing.assert_awaited_once()
    platform.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_reuses_stable_owner_id(weixin_event):
    event, platform = weixin_event

    await event.send_typing()
    await event.stop_typing()

    start_owner = platform.start_typing.await_args.args[1]
    stop_owner = platform.stop_typing.await_args.args[1]
    assert start_owner == stop_owner


@pytest.mark.asyncio
async def test_start_typing_skips_without_token(adapter):
    adapter.token = None
    adapter._ensure_typing_ticket = AsyncMock(return_value="ticket-1")
    adapter._send_typing_state = AsyncMock()

    await adapter.start_typing("user-1", "owner-a")

    adapter._ensure_typing_ticket.assert_not_awaited()
    adapter._send_typing_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_typing_skips_without_context_token(adapter):
    adapter._context_tokens.clear()
    adapter._ensure_typing_ticket = AsyncMock(return_value="ticket-1")
    adapter._send_typing_state = AsyncMock()

    await adapter.start_typing("user-1", "owner-a")

    adapter._ensure_typing_ticket.assert_not_awaited()
    adapter._send_typing_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_typing_ticket_reuses_fresh_ticket(adapter):
    state = TypingSessionState(
        ticket="cached-ticket",
        ticket_context_token="ctx-1",
        refresh_after=float("inf"),
    )
    adapter.client.get_typing_config = AsyncMock()

    result = await adapter._ensure_typing_ticket("user-1", state)

    assert result == "cached-ticket"
    adapter.client.get_typing_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_typing_ticket_refreshes_stale_ticket(adapter):
    state = TypingSessionState(ticket="stale-ticket", refresh_after=0.0)
    adapter.client.get_typing_config = AsyncMock(
        return_value={"typing_ticket": "fresh-ticket"}
    )

    result = await adapter._ensure_typing_ticket("user-1", state)

    assert result == "fresh-ticket"
    assert state.ticket == "fresh-ticket"
    adapter.client.get_typing_config.assert_awaited_once_with("user-1", "ctx-1")


@pytest.mark.asyncio
async def test_ensure_typing_ticket_refreshes_when_context_token_changes(adapter):
    state = TypingSessionState(
        ticket="cached-ticket",
        ticket_context_token="ctx-1",
        refresh_after=float("inf"),
    )
    adapter._context_tokens["user-1"] = "ctx-2"
    adapter.client.get_typing_config = AsyncMock(
        return_value={"typing_ticket": "fresh-ticket"}
    )

    result = await adapter._ensure_typing_ticket("user-1", state)

    assert result == "fresh-ticket"
    assert state.ticket_context_token == "ctx-2"
    adapter.client.get_typing_config.assert_awaited_once_with("user-1", "ctx-2")


@pytest.mark.asyncio
async def test_send_typing_state_raises_on_nonzero_ret(adapter):
    adapter.client.send_typing_state = AsyncMock(
        return_value={"ret": 1, "errmsg": "expired"}
    )

    with pytest.raises(RuntimeError, match="sendtyping failed"):
        await adapter._send_typing_state("user-1", "ticket-1", cancel=False)


@pytest.mark.asyncio
async def test_cancel_task_safely_logs_task_errors(adapter):
    async def failing_task():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError as exc:
            raise RuntimeError("task wait failed") from exc

    task = asyncio.create_task(failing_task())
    await asyncio.sleep(0)

    with patch(
        "astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter.logger.warning"
    ) as warning_mock:
        await adapter._cancel_task_safely(
            task,
            log_message="weixin_oc(%s): typing cleanup failed",
            log_args=(adapter.meta().id,),
        )

    warning_mock.assert_called_once_with(
        "weixin_oc(%s): typing cleanup failed",
        adapter.meta().id,
        exc_info=True,
    )


@pytest.mark.asyncio
async def test_start_typing_same_owner_is_idempotent(adapter):
    stop_event = asyncio.Event()
    adapter._send_typing_state = AsyncMock()
    adapter._ensure_typing_ticket = AsyncMock(return_value="ticket-1")

    async def fake_keepalive(_user_id):
        await stop_event.wait()

    adapter._typing_keepalive_loop = fake_keepalive

    await adapter.start_typing("user-1", "owner-a")
    await adapter.start_typing("user-1", "owner-a")

    assert adapter._send_typing_state.await_count == 1
    state = adapter._typing_states["user-1"]
    assert state.owners == {"owner-a"}

    await adapter.stop_typing("user-1", "owner-a")
    stop_event.set()


@pytest.mark.asyncio
async def test_stop_typing_only_cancels_on_last_owner(adapter):
    stop_event = asyncio.Event()
    adapter._send_typing_state = AsyncMock()
    adapter._ensure_typing_ticket = AsyncMock(return_value="ticket-1")

    async def fake_keepalive(_user_id):
        await stop_event.wait()

    adapter._typing_keepalive_loop = fake_keepalive

    await adapter.start_typing("user-1", "owner-a")
    await adapter.start_typing("user-1", "owner-b")
    await adapter.stop_typing("user-1", "owner-a")

    state = adapter._typing_states["user-1"]
    assert state.owners == {"owner-b"}
    assert adapter._send_typing_state.await_count == 1

    await adapter.stop_typing("user-1", "owner-b")
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    stop_event.set()
    assert adapter._send_typing_state.await_count == 2


@pytest.mark.asyncio
async def test_stop_typing_is_safe_to_repeat(adapter):
    adapter._send_typing_state = AsyncMock()
    adapter._ensure_typing_ticket = AsyncMock(return_value="ticket-1")

    async def fake_keepalive(_user_id):
        await asyncio.Event().wait()

    adapter._typing_keepalive_loop = fake_keepalive

    await adapter.start_typing("user-1", "owner-a")
    await adapter.stop_typing("user-1", "owner-a")
    await adapter.stop_typing("user-1", "owner-a")
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert adapter._send_typing_state.await_count == 2


@pytest.mark.asyncio
async def test_keepalive_failure_cleans_state(adapter):
    adapter._send_typing_state = AsyncMock()
    adapter._ensure_typing_ticket = AsyncMock(return_value="ticket-1")

    async def fake_keepalive(_user_id):
        raise RuntimeError("keepalive failed")

    adapter._typing_keepalive_loop = fake_keepalive

    await adapter.start_typing("user-1", "owner-a")
    await asyncio.sleep(0)

    state = adapter._typing_states["user-1"]
    assert state.keepalive_task is None

    await adapter.stop_typing("user-1", "owner-a")
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert adapter._send_typing_state.await_count == 2


@pytest.mark.asyncio
async def test_keepalive_failure_restarts_for_active_owner(adapter):
    adapter._typing_keepalive_interval_s = 0
    adapter._send_typing_state = AsyncMock()
    adapter._ensure_typing_ticket = AsyncMock(return_value="ticket-1")
    keepalive_round = 0
    stop_event = asyncio.Event()

    async def fake_keepalive(_user_id):
        nonlocal keepalive_round
        keepalive_round += 1
        if keepalive_round == 1:
            raise RuntimeError("keepalive failed")
        await stop_event.wait()

    adapter._typing_keepalive_loop = fake_keepalive

    await adapter.start_typing("user-1", "owner-a")
    for _ in range(4):
        await asyncio.sleep(0)

    state = adapter._typing_states["user-1"]
    assert keepalive_round >= 2
    assert state.keepalive_task is not None

    stop_event.set()
    await adapter.stop_typing("user-1", "owner-a")
    for _ in range(2):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_stop_typing_does_not_cancel_new_owner_session(adapter):
    cancel_blocked = asyncio.Event()
    allow_cancel_exit = asyncio.Event()
    adapter._send_typing_state = AsyncMock()
    adapter._ensure_typing_ticket = AsyncMock(return_value="ticket-1")

    async def fake_keepalive(_user_id):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancel_blocked.set()
            await allow_cancel_exit.wait()
            raise

    adapter._typing_keepalive_loop = fake_keepalive

    await adapter.start_typing("user-1", "owner-a")
    stop_task = asyncio.create_task(adapter.stop_typing("user-1", "owner-a"))
    await cancel_blocked.wait()
    await adapter.start_typing("user-1", "owner-b")
    allow_cancel_exit.set()
    await stop_task

    assert adapter._send_typing_state.await_count == 2


@pytest.mark.asyncio
async def test_start_typing_cancels_inflight_cancel_task(adapter):
    cancel_started = asyncio.Event()
    release_cancel = asyncio.Event()
    stop_event = asyncio.Event()
    events: list[str] = []
    adapter._ensure_typing_ticket = AsyncMock(return_value="ticket-1")

    async def fake_send_typing_state(_user_id, ticket, *, cancel):
        if cancel:
            events.append("cancel-start")
            cancel_started.set()
            try:
                await release_cancel.wait()
            except asyncio.CancelledError:
                events.append("cancel-cancelled")
                raise
            events.append("cancel-finished")
            return
        events.append(f"start-{ticket}")

    async def fake_keepalive(_user_id):
        await stop_event.wait()

    adapter._send_typing_state = fake_send_typing_state
    adapter._typing_keepalive_loop = fake_keepalive

    await adapter.start_typing("user-1", "owner-a")
    await adapter.stop_typing("user-1", "owner-a")
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await cancel_started.wait()

    start_task = asyncio.create_task(adapter.start_typing("user-1", "owner-b"))
    await asyncio.sleep(0)
    release_cancel.set()
    await start_task

    assert "cancel-cancelled" in events
    assert "cancel-finished" not in events

    stop_event.set()
    await adapter.stop_typing("user-1", "owner-b")
    await asyncio.sleep(0)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_start_typing_logs_ignored_cancel_task_errors(adapter):
    stop_event = asyncio.Event()
    adapter._ensure_typing_ticket = AsyncMock(return_value="ticket-1")
    state = adapter._get_typing_state("user-1")

    async def fake_send_typing_state(_user_id, _ticket, *, cancel):
        return None

    async def fake_cancel_task():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError as exc:
            raise RuntimeError("cancel failed") from exc

    async def fake_keepalive(_user_id):
        await stop_event.wait()

    adapter._send_typing_state = fake_send_typing_state
    adapter._typing_keepalive_loop = fake_keepalive
    state.cancel_task = asyncio.create_task(fake_cancel_task())
    await asyncio.sleep(0)

    with patch(
        "astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter.logger.warning"
    ) as warning_mock:
        await adapter.start_typing("user-1", "owner-a")

    warning_mock.assert_called_once_with(
        "weixin_oc(%s): ignored error from cancelled typing task",
        adapter.meta().id,
        exc_info=True,
    )

    stop_event.set()
    await adapter.stop_typing("user-1", "owner-a")
    await asyncio.sleep(0)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_cleanup_typing_tasks_sends_final_cancel(adapter):
    adapter._send_typing_state = AsyncMock()

    async def fake_keepalive(_user_id):
        await asyncio.Event().wait()

    task = asyncio.create_task(fake_keepalive("user-1"))
    adapter._typing_states["user-1"] = TypingSessionState(
        ticket="ticket-1",
        refresh_after=float("inf"),
        keepalive_task=task,
        owners={"owner-a"},
    )

    await adapter._cleanup_typing_tasks()

    adapter._send_typing_state.assert_awaited_once_with(
        "user-1",
        "ticket-1",
        cancel=True,
    )


@pytest.mark.asyncio
async def test_run_finally_cancels_keepalive_before_client_close(adapter):
    order: list[str] = []
    task = asyncio.create_task(asyncio.Event().wait())
    adapter._typing_states["user-1"] = TypingSessionState(
        ticket="ticket-1",
        refresh_after=float("inf"),
        keepalive_task=task,
        owners={"owner-a"},
    )
    adapter._cleanup_typing_tasks = AsyncMock(
        side_effect=lambda: order.append("cleanup")
    )
    adapter.client.close = AsyncMock(side_effect=lambda: order.append("close"))

    with patch.object(
        adapter,
        "_poll_inbound_updates",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await adapter.run()

    assert order == ["cleanup", "close"]


@pytest.mark.asyncio
async def test_run_recovers_after_server_disconnect(adapter):
    poll_count = 0
    adapter._cleanup_typing_tasks = AsyncMock()
    adapter.client.close = AsyncMock()

    async def fake_poll():
        nonlocal poll_count
        poll_count += 1
        if poll_count == 1:
            raise aiohttp.ServerDisconnectedError()
        assert adapter.client.close.await_count == 1
        adapter._shutdown_event.set()

    with (
        patch.object(adapter, "_poll_inbound_updates", side_effect=fake_poll),
        patch(
            "astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep_mock,
        patch(
            "astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter.logger.warning"
        ) as warning_mock,
    ):
        await adapter.run()

    assert poll_count == 2
    warning_mock.assert_called_once()
    assert adapter.client.close.await_count == 2
    sleep_mock.assert_awaited_once_with(2)
    assert adapter._last_inbound_error
    assert (
        "Server disconnected" in adapter._last_inbound_error
        or "ServerDisconnectedError" in adapter._last_inbound_error
    )


@pytest.mark.asyncio
async def test_run_keeps_non_network_poll_errors_fatal(adapter):
    poll_mock = AsyncMock(side_effect=RuntimeError("boom"))
    adapter._cleanup_typing_tasks = AsyncMock()
    adapter.client.close = AsyncMock()

    with (
        patch.object(adapter, "_poll_inbound_updates", poll_mock),
        patch(
            "astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter.logger.exception"
        ) as exception_mock,
    ):
        await adapter.run()

    assert poll_mock.await_count == 1
    adapter._cleanup_typing_tasks.assert_awaited_once()
    adapter.client.close.assert_awaited_once()
    exception_mock.assert_called_once()


@pytest.mark.asyncio
async def test_send_still_works_with_existing_event_behavior(weixin_event):
    event, platform = weixin_event

    with patch(
        "astrbot.core.platform.astr_message_event.Metric.upload",
        new_callable=AsyncMock,
    ):
        await event.send(MessageChain([Plain("reply")]))

    platform.send_by_session.assert_awaited_once()
