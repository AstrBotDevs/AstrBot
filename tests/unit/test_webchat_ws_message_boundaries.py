import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent
from astrbot.core.platform.sources.webchat.webchat_queue_mgr import webchat_queue_mgr
from astrbot.dashboard.services.live_chat_service import LiveChatService
from astrbot.dashboard.services.open_api_service import (
    OpenApiService,
    OpenApiWebSocketChatBridge,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("consumer", ["openapi", "live"])
@pytest.mark.parametrize("mode", ["nonstream", "stream", "end_only", "empty"])
async def test_websocket_consumers_preserve_message_boundaries(consumer, mode):
    """Consume real adapter frames without splitting components or saving empties.

    Args:
        consumer: WebSocket service receiving the adapter's output.
        mode: Normal sends, streaming sends, an unfinished stream, or no output.
    """
    session_id = f"boundary-{consumer}-{mode}"
    request_id = f"request-{session_id}"
    core = SimpleNamespace(
        platform_manager=SimpleNamespace(platform_insts=[]),
        platform_message_history_manager=SimpleNamespace(insert=AsyncMock()),
        astrbot_config_mgr=SimpleNamespace(confs={}),
        astrbot_config={"dashboard": {"jwt_secret": "test-secret"}},
        plugin_manager=SimpleNamespace(),
    )
    saved_record = SimpleNamespace(id=1, created_at=datetime.now(timezone.utc))
    core.platform_message_history_manager.insert.return_value = saved_record
    save = AsyncMock(return_value=saved_record)
    send_json = AsyncMock()
    send_error = AsyncMock()
    build_parts = AsyncMock(return_value=[{"type": "plain", "text": "hello"}])
    payload = {
        "t": "send",
        "message": [{"type": "plain", "text": "hello"}],
        "session_id": session_id,
        "message_id": request_id,
    }
    if consumer == "openapi":
        service = OpenApiService(SimpleNamespace(), core)
        service.prepare_chat_send = AsyncMock(return_value=("alice", session_id, None))
        service.update_session_config_route = AsyncMock(return_value=None)
        bridge = OpenApiWebSocketChatBridge(
            build_user_message_parts=build_parts,
            create_attachment_from_file=AsyncMock(),
            extract_web_search_refs=lambda *_: {},
            insert_user_message=AsyncMock(),
            save_bot_message=save,
        )
        task = asyncio.create_task(
            service.handle_chat_ws_send(
                post_data=payload,
                conf_list=[],
                chat_bridge=bridge,
                send_json=send_json,
                send_error=send_error,
            )
        )
    else:
        service = LiveChatService(SimpleNamespace(), core)
        session = service.create_session("alice")
        service.build_chat_message_parts = build_parts
        service.ensure_chat_subscription = AsyncMock(return_value="subscription")
        service.save_bot_message = save
        task = asyncio.create_task(
            service.handle_chat_message(session, payload, send_json)
        )

    try:
        await asyncio.wait_for(
            webchat_queue_mgr.get_or_create_queue(session_id).get(), timeout=1
        )
        if mode != "empty":
            await WebChatMessageEvent._send(
                request_id,
                MessageChain(type="reasoning").message("Thought."),
                session_id,
                streaming=mode != "nonstream",
            )
            await WebChatMessageEvent._send(
                request_id,
                MessageChain([Plain("First."), Plain("Second.")]),
                session_id,
                streaming=mode != "nonstream",
                emit_complete=mode == "stream",
            )
            await WebChatMessageEvent._send(
                request_id,
                MessageChain().message("Third."),
                session_id,
                streaming=mode != "nonstream",
                emit_complete=mode == "stream",
            )
        await WebChatMessageEvent._send(request_id, None, session_id)
        await asyncio.wait_for(task, timeout=1)

        saved_parts = [call.args[1] for call in save.await_args_list]
        assert len(saved_parts) == (
            0 if mode == "empty" else 1 if mode == "end_only" else 2
        )
        if saved_parts:
            assert saved_parts[0][0] == {"type": "think", "think": "Thought."}
            assert [
                "".join(part.get("text", "") for part in parts) for parts in saved_parts
            ] == (
                ["First.Second.Third."]
                if mode == "end_only"
                else ["First.Second.", "Third."]
            )
        saved_events = [
            call.args[0]
            for call in send_json.await_args_list
            if call.args[0].get("type") == "message_saved"
        ]
        assert len(saved_events) == len(saved_parts)
        send_error.assert_not_awaited()
        assert not any(
            call.args[0].get("type", call.args[0].get("t")) == "error"
            for call in send_json.await_args_list
        )
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if consumer == "live":
            await service.cleanup_session(session)
        webchat_queue_mgr.remove_queues(session_id)
