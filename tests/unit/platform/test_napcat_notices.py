from __future__ import annotations

import pytest

from tests.unit.platform.napcat_adapter_support import *  # noqa: F403

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_napcat_private_notice_events_do_not_auto_wake_pipeline(monkeypatch):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "bot_offline",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 123456,
            "tag": "gateway_disconnect",
            "message": "socket closed by remote peer",
        }
    )

    await adapter.handle_forward_ws_event(event)
    queued = queue.get_nowait()

    stage = WakingCheckStage()
    catalogs = RuntimeCatalogs()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "wake_prefix": ["/"],
                "platform_settings": {
                    "no_permission_reply": True,
                    "friend_message_needs_wake_prefix": False,
                    "ignore_bot_self_message": False,
                    "ignore_at_all": False,
                    "unique_session": False,
                    "group_wake_policy": {
                        "mention_bot": True,
                        "reply_to_bot": True,
                    },
                },
                "plugin_set": ["*"],
            },
            astrbot_config_id="default",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: CommandCatalogStore(),
            ),
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
            handlers=catalogs.handlers,
            plugins=catalogs.plugins,
        )
    )

    await stage.process(queued)

    assert queued.is_private_chat() is True
    assert queued.is_at_or_wake_command is False
    assert queued.is_wake is False


@pytest.mark.asyncio
async def test_napcat_notice_poke_event_is_queued_as_group_message():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "poke",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "target_id": 123456,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert (
        queued.get_message_str()
        == "[notice:notify:poke] user 111222 target 123456 group 654321"
    )
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert queued.get_extra("platform_event") == "napcat"
    assert queued.get_extra("onebot_post_type") == "notice"
    assert queued.get_extra("onebot_notice_type") == "notify"
    assert queued.get_extra("onebot_sub_type") == "poke"
    assert queued.get_extra("napcat_self_id") == 123456
    assert queued.get_extra("napcat_user_id") == 111222
    assert queued.get_extra("napcat_group_id") == 654321
    assert queued.get_extra("napcat_target_id") == 123456
    assert queued.get_extra("napcat_time") == 1720000000
    assert queued.is_notice_type("notify", sub_type="poke")
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "poke",
        "user_id": 111222,
        "group_id": 654321,
        "target_id": 123456,
    }
    assert (
        queued.get_extra("napcat_event").items()
        >= {
            "group_id": 654321,
            "notice_type": "notify",
            "post_type": "notice",
            "self_id": 123456,
            "sub_type": "poke",
            "target_id": 123456,
            "time": 1720000000,
            "user_id": 111222,
        }.items()
    )
    assert len(queued.get_messages()) == 1
    assert isinstance(queued.get_messages()[0], Poke)
    assert str(queued.get_messages()[0].id) == "123456"


@pytest.mark.asyncio
async def test_napcat_group_notice_keeps_group_session_when_unique_session_enabled(
    monkeypatch,
):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_recall",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "operator_id": 333444,
            "message_id": 777888,
        }
    )

    await adapter.handle_forward_ws_event(event)
    queued = queue.get_nowait()

    stage = WakingCheckStage()
    catalogs = RuntimeCatalogs()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "wake_prefix": ["/"],
                "platform_settings": {
                    "no_permission_reply": True,
                    "friend_message_needs_wake_prefix": False,
                    "ignore_bot_self_message": False,
                    "ignore_at_all": False,
                    "unique_session": True,
                },
                "plugin_set": ["*"],
            },
            astrbot_config_id="default",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: CommandCatalogStore(),
            ),
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
            handlers=catalogs.handlers,
            plugins=catalogs.plugins,
        )
    )

    await stage.process(queued)

    assert queued.session.session_id == "654321"


@pytest.mark.asyncio
async def test_napcat_group_message_route_identity_keeps_original_group_target_after_unique_session(
    monkeypatch,
):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    queued = _make_manual_event(
        adapter,
        sender_id="111222",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
        message=[Plain("hello")],
    )
    queued.message_str = "hello"

    stage = WakingCheckStage()
    catalogs = RuntimeCatalogs()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "wake_prefix": ["/"],
                "platform_settings": {
                    "no_permission_reply": True,
                    "friend_message_needs_wake_prefix": False,
                    "ignore_bot_self_message": False,
                    "ignore_at_all": False,
                    "unique_session": True,
                },
                "plugin_set": ["*"],
            },
            astrbot_config_id="default",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: CommandCatalogStore(),
            ),
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
            handlers=catalogs.handlers,
            plugins=catalogs.plugins,
        )
    )

    assert queued.route_origin == "napcat-test:GroupMessage:654321"

    await stage.process(queued)

    assert queued.session.session_id == "111222_654321"
    assert queued.route_identity.target_id == "654321"
    assert queued.route_origin == "napcat-test:GroupMessage:654321"


