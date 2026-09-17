import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.event import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform import Platform
from astrbot.core.platform.sources.lark import lark_adapter
from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent


@pytest.fixture
def private_chat(monkeypatch):
    """Build a private conversation with mocked storage and IM responses.

    Args:
        monkeypatch: Fixture used to isolate storage and network operations.

    Returns:
        Adapter, inbound event, message API mock, and persistent route storage.
    """
    routes = {}
    preferences = MagicMock()
    preferences.put_async = AsyncMock(
        side_effect=lambda scope, scope_id, key, value: routes.__setitem__(
            (scope, scope_id, key), value
        )
    )
    preferences.get_async = AsyncMock(
        side_effect=lambda scope, scope_id, key, default=None: routes.get(
            (scope, scope_id, key), default
        )
    )
    monkeypatch.setattr(lark_adapter, "sp", preferences)
    monkeypatch.setattr(Platform, "send_by_session", AsyncMock())
    monkeypatch.setattr(
        LarkMessageEvent, "_upload_lark_file", AsyncMock(return_value="file_test")
    )
    create = AsyncMock(
        return_value=SimpleNamespace(success=lambda: True, code=0, msg="success")
    )
    adapter = LarkPlatformAdapter.__new__(LarkPlatformAdapter)
    adapter.config = {"id": "lark-test"}
    adapter.appid = "cli_test"
    adapter.bot_open_id = "ou_bot"
    adapter.bot_name = "Test bot"
    adapter._user_name_cache = {}
    adapter.handle_msg = AsyncMock()
    adapter.lark_api = SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(acreate=create))),
        contact=SimpleNamespace(
            v3=SimpleNamespace(
                user=SimpleNamespace(
                    aget=AsyncMock(
                        return_value=SimpleNamespace(
                            success=lambda: True,
                            data=SimpleNamespace(
                                user=SimpleNamespace(name="Test user")
                            ),
                        )
                    )
                )
            )
        ),
    )
    event = SimpleNamespace(
        event=SimpleNamespace(
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(open_id="ou_test_user"), sender_type="user"
            ),
            message=SimpleNamespace(
                create_time="1700000000000",
                chat_type="p2p",
                chat_id="oc_test_private",
                parent_id=None,
                mentions=None,
                content='{"text":"hello"}',
                message_id="om_test_inbound",
                message_type="text",
            ),
        )
    )
    return adapter, event, create, routes


@pytest.mark.asyncio
async def test_private_file_retries_failed_open_id_with_chat_id(private_chat):
    adapter, event, create, _ = private_chat
    await adapter.convert_msg(event)
    message = adapter.handle_msg.await_args.args[0]
    assert message.session_id == "ou_test_user"
    assert message.sender.user_id == "ou_test_user"
    create.side_effect = [
        SimpleNamespace(
            success=lambda: False,
            code=230101,
            msg="Sending messages to users is temporarily unavailable.",
        ),
        SimpleNamespace(success=lambda: True, code=0, msg="success"),
    ]

    await adapter.send_by_session(
        MessageSession("lark-test", MessageType.FRIEND_MESSAGE, message.session_id),
        MessageChain([Comp.File(file="test.csv", name="test.csv")]),
    )

    assert create.await_count == 2
    first, fallback = [call.args[0] for call in create.await_args_list]
    assert (first.receive_id_type, first.request_body.receive_id) == (
        "open_id",
        "ou_test_user",
    )
    assert (fallback.receive_id_type, fallback.request_body.receive_id) == (
        "chat_id",
        "oc_test_private",
    )
    assert first.request_body.msg_type == fallback.request_body.msg_type == "file"
    assert json.loads(fallback.request_body.content) == {"file_key": "file_test"}
    assert first.request_body.uuid == fallback.request_body.uuid
    LarkMessageEvent._upload_lark_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_successful_open_id_send_does_not_use_fallback(private_chat):
    adapter, event, create, _ = private_chat
    await adapter.convert_msg(event)

    await adapter.send_by_session(
        MessageSession("lark-test", MessageType.FRIEND_MESSAGE, "ou_test_user"),
        MessageChain([Comp.Plain("hello")]),
    )

    create.assert_awaited_once()
    request = create.await_args.args[0]
    assert request.receive_id_type == "open_id"
    assert request.request_body.receive_id == "ou_test_user"