@pytest.mark.asyncio
async def test_napcat_reply_only_wake_resolves_sender_lazily_in_waking_stage(
    monkeypatch,
):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock(
        return_value=NapCatFetchedMessage(message_id=9001, sender_id=123456)
    )
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 781,
            "font": 14,
            "raw_message": "[CQ:reply,id=9001] hello",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "reply", "data": {"id": "9001"}},
                {"type": "text", "data": {"text": " hello"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)
    queued = queue.get_nowait()
    reply = queued.get_messages()[0]
    assert reply.sender_id == 0
    adapter.client.get_message.assert_not_awaited()

    stage = WakingCheckStage()
    catalogs = RuntimeCatalogs()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "wake_prefix": ["/"],
                "platform_settings": {
                    "no_permission_reply": True,
                    "friend_message_needs_wake_prefix": False,
                    "ignore_bot_self_message": False,
                    "ignore_at_all": False,
                    "unique_session": False,
                    "group_wake_policy": {
                        "mention_bot": True,
                        "reply_to_bot": True,
                    },
                },
                "plugin_set": ["*"],
            },
            astrbot_config_id="default",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: CommandCatalogStore(),
            ),
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
            handlers=catalogs.handlers,
            plugins=catalogs.plugins,
        )
    )

    await stage.process(queued)

    assert queued.is_wake is True
    assert queued.is_at_or_wake_command is True
    assert reply.sender_id == "123456"
    adapter.client.get_message.assert_awaited_once_with("9001")


@pytest.mark.asyncio
async def test_napcat_event_send_uses_route_identity_after_unique_session_mutation():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.send_group_message = AsyncMock()
    event = _make_manual_event(
        adapter,
        sender_id="111222",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
    )
    event.session_id = "111222_654321"

    await event.send(MessageChain([Plain("reply")]))

    adapter.client.send_group_message.assert_awaited_once()
    call = adapter.client.send_group_message.await_args.kwargs
    assert call["group_id"] == "654321"
    assert event.route_identity.target_id == "654321"
    assert event.session.session_id == "111222_654321"


@pytest.mark.asyncio
async def test_napcat_forward_ws_accepts_private_poke_payload_with_sender_id_and_raw_info():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "poke",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 445566,
            "sender_id": 123456,
            "target_id": 445566,
            "raw_info": [{"uid": "u_1"}, {"uid": "u_2"}],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.get_sender_id() == "123456"
    assert queued.session.session_id == "445566"
    assert queued.get_extra("napcat_sender_id") == 123456
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "poke",
        "user_id": 445566,
        "sender_id": 123456,
        "target_id": 445566,
    }
    assert (
        queued.get_extra("napcat_event").items()
        >= {
            "notice_type": "notify",
            "post_type": "notice",
            "raw_info": [{"uid": "u_1"}, {"uid": "u_2"}],
            "self_id": 123456,
            "sender_id": 123456,
            "sub_type": "poke",
            "target_id": 445566,
            "time": 1720000000,
            "user_id": 445566,
        }.items()
    )


@pytest.mark.asyncio
async def test_napcat_forward_ws_ignores_ephemeral_input_status_notice():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "input_status",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 3013138453,
            "group_id": 0,
            "event_type": 1,
            "status_text": "对方正在输入...",
        }
    )

    await adapter.handle_forward_ws_event(event)

    assert queue.empty()


@pytest.mark.asyncio
async def test_napcat_private_event_typing_helpers_use_input_status():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_input_status = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(adapter, sender_id="445566")

    await event.send_typing()
    adapter.client.set_input_status.assert_awaited_once_with(
        user_id="445566",
        event_type=1,
    )

    adapter.client.set_input_status.reset_mock()
    await event.stop_typing()
    adapter.client.set_input_status.assert_awaited_once_with(
        user_id="445566",
        event_type=2,
    )


@pytest.mark.asyncio
async def test_napcat_group_event_typing_helpers_are_noops():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_input_status = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="445566",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
    )

    await event.send_typing()
    await event.stop_typing()

    adapter.client.set_input_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_group_history_fetches_recent_messages():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.call_action = AsyncMock(
        side_effect=[
            {
                "status": "ok",
                "retcode": 0,
                "messages": [
                    {"message_id": 100, "raw_message": "m100"},
                    {"message_id": 101, "raw_message": "m101"},
                ],
            },
            {
                "status": "ok",
                "retcode": 0,
                "messages": [
                    {"message_id": 101, "raw_message": "m101"},
                ],
            },
            {
                "status": "ok",
                "retcode": 0,
                "messages": [
                    {"message_id": 99, "raw_message": "m99"},
                    {"message_id": 98, "raw_message": "m98"},
                    {"message_id": 100, "raw_message": "m100"},
                ],
            },
        ]
    )

    history = await adapter.client.get_group_msg_history(group_id="654321", count=4)

    assert [item["message_id"] for item in history] == [98, 99, 100, 101]
    assert adapter.client.call_action.await_count == 3


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_friend_history_honors_explicit_message_seq():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.call_action = AsyncMock(
        return_value={
            "status": "ok",
            "retcode": 0,
            "messages": [
                {"message_id": 501, "raw_message": "m501"},
                {"message_id": 502, "raw_message": "m502"},
            ],
        }
    )

    history = await adapter.client.get_friend_msg_history(
        user_id="445566",
        count=2,
        message_seq=500,
    )

    assert [item["message_id"] for item in history] == [501, 502]
    adapter.client.call_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_ai_actions_match_napcat_payload_schema():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.call_action = AsyncMock(
        side_effect=[
            {
                "status": "ok",
                "retcode": 0,
                "data": [{"type": "default", "characters": []}],
            },
            {
                "status": "ok",
                "retcode": 0,
                "data": {"message_id": 0},
            },
        ]
    )

    characters = await adapter.client.get_ai_characters(group_id="654321", chat_type=2)
    assert characters == [{"type": "default", "characters": []}]

    await adapter.client.send_group_ai_record(
        group_id="654321",
        character="voice-1",
        text="你好",
        chat_type=2,
        timeout_seconds=30,
    )

    assert adapter.client.call_action.await_args_list[0].args == ("get_ai_characters",)
    assert adapter.client.call_action.await_args_list[0].kwargs == {
        "group_id": "654321",
        "chat_type": 2,
    }
    assert adapter.client.call_action.await_args_list[1].args == (
        "send_group_ai_record",
    )
    assert adapter.client.call_action.await_args_list[1].kwargs == {
        "group_id": "654321",
        "character": "voice-1",
        "text": "你好",
    }


@pytest.mark.asyncio
async def test_napcat_notify_group_name_event_is_queued_with_notify_info():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "group_name",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "name_new": "NapCat New Name",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert (
        queued.get_message_str()
        == "[notice:notify:group_name] user 111222 group 654321 name NapCat New Name"
    )
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "group_name",
        "user_id": 111222,
        "group_id": 654321,
        "name_new": "NapCat New Name",
    }


@pytest.mark.asyncio
async def test_napcat_notify_profile_like_event_is_queued_with_notify_info():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "profile_like",
            "time": 1720000000,
            "self_id": 123456,
            "operator_id": 111222,
            "operator_nick": "tester",
            "times": 3,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.get_sender_id() == "111222"
    assert queued.session.session_id == "111222"
    assert (
        queued.get_message_str()
        == "[notice:notify:profile_like] operator 111222 operator_nick tester times 3"
    )
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "profile_like",
        "operator_id": 111222,
        "operator_nick": "tester",
        "times": 3,
    }


@pytest.mark.asyncio
async def test_napcat_notify_group_title_event_is_queued_with_notify_info():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "title",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "title": "NapCat Title",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert (
        queued.get_message_str()
        == "[notice:notify:title] user 111222 group 654321 title NapCat Title"
    )
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "title",
        "user_id": 111222,
        "group_id": 654321,
        "title": "NapCat Title",
    }


@pytest.mark.asyncio
async def test_napcat_notify_gray_tip_event_is_queued_with_notify_info():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "gray_tip",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 777888,
            "busi_id": "tip-1",
            "content": "gray tip content",
            "raw_info": {"kind": "gray-tip"},
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert (
        queued.get_message_str()
        == "[notice:notify:gray_tip] user 111222 message 777888 group 654321 busi tip-1 content gray tip content"
    )
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "gray_tip",
        "user_id": 111222,
        "group_id": 654321,
        "busi_id": "tip-1",
        "content": "gray tip content",
    }