@pytest.mark.asyncio
async def test_mixed_chain_retries_only_failed_file(private_chat):
    adapter, event, create, _ = private_chat
    await adapter.convert_msg(event)
    create.side_effect = [
        SimpleNamespace(success=lambda: True, code=0, msg="success"),
        SimpleNamespace(success=lambda: False, code=230101, msg="Unavailable"),
        SimpleNamespace(success=lambda: True, code=0, msg="success"),
    ]

    await adapter.send_by_session(
        MessageSession("lark-test", MessageType.FRIEND_MESSAGE, "ou_test_user"),
        MessageChain(
            [Comp.Plain("hello"), Comp.File(file="test.csv", name="test.csv")]
        ),
    )

    requests = [call.args[0] for call in create.await_args_list]
    assert [(req.request_body.msg_type, req.receive_id_type) for req in requests] == [
        ("post", "open_id"),
        ("file", "open_id"),
        ("file", "chat_id"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("known_chat", [False, True])
async def test_failed_delivery_is_not_reported_as_success(private_chat, known_chat):
    adapter, event, create, _ = private_chat
    if known_chat:
        await adapter.convert_msg(event)
    create.return_value = SimpleNamespace(
        success=lambda: False, code=230101, msg="Unavailable"
    )

    with pytest.raises(RuntimeError, match="230101"):
        await adapter.send_by_session(
            MessageSession("lark-test", MessageType.FRIEND_MESSAGE, "ou_test_user"),
            MessageChain([Comp.File(file="test.csv", name="test.csv")]),
        )

    assert create.await_count == (2 if known_chat else 1)
    Platform.send_by_session.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", ["oc_group", "ou_test_user%oc_group"])
async def test_group_send_keeps_chat_id_routing(private_chat, session_id):
    adapter, event, create, _ = private_chat
    event.event.message.chat_type = "group"
    event.event.message.chat_id = "oc_group"
    await adapter.convert_msg(event)

    await adapter.send_by_session(
        MessageSession("lark-test", MessageType.GROUP_MESSAGE, session_id),
        MessageChain([Comp.Plain("hello")]),
    )

    create.assert_awaited_once()
    request = create.await_args.args[0]
    assert (request.receive_id_type, request.request_body.receive_id) == (
        "chat_id",
        "oc_group",
    )
    lark_adapter.sp.put_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_transport_timeout_does_not_retry_unknown_delivery(private_chat):
    adapter, event, create, _ = private_chat
    await adapter.convert_msg(event)
    create.side_effect = TimeoutError("Unknown delivery status")

    with pytest.raises(TimeoutError):
        await adapter.send_by_session(
            MessageSession("lark-test", MessageType.FRIEND_MESSAGE, "ou_test_user"),
            MessageChain([Comp.Plain("hello")]),
        )

    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_private_route_survives_adapter_recreation_and_is_scoped(private_chat):
    adapter, event, create, routes = private_chat
    await adapter.convert_msg(event)
    assert routes
    restarted = LarkPlatformAdapter.__new__(LarkPlatformAdapter)
    restarted.config = adapter.config.copy()
    restarted.appid = adapter.appid
    restarted.lark_api = adapter.lark_api
    create.side_effect = [
        SimpleNamespace(success=lambda: False, code=230101, msg="Unavailable"),
        SimpleNamespace(success=lambda: True, code=0, msg="success"),
    ]
    session = MessageSession("lark-test", MessageType.FRIEND_MESSAGE, "ou_test_user")
    await restarted.send_by_session(session, MessageChain([Comp.Plain("hello")]))
    assert create.await_args.args[0].request_body.receive_id == "oc_test_private"

    restarted.config = {"id": "another-bot"}
    restarted.appid = "cli_another_bot"
    create.reset_mock(side_effect=True)
    create.return_value = SimpleNamespace(
        success=lambda: False, code=230101, msg="Unavailable"
    )
    with pytest.raises(RuntimeError, match="230101"):
        await restarted.send_by_session(
            MessageSession("another-bot", MessageType.FRIEND_MESSAGE, "ou_test_user"),
            MessageChain([Comp.Plain("hello")]),
        )
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_file_upload_failure_does_not_report_delivery(private_chat):
    adapter, event, create, _ = private_chat
    await adapter.convert_msg(event)
    LarkMessageEvent._upload_lark_file.return_value = None

    with pytest.raises(RuntimeError, match="upload"):
        await adapter.send_by_session(
            MessageSession("lark-test", MessageType.FRIEND_MESSAGE, "ou_test_user"),
            MessageChain([Comp.File(file="test.csv", name="test.csv")]),
        )

    create.assert_not_awaited()
    Platform.send_by_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_message_does_not_replace_private_route(private_chat):
    adapter, event, create, _ = private_chat
    await adapter.convert_msg(event)
    event.event.message.chat_type = "group"
    event.event.message.chat_id = "oc_group"
    await adapter.convert_msg(event)
    create.side_effect = [
        SimpleNamespace(success=lambda: False, code=230101, msg="Unavailable"),
        SimpleNamespace(success=lambda: True, code=0, msg="success"),
    ]

    await adapter.send_by_session(
        MessageSession("lark-test", MessageType.FRIEND_MESSAGE, "ou_test_user"),
        MessageChain([Comp.Plain("hello")]),
    )

    assert create.await_args.args[0].request_body.receive_id == "oc_test_private"


@pytest.mark.asyncio
async def test_reply_failure_keeps_boolean_result_without_proactive_fallback(
    private_chat,
):
    adapter, _, create, _ = private_chat
    reply = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: False, code=230101, msg="Unavailable"
        )
    )
    adapter.lark_api.im.v1.message.areply = reply

    result = await LarkMessageEvent._send_im_message(
        adapter.lark_api,
        content='{"text":"hello"}',
        msg_type="text",
        reply_message_id="om_inbound",
        receive_id="ou_test_user",
        receive_id_type="open_id",
        fallback_chat_id="oc_test_private",
    )

    assert result is False
    reply.assert_awaited_once()
    create.assert_not_awaited()