@pytest.mark.asyncio
async def test_napcat_online_file_send_notice_uses_peer_id_for_friend_session():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "online_file_send",
            "sub_type": "receive",
            "time": 1720000000,
            "self_id": 123456,
            "peer_id": 445566,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.get_sender_id() == "445566"
    assert queued.session.session_id == "445566"
    assert queued.get_message_str() == "[notice:online_file_send:receive] peer 445566"
    assert queued.get_extra("napcat_peer_id") == 445566


@pytest.mark.asyncio
async def test_napcat_online_file_notice_actions_use_peer_id_without_sender_id():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_online_file_messages = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {"items": []}}
    )
    adapter.client.receive_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="",
        message=[
            OnlineFile(
                msg_id="msg-1",
                element_id="element-1",
                file_name="demo.zip",
                file_size="1024",
                is_dir=False,
            )
        ],
    )
    event.set_extra("napcat_peer_id", "445566")

    await event.get_online_file_messages()
    adapter.client.get_online_file_messages.assert_awaited_once_with(user_id="445566")

    await event.receive_online_file()
    adapter.client.receive_online_file.assert_awaited_once_with(
        user_id="445566",
        msg_id="msg-1",
        element_id="element-1",
    )


@pytest.mark.asyncio
async def test_napcat_group_recall_notice_exposes_recall_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_recall",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "operator_id": 333444,
            "message_id": 777888,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_recall")
    assert queued.get_recall_info() == {
        "notice_type": "group_recall",
        "message_id": 777888,
        "user_id": 111222,
        "group_id": 654321,
        "operator_id": 333444,
    }


@pytest.mark.asyncio
async def test_napcat_group_upload_notice_exposes_upload_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_upload",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "file": {
                "id": "file-id",
                "name": "demo.zip",
                "size": 2048,
                "busid": 102,
            },
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_upload")
    assert queued.get_message_str() == (
        "[notice:group_upload] user 111222 group 654321 file demo.zip "
        "file_id file-id file_size 2048 busid 102"
    )
    assert queued.get_upload_info() == {
        "notice_type": "group_upload",
        "group_id": 654321,
        "user_id": 111222,
        "file": {
            "id": "file-id",
            "name": "demo.zip",
            "size": 2048,
            "busid": 102,
        },
    }


@pytest.mark.asyncio
async def test_napcat_group_request_accepts_nonstandard_sub_type_strings():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "request",
            "request_type": "group",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "sub_type": "join_request",
            "comment": "please approve",
            "flag": "flag-1",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_request_info() == {
        "request_type": "group",
        "sub_type": "join_request",
        "user_id": 111222,
        "flag": "flag-1",
        "comment": "please approve",
        "group_id": 654321,
    }


@pytest.mark.asyncio
async def test_napcat_group_reaction_notice_exposes_reaction_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_msg_emoji_like",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 777,
            "is_add": True,
            "likes": [
                {"emoji_id": 128077, "count": 2},
                {"emoji_id": 128293, "count": 1},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == (
        "[notice:group_msg_emoji_like] user 111222 message 777 group 654321 "
        "likes 128077=2,128293=1 action add"
    )
    assert queued.get_reaction_info() == {
        "notice_type": "group_msg_emoji_like",
        "group_id": 654321,
        "message_id": 777,
        "user_id": 111222,
        "is_add": True,
        "likes": [
            {"emoji_id": 128077, "count": 2},
            {"emoji_id": 128293, "count": 1},
        ],
    }


@pytest.mark.asyncio
async def test_napcat_lagrange_reaction_notice_exposes_reaction_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "reaction",
            "sub_type": "add",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "operator_id": 111222,
            "message_id": 777,
            "code": "128077",
            "count": 3,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_reaction_info() == {
        "notice_type": "reaction",
        "group_id": 654321,
        "message_id": 777,
        "operator_id": 111222,
        "code": "128077",
        "count": 3,
        "sub_type": "add",
    }


@pytest.mark.asyncio
async def test_napcat_group_admin_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_admin",
            "sub_type": "set",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_admin", sub_type="set")
    assert queued.get_group_admin_info() == {
        "notice_type": "group_admin",
        "sub_type": "set",
        "group_id": 654321,
        "user_id": 111222,
    }


@pytest.mark.asyncio
async def test_napcat_group_ban_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_ban",
            "sub_type": "ban",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "operator_id": 333444,
            "duration": 600,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_ban", sub_type="ban")
    assert queued.get_group_ban_info() == {
        "notice_type": "group_ban",
        "sub_type": "ban",
        "group_id": 654321,
        "user_id": 111222,
        "operator_id": 333444,
        "duration": 600,
    }


@pytest.mark.asyncio
async def test_napcat_group_card_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_card",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "card_old": "old-card",
            "card_new": "new-card",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_card")
    assert queued.get_group_card_info() == {
        "notice_type": "group_card",
        "group_id": 654321,
        "user_id": 111222,
        "card_old": "old-card",
        "card_new": "new-card",
    }


@pytest.mark.asyncio
async def test_napcat_group_increase_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_increase",
            "sub_type": "invite",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "operator_id": 333444,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_increase", sub_type="invite")
    assert queued.get_group_increase_info() == {
        "notice_type": "group_increase",
        "sub_type": "invite",
        "group_id": 654321,
        "user_id": 111222,
        "operator_id": 333444,
    }


@pytest.mark.asyncio
async def test_napcat_group_decrease_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_decrease",
            "sub_type": "kick",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "operator_id": 333444,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_decrease", sub_type="kick")
    assert queued.get_group_decrease_info() == {
        "notice_type": "group_decrease",
        "sub_type": "kick",
        "group_id": 654321,
        "user_id": 111222,
        "operator_id": 333444,
    }


@pytest.mark.asyncio
async def test_napcat_group_essence_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "essence",
            "sub_type": "add",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "message_id": 777888,
            "operator_id": 333444,
            "sender_id": 111222,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("essence", sub_type="add")
    assert queued.get_group_essence_info() == {
        "notice_type": "essence",
        "sub_type": "add",
        "group_id": 654321,
        "message_id": 777888,
        "operator_id": 333444,
        "sender_id": 111222,
    }


@pytest.mark.asyncio
async def test_napcat_group_request_event_is_queued_with_group_session():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_group_add_request = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "request",
            "request_type": "group",
            "sub_type": "add",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "comment": "let me in",
            "flag": "request-flag",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert (
        queued.get_message_str()
        == "[request:group:add] user 111222 group 654321 comment let me in "
        "flag request-flag"
    )
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert queued.get_sender_id() == "111222"
    assert queued.get_extra("onebot_post_type") == "request"
    assert queued.get_extra("onebot_request_type") == "group"
    assert queued.get_extra("onebot_sub_type") == "add"
    assert queued.get_extra("napcat_self_id") == 123456
    assert queued.get_extra("napcat_user_id") == 111222
    assert queued.get_extra("napcat_group_id") == 654321
    assert queued.get_extra("napcat_comment") == "let me in"
    assert queued.get_extra("napcat_flag") == "request-flag"
    assert queued.get_extra("napcat_time") == 1720000000
    assert queued.get_request_info() == {
        "request_type": "group",
        "sub_type": "add",
        "user_id": 111222,
        "flag": "request-flag",
        "comment": "let me in",
        "group_id": 654321,
    }
    assert queued.get_extra("napcat_event") == {
        "comment": "let me in",
        "flag": "request-flag",
        "group_id": 654321,
        "post_type": "request",
        "request_type": "group",
        "self_id": 123456,
        "sub_type": "add",
        "time": 1720000000,
        "user_id": 111222,
    }
    assert queued.get_messages() == []
    await queued.approve_request()
    adapter.client.set_group_add_request.assert_awaited_with(
        flag="request-flag",
        approve=True,
        reason=None,
    )
    await queued.reject_request(reason="denied")
    adapter.client.set_group_add_request.assert_awaited_with(
        flag="request-flag",
        approve=False,
        reason="denied",
    )


@pytest.mark.asyncio
async def test_napcat_friend_request_event_can_be_approved_or_rejected():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_friend_add_request = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "request",
            "request_type": "friend",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 111222,
            "comment": "hello",
            "flag": "friend-request-flag",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.get_message_str() == (
        "[request:friend] user 111222 comment hello flag friend-request-flag"
    )
    assert queued.get_request_info() == {
        "request_type": "friend",
        "user_id": 111222,
        "flag": "friend-request-flag",
        "comment": "hello",
    }
    await queued.approve_request(remark="new-friend")
    adapter.client.set_friend_add_request.assert_awaited_with(
        flag="friend-request-flag",
        approve=True,
        remark="new-friend",
    )
    await queued.reject_request()
    adapter.client.set_friend_add_request.assert_awaited_with(
        flag="friend-request-flag",
        approve=False,
        remark=None,
    )
