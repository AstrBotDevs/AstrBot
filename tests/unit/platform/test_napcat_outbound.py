from __future__ import annotations

import pytest

from tests.unit.platform.napcat_adapter_support import *  # noqa: F403

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_record_video_and_file_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                Record(file="https://example.com/demo.wav"),
                Video(file="https://example.com/demo.mp4", cover="thumb://cover"),
                File(name="demo.txt", url="https://example.com/demo.txt"),
            ]
        )
    )

    assert isinstance(payload, list)
    assert [segment.to_dict()["type"] for segment in payload] == [
        "record",
        "video",
        "file",
    ]
    assert payload[0].to_dict()["data"]["file"] == "https://example.com/demo.wav"
    assert payload[1].to_dict()["data"]["thumb"] == "thumb://cover"
    assert payload[2].to_dict()["data"]["name"] == "demo.txt"


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_face_contact_location_poke_and_json():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                Face(id=123),
                Contact(_type="qq", id=456789),
                Location(
                    lat=31.2304,
                    lon=121.4737,
                    title="Shanghai",
                    content="The Bund",
                ),
                Poke(id=10001, poke_type="2000"),
                Json(data={"app": "com.tencent.test", "desc": "demo"}),
            ]
        )
    )

    assert isinstance(payload, list)
    assert [segment.to_dict()["type"] for segment in payload] == [
        "face",
        "contact",
        "location",
        "poke",
        "json",
    ]
    assert payload[0].to_dict()["data"]["id"] == "123"
    assert payload[1].to_dict()["data"] == {"type": "qq", "id": "456789"}
    assert payload[2].to_dict()["data"]["title"] == "Shanghai"
    assert payload[3].to_dict()["data"] == {"type": "2000", "id": "10001"}
    assert payload[4].to_dict()["data"]["data"] == {
        "app": "com.tencent.test",
        "desc": "demo",
    }


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_mface_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                MFace(
                    emoji_package_id=1152,
                    emoji_id="987654321",
                    key="market-face-key",
                    summary="[HappyFace]",
                )
            ]
        )
    )

    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0].to_dict() == {
        "type": "mface",
        "data": {
            "emoji_package_id": 1152.0,
            "emoji_id": "987654321",
            "key": "market-face-key",
            "summary": "[HappyFace]",
        },
    }


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_id_and_custom_music():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                Music(_type="qq", id=12345),
                Music(
                    _type="custom",
                    url="https://example.com/page",
                    audio="https://example.com/audio.mp3",
                    title="Custom Song",
                    image="https://example.com/cover.jpg",
                    content="Custom intro",
                ),
            ]
        )
    )

    assert isinstance(payload, list)
    assert [segment.to_dict()["type"] for segment in payload] == ["music", "music"]
    assert payload[0].to_dict()["data"] == {"type": "qq", "id": "12345"}
    assert payload[1].to_dict()["data"] == {
        "type": "custom",
        "id": None,
        "url": "https://example.com/page",
        "image": "https://example.com/cover.jpg",
        "audio": "https://example.com/audio.mp3",
        "title": "Custom Song",
        "content": "Custom intro",
    }


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_share_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                Share(
                    url="https://example.com/article",
                    title="Example Article",
                    content="A short summary",
                    image="https://example.com/cover.png",
                )
            ]
        )
    )

    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0].to_dict() == {
        "type": "share",
        "data": {
            "url": "https://example.com/article",
            "title": "Example Article",
            "content": "A short summary",
            "image": "https://example.com/cover.png",
        },
    }


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_dice_rps_and_shake():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain([Dice(), RPS(), Shake()])
    )

    assert isinstance(payload, list)
    assert [segment.to_dict() for segment in payload] == [
        {"type": "dice", "data": {}},
        {"type": "rps", "data": {}},
        {"type": "shake", "data": {}},
    ]


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_xml_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain([Xml(data="<msg template='123'>demo</msg>")])
    )

    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0].to_dict() == {
        "type": "xml",
        "data": {"data": "<msg template='123'>demo</msg>"},
    }


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_markdown_and_miniapp_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                Markdown(content="# Demo\ncontent"),
                MiniApp(data='{"app":"demo","page":"/index"}'),
            ]
        )
    )

    assert isinstance(payload, list)
    assert [segment.to_dict()["type"] for segment in payload] == [
        "markdown",
        "miniapp",
    ]
    assert payload[0].to_dict()["data"] == {"content": "# Demo\ncontent"}
    assert payload[1].to_dict()["data"] == {"data": '{"app":"demo","page":"/index"}'}


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_onlinefile_and_flashtransfer():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                OnlineFile(
                    msg_id="msg-1",
                    element_id="element-1",
                    file_name="demo.zip",
                    file_size="1024",
                    is_dir=False,
                ),
                FlashTransfer(file_set_id="flash-set-1"),
            ]
        )
    )

    assert isinstance(payload, list)
    assert [segment.to_dict()["type"] for segment in payload] == [
        "onlinefile",
        "flashtransfer",
    ]
    assert payload[0].to_dict()["data"] == {
        "msgId": "msg-1",
        "elementId": "element-1",
        "fileName": "demo.zip",
        "fileSize": "1024",
        "isDir": False,
    }
    assert payload[1].to_dict()["data"] == {"fileSetId": "flash-set-1"}


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_forward_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain([Forward(id="forward-res-id")])
    )

    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0].to_dict() == {
        "type": "forward",
        "data": {"id": "forward-res-id"},
    }


@pytest.mark.asyncio
async def test_napcat_send_by_session_supports_forward_nodes():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.send_group_message = AsyncMock()
    adapter.client.send_group_forward_message = AsyncMock()
    session = MessageSession(
        platform_name="napcat-test",
        message_type=MessageType.GROUP_MESSAGE,
        session_id="654321",
    )

    await adapter.send_by_session(
        session,
        MessageChain(
            [
                Plain("before"),
                Nodes(
                    [
                        Node(
                            uin="1001",
                            name="alice",
                            content=[Plain("first node")],
                        ),
                        Node(
                            uin="1002",
                            name="bob",
                            content=[Plain("second node")],
                        ),
                    ]
                ),
                Plain("after"),
            ]
        ),
    )

    assert adapter.client.send_group_message.await_count == 2
    first_standard = adapter.client.send_group_message.await_args_list[0].kwargs
    second_standard = adapter.client.send_group_message.await_args_list[1].kwargs
    assert first_standard["group_id"] == "654321"
    assert second_standard["group_id"] == "654321"
    assert [
        segment.to_dict()["data"]["text"] for segment in first_standard["message"]
    ] == ["before"]
    assert [
        segment.to_dict()["data"]["text"] for segment in second_standard["message"]
    ] == ["after"]

    adapter.client.send_group_forward_message.assert_awaited_once()
    forward_call = adapter.client.send_group_forward_message.await_args.kwargs
    assert forward_call["group_id"] == "654321"
    assert len(forward_call["messages"]) == 2
    assert forward_call["messages"][0]["type"] == "node"
    assert forward_call["messages"][0]["data"]["nickname"] == "alice"
    assert (
        forward_call["messages"][0]["data"]["content"][0]["data"]["text"]
        == "first node"
    )
    assert forward_call["messages"][1]["data"]["nickname"] == "bob"


@pytest.mark.asyncio
async def test_napcat_get_group_returns_group_details():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock(
        return_value=NapCatFetchedMessage(message_id=9001)
    )
    adapter.client.get_group_info = AsyncMock(
        return_value=SimpleNamespace(
            group_id=654321.0,
            group_name="NapCat Group",
        )
    )
    adapter.client.get_group_member_list = AsyncMock(
        return_value=[
            SimpleNamespace(
                user_id=1.0,
                nickname="owner-nick",
                card="owner-card",
                role="owner",
            ),
            SimpleNamespace(
                user_id=2.0,
                nickname="admin-nick",
                card="",
                role="admin",
            ),
            SimpleNamespace(
                user_id=3.0,
                nickname="member-nick",
                card="member-card",
                role="member",
            ),
        ]
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
            "message_id": 777,
            "font": 14,
            "raw_message": "hello",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "admin",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    group = await queued.get_group()
    assert group is not None
    assert group.group_id == "654321"
    assert group.group_name == "NapCat Group"
    assert group.member_count == 3
    assert group.group_owner == "1"
    assert group.group_admins == ["2"]
    assert [member.user_id for member in group.members] == ["1", "2", "3"]
    assert [member.nickname for member in group.members] == [
        "owner-card",
        "admin-nick",
        "member-card",
    ]


@pytest.mark.asyncio
async def test_napcat_get_group_returns_none_without_group_context():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")

    assert await event.get_group() is None


@pytest.mark.asyncio
async def test_napcat_get_group_supports_explicit_group_id_no_cache_and_mapping_data():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_group_info = AsyncMock(
        return_value={"group_id": "777888", "group_name": "Mapped Group"}
    )
    adapter.client.get_group_member_list = AsyncMock(
        return_value=[
            {"user_id": 11, "nickname": "owner-nick", "card": "", "role": "owner"},
            {"user_id": 12, "nickname": "admin-nick", "role": "admin"},
            {"user_id": 13, "card": "member-card", "role": "member"},
            {"user_id": None, "nickname": "ignored"},
        ]
    )
    event = _make_manual_event(adapter, sender_id="445566")

    group = await event.get_group(group_id="777888", no_cache=True)

    adapter.client.get_group_info.assert_awaited_once_with(group_id="777888")
    adapter.client.get_group_member_list.assert_awaited_once_with(
        "777888",
        no_cache=True,
    )
    assert group is not None
    assert group.group_id == "777888"
    assert group.group_name == "Mapped Group"
    assert group.group_owner == "11"
    assert group.group_admins == ["12"]
    assert [member.user_id for member in group.members] == ["11", "12", "13"]
    assert [member.nickname for member in group.members] == [
        "owner-nick",
        "admin-nick",
        "member-card",
    ]


@pytest.mark.asyncio
async def test_napcat_event_get_forward_msg_resolves_component_or_returns_none():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_forward_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {"messages": []}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="445566",
        message=[Forward(id="forward-123")],
    )

    payload = await event.get_forward_msg()
    assert payload["data"] == {"messages": []}
    adapter.client.get_forward_message.assert_awaited_once_with("forward-123")

    adapter.client.get_forward_message.reset_mock()
    explicit_payload = await event.get_forward_msg(" forward-456 ")
    assert explicit_payload["status"] == "ok"
    adapter.client.get_forward_message.assert_awaited_once_with("forward-456")

    empty_event = _make_manual_event(adapter, sender_id="445566", message=[])
    assert await empty_event.get_forward_msg() is None


def test_napcat_event_notice_and_request_helpers_return_none_when_unrelated():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")

    assert event.get_notify_info() is None
    assert event.get_group_admin_info() is None
    assert event.get_group_ban_info() is None
    assert event.get_group_card_info() is None
    assert event.get_group_increase_info() is None
    assert event.get_group_decrease_info() is None
    assert event.get_group_essence_info() is None
    assert event.get_request_info() is None


def test_napcat_event_notice_and_request_helpers_omit_optional_fields_when_missing():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    notify_event = _make_manual_event(adapter, sender_id="445566")
    notify_event.set_extra("onebot_post_type", "notice")
    notify_event.set_extra("onebot_notice_type", "notify")
    notify_event.set_extra("onebot_sub_type", "poke")
    notify_event.set_extra("napcat_user_id", "445566")
    assert notify_event.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "poke",
        "user_id": "445566",
    }

    request_event = _make_manual_event(adapter, sender_id="445566")
    request_event.set_extra("onebot_post_type", "request")
    request_event.set_extra("onebot_request_type", "friend")
    request_event.set_extra("onebot_sub_type", "add")
    request_event.set_extra("napcat_user_id", "445566")
    request_event.set_extra("napcat_flag", "flag-1")
    assert request_event.get_request_info() == {
        "request_type": "friend",
        "sub_type": "add",
        "user_id": "445566",
        "flag": "flag-1",
    }

    essence_event = _make_manual_event(adapter, sender_id="445566")
    essence_event.message_obj.raw_message = SimpleNamespace()
    essence_event.set_extra("onebot_post_type", "notice")
    essence_event.set_extra("onebot_notice_type", "essence")
    essence_event.set_extra("onebot_sub_type", "add")
    essence_event.set_extra("napcat_group_id", "654321")
    essence_event.set_extra("napcat_message_id", "9001")
    essence_event.set_extra("napcat_operator_id", "10001")
    assert essence_event.get_group_essence_info() == {
        "notice_type": "essence",
        "sub_type": "add",
        "group_id": "654321",
        "message_id": "9001",
        "operator_id": "10001",
    }


@pytest.mark.asyncio
async def test_napcat_event_delete_validates_message_event_and_message_id():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.delete_message = AsyncMock()

    notice_event = _make_manual_event(adapter, sender_id="445566")
    notice_event.set_extra("onebot_post_type", "notice")
    with pytest.raises(ValueError, match="delete\\(\\) is only available"):
        await notice_event.delete()

    missing_id_event = _make_manual_event(adapter, sender_id="445566")
    missing_id_event.set_extra("onebot_post_type", "message")
    missing_id_event.message_obj.message_id = ""
    with pytest.raises(
        ValueError, match="current NapCat event does not contain a message_id"
    ):
        await missing_id_event.delete()


@pytest.mark.asyncio
async def test_napcat_event_send_streaming_batches_without_fallback():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")
    event.send = AsyncMock()

    async def _generator():
        yield MessageChain([Plain("hello")])
        yield MessageChain([Plain(" world"), Face(id="123")])

    result = await event.send_streaming(_generator())

    assert isinstance(result, PlatformSendResult)
    assert result.status == "unknown"
    assert result.success is False
    event.send.assert_awaited_once()
    sent_chain = event.send.await_args.args[0]
    assert isinstance(sent_chain, MessageChain)
    assert [type(component).__name__ for component in sent_chain.chain] == [
        "Plain",
        "Face",
    ]
    assert sent_chain.chain[0].text == "hello world"
    assert sent_chain.chain[1].id == 123
    assert event._has_send_oper is True


@pytest.mark.asyncio
async def test_napcat_event_send_streaming_fallback_sends_components_incrementally(
    monkeypatch: pytest.MonkeyPatch,
):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")
    event.send = AsyncMock()
    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "astrbot.core.platform.sources.napcat.message_event.asyncio.sleep", sleep_mock
    )

    async def _generator():
        yield MessageChain([Plain("hello "), Face(id="1")])
        yield "ignored"
        yield MessageChain([Plain("world"), Face(id="2")])

    result = await event.send_streaming(_generator(), use_fallback=True)

    assert isinstance(result, PlatformSendResult)
    assert result.status == "unknown"
    assert result.success is False
    assert event.send.await_count == 3
    first_chain = event.send.await_args_list[0].args[0]
    second_chain = event.send.await_args_list[1].args[0]
    third_chain = event.send.await_args_list[2].args[0]
    assert [type(component).__name__ for component in first_chain.chain] == ["Face"]
    assert [type(component).__name__ for component in second_chain.chain] == ["Face"]
    assert [type(component).__name__ for component in third_chain.chain] == ["Plain"]
    assert first_chain.chain[0].id == 1
    assert second_chain.chain[0].id == 2
    assert third_chain.chain[0].text == "hello world"
    assert sleep_mock.await_count == 2
    assert event._has_send_oper is True


@pytest.mark.asyncio
async def test_napcat_event_send_streaming_ignores_empty_non_fallback_stream():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")
    event.send = AsyncMock()

    async def _generator():
        if False:
            yield MessageChain([])

    result = await event.send_streaming(_generator())

    assert result is None
    event.send.assert_not_called()


@pytest.mark.asyncio
async def test_napcat_event_send_streaming_ignores_empty_fallback_stream():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")
    event.send = AsyncMock()

    async def _generator():
        if False:
            yield MessageChain([])

    result = await event.send_streaming(_generator(), use_fallback=True)

    assert result is None
    event.send.assert_not_called()
    assert event._has_send_oper is False


@pytest.mark.asyncio
async def test_napcat_event_online_file_actions_resolve_current_component():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_online_file_messages = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {"items": []}}
    )
    adapter.client.receive_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.refuse_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.cancel_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="445566",
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

    payload = await event.get_online_file_messages()
    assert payload["status"] == "ok"
    adapter.client.get_online_file_messages.assert_awaited_once_with(user_id="445566")

    await event.receive_online_file()
    adapter.client.receive_online_file.assert_awaited_once_with(
        user_id="445566",
        msg_id="msg-1",
        element_id="element-1",
    )

    await event.refuse_online_file()
    adapter.client.refuse_online_file.assert_awaited_once_with(
        user_id="445566",
        msg_id="msg-1",
        element_id="element-1",
    )

    await event.cancel_online_file()
    adapter.client.cancel_online_file.assert_awaited_once_with(
        user_id="445566",
        msg_id="msg-1",
    )


@pytest.mark.asyncio
async def test_napcat_event_online_file_actions_validate_required_fields():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566", message=[])

    with pytest.raises(ValueError, match="msg_id is required"):
        await event.cancel_online_file()

    with pytest.raises(ValueError, match="element_id is required"):
        await event.receive_online_file(user_id="445566", msg_id="msg-1")


@pytest.mark.asyncio
async def test_napcat_event_online_file_actions_allow_explicit_overrides():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.receive_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.refuse_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.cancel_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="445566",
        message=[
            OnlineFile(
                msg_id="embedded-msg",
                element_id="embedded-element",
                file_name="demo.zip",
                file_size="1024",
                is_dir=False,
            )
        ],
    )

    await event.receive_online_file(
        user_id="778899",
        msg_id="explicit-msg",
        element_id="explicit-element",
    )
    adapter.client.receive_online_file.assert_awaited_once_with(
        user_id="778899",
        msg_id="explicit-msg",
        element_id="explicit-element",
    )

    await event.refuse_online_file(
        user_id="778899",
        msg_id="explicit-msg-2",
        element_id="explicit-element-2",
    )
    adapter.client.refuse_online_file.assert_awaited_once_with(
        user_id="778899",
        msg_id="explicit-msg-2",
        element_id="explicit-element-2",
    )

    await event.cancel_online_file(user_id="778899", msg_id="explicit-msg-3")
    adapter.client.cancel_online_file.assert_awaited_once_with(
        user_id="778899",
        msg_id="explicit-msg-3",
    )


@pytest.mark.asyncio
async def test_napcat_online_file_actions_do_not_infer_private_peer_from_group_events():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    group_event = _make_manual_event(
        adapter,
        sender_id="445566",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
        message=[
            OnlineFile(
                msg_id="group-msg-1",
                element_id="group-element-1",
                file_name="demo.zip",
                file_size="1024",
                is_dir=False,
            )
        ],
    )

    with pytest.raises(ValueError, match="outside private chats"):
        await group_event.get_online_file_messages()

    with pytest.raises(ValueError, match="outside private chats"):
        await group_event.receive_online_file()

    with pytest.raises(ValueError, match="outside private chats"):
        await group_event.send_online_file("C:\\tmp\\demo.zip")


@pytest.mark.asyncio
async def test_napcat_event_send_platform_specific_file_actions():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.send_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.send_online_folder = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.send_flash_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )

    private_event = _make_manual_event(adapter, sender_id="445566")
    await private_event.send_online_file("C:\\tmp\\demo.zip", file_name="demo.zip")
    adapter.client.send_online_file.assert_awaited_once_with(
        user_id="445566",
        file_path="C:\\tmp\\demo.zip",
        file_name="demo.zip",
    )

    await private_event.send_online_folder(
        "C:\\tmp\\demo-folder",
        folder_name="demo-folder",
    )
    adapter.client.send_online_folder.assert_awaited_once_with(
        user_id="445566",
        folder_path="C:\\tmp\\demo-folder",
        folder_name="demo-folder",
    )

    await private_event.send_flash_message("flash-set-1")
    adapter.client.send_flash_message.assert_awaited_with(
        fileset_id="flash-set-1",
        user_id="445566",
    )

    group_event = _make_manual_event(
        adapter,
        sender_id="445566",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
    )
    await group_event.send_flash_message("flash-set-2")
    adapter.client.send_flash_message.assert_awaited_with(
        fileset_id="flash-set-2",
        group_id="654321",
    )


@pytest.mark.asyncio
async def test_napcat_event_flash_file_management_helpers():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.create_flash_task = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {"fileset_id": "flash-1"}}
    )
    adapter.client.get_flash_file_list = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {"files": ["a.png"]}}
    )
    adapter.client.get_flash_file_url = AsyncMock(
        return_value={
            "status": "ok",
            "retcode": 0,
            "data": {"url": "https://example.com/a.png"},
        }
    )
    event = _make_manual_event(adapter, sender_id="445566")

    created = await event.create_flash_task(
        ["C:\\tmp\\a.png"],
        name="flash-task",
        thumb_path="C:\\tmp\\thumb.png",
    )
    assert created["data"]["fileset_id"] == "flash-1"
    adapter.client.create_flash_task.assert_awaited_once_with(
        files=["C:\\tmp\\a.png"],
        name="flash-task",
        thumb_path="C:\\tmp\\thumb.png",
    )

    listed = await event.get_flash_file_list("flash-1")
    assert listed["data"]["files"] == ["a.png"]
    adapter.client.get_flash_file_list.assert_awaited_once_with(fileset_id="flash-1")

    resolved = await event.get_flash_file_url("flash-1", file_index=0)
    assert resolved["data"]["url"] == "https://example.com/a.png"
    adapter.client.get_flash_file_url.assert_awaited_once_with(
        fileset_id="flash-1",
        file_name=None,
        file_index=0,
    )


@pytest.mark.asyncio
async def test_napcat_event_request_helpers_validate_request_specific_rules():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_friend_add_request = AsyncMock()
    adapter.client.set_group_add_request = AsyncMock()

    non_request_event = _make_manual_event(adapter, sender_id="445566")
    with pytest.raises(
        ValueError,
        match="approve_request\\(\\)/reject_request\\(\\) are only available",
    ):
        await non_request_event.approve_request()

    friend_message = AstrBotMessage()
    friend_message.type = MessageType.FRIEND_MESSAGE
    friend_message.self_id = "123456"
    friend_message.session_id = "445566"
    friend_message.message_id = "friend-request-msg"
    friend_message.sender = MessageMember("445566", "friend-user")
    friend_message.message = []
    friend_message.message_str = ""
    friend_message.group_id = None
    friend_message.raw_message = SimpleNamespace(flag="friend-flag")
    friend_event = adapter.create_event(friend_message)
    friend_event.set_extra("onebot_request_type", "friend")

    with pytest.raises(
        ValueError, match="friend add requests do not support a reject reason"
    ):
        await friend_event.reject_request(reason="nope")

    group_message = AstrBotMessage()
    group_message.type = MessageType.GROUP_MESSAGE
    group_message.self_id = "123456"
    group_message.session_id = "654321"
    group_message.group_id = "654321"
    group_message.message_id = "group-request-msg"
    group_message.sender = MessageMember("445566", "group-user")
    group_message.message = []
    group_message.message_str = ""
    group_message.raw_message = SimpleNamespace(flag="group-flag")
    group_event = adapter.create_event(group_message)
    group_event.set_extra("onebot_request_type", "group")

    with pytest.raises(ValueError, match="group add requests do not support a remark"):
        await group_event.approve_request(remark="hello")

    missing_flag_message = AstrBotMessage()
    missing_flag_message.type = MessageType.FRIEND_MESSAGE
    missing_flag_message.self_id = "123456"
    missing_flag_message.session_id = "445566"
    missing_flag_message.message_id = "missing-flag-msg"
    missing_flag_message.sender = MessageMember("445566", "friend-user")
    missing_flag_message.message = []
    missing_flag_message.message_str = ""
    missing_flag_message.group_id = None
    missing_flag_message.raw_message = SimpleNamespace(flag=" ")
    missing_flag_event = adapter.create_event(missing_flag_message)
    missing_flag_event.set_extra("onebot_request_type", "friend")

    with pytest.raises(
        ValueError, match="current NapCat request event does not contain a flag"
    ):
        await missing_flag_event.approve_request()


@pytest.mark.asyncio
async def test_napcat_event_group_management_helpers_route_to_forward_ws_client():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_group_admin = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_ban = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_card = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_kick = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_kick_members = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_leave = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_whole_ban = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_essence_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.delete_essence_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.send_group_notice = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.group_poke = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.get_group_msg_history = AsyncMock(
        return_value=[{"message_id": 1001, "message": []}]
    )
    adapter.client.get_ai_characters = AsyncMock(
        return_value=[
            {
                "type": "default",
                "characters": [
                    {"character_id": "voice-1", "character_name": "Demo Voice"}
                ],
            }
        ]
    )
    adapter.client.send_group_ai_record = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="445566",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
    )

    await event.set_group_admin(enable=False)
    adapter.client.set_group_admin.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        enable=False,
    )

    await event.set_group_ban(duration=600)
    adapter.client.set_group_ban.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        duration=600,
    )

    await event.set_group_card("new-card")
    adapter.client.set_group_card.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        card="new-card",
    )

    await event.kick_group_member(reject_add_request=True)
    adapter.client.set_group_kick.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        reject_add_request=True,
    )

    await event.kick_group_members(["10001", 10002], reject_add_request=False)
    adapter.client.set_group_kick_members.assert_awaited_once_with(
        group_id="654321",
        user_ids=["10001", 10002],
        reject_add_request=False,
    )

    await event.leave_group(is_dismiss=True)
    adapter.client.set_group_leave.assert_awaited_once_with(
        group_id="654321",
        is_dismiss=True,
    )

    await event.set_group_whole_ban(enable=True)
    adapter.client.set_group_whole_ban.assert_awaited_once_with(
        group_id="654321",
        enable=True,
    )

    await event.set_essence_message()
    adapter.client.set_essence_message.assert_awaited_once_with(
        message_id="local-message-id",
    )

    await event.delete_essence_message()
    adapter.client.delete_essence_message.assert_awaited_once_with(
        message_id="local-message-id",
        msg_seq=None,
        msg_random=None,
        group_id="654321",
    )

    await event.send_group_notice("hello", pinned=1)
    adapter.client.send_group_notice.assert_awaited_once_with(
        group_id="654321",
        content="hello",
        pinned=1,
        type_=None,
        confirm_required=None,
        is_show_edit_card=None,
        tip_window_type=None,
        image=None,
    )

    await event.send_poke(target_id="123456")
    adapter.client.group_poke.assert_awaited_once_with(
        user_id="445566",
        group_id="654321",
        target_id="123456",
    )

    history = await event.get_group_msg_history(count=50)
    assert history == [{"message_id": 1001, "message": []}]
    adapter.client.get_group_msg_history.assert_awaited_once_with(
        group_id="654321",
        count=50,
        message_seq=None,
    )

    characters = await event.get_ai_characters()
    assert characters[0]["characters"][0]["character_id"] == "voice-1"
    adapter.client.get_ai_characters.assert_awaited_once_with(
        group_id="654321",
        chat_type=1,
    )

    await event.send_group_ai_record("你好", character="voice-1")
    adapter.client.send_group_ai_record.assert_awaited_once_with(
        group_id="654321",
        character="voice-1",
        text="你好",
        chat_type=1,
        timeout_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_napcat_event_social_helpers_and_group_validation():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.send_like = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.friend_poke = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_input_status = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.get_friend_msg_history = AsyncMock(
        return_value=[{"message_id": 2001, "message": []}]
    )
    adapter.client.fetch_custom_face = AsyncMock(
        return_value=["https://example.com/face-1.png"]
    )

    private_event = _make_manual_event(adapter, sender_id="445566")
    await private_event.send_like(times=3)
    adapter.client.send_like.assert_awaited_once_with(user_id="445566", times=3)

    await private_event.send_poke(target_id="123456")
    adapter.client.friend_poke.assert_awaited_once_with(
        user_id="445566",
        target_id="123456",
    )

    await private_event.set_input_status(event_type=1)
    adapter.client.set_input_status.assert_awaited_once_with(
        user_id="445566",
        event_type=1,
    )

    history = await private_event.get_friend_msg_history(count=5)
    assert history == [{"message_id": 2001, "message": []}]
    adapter.client.get_friend_msg_history.assert_awaited_once_with(
        user_id="445566",
        count=5,
        message_seq=None,
    )

    faces = await private_event.fetch_custom_face(count=1)
    assert faces == ["https://example.com/face-1.png"]
    adapter.client.fetch_custom_face.assert_awaited_once_with(count=1)

    with pytest.raises(ValueError, match="group_id is required"):
        await private_event.set_group_admin()

    with pytest.raises(ValueError, match="user_ids is required"):
        await private_event.kick_group_members([])


@pytest.mark.asyncio
async def test_napcat_adapter_proactive_management_helpers_proxy_to_forward_ws_client():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_group_admin = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_ban = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_card = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_kick = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_kick_members = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_leave = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_whole_ban = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_essence_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.delete_essence_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.send_group_notice = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.send_like = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.group_poke = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.friend_poke = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_input_status = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.get_group_msg_history = AsyncMock(
        return_value=[{"message_id": 3001}]
    )
    adapter.client.get_friend_msg_history = AsyncMock(
        return_value=[{"message_id": 3002}]
    )
    adapter.client.fetch_custom_face = AsyncMock(
        return_value=["https://example.com/face-2.png"]
    )
    adapter.client.get_ai_characters = AsyncMock(
        return_value=[{"type": "default", "characters": []}]
    )
    adapter.client.send_group_ai_record = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )

    await adapter.set_group_admin(group_id="654321", user_id="445566", enable=True)
    adapter.client.set_group_admin.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        enable=True,
    )

    await adapter.set_group_ban(group_id="654321", user_id="445566", duration=60)
    adapter.client.set_group_ban.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        duration=60,
    )

    await adapter.set_group_card(group_id="654321", user_id="445566", card="new-card")
    adapter.client.set_group_card.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        card="new-card",
    )

    await adapter.kick_group_member(
        group_id="654321",
        user_id="445566",
        reject_add_request=True,
    )
    adapter.client.set_group_kick.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        reject_add_request=True,
    )

    await adapter.kick_group_members(group_id="654321", user_ids=["1", "2"])
    adapter.client.set_group_kick_members.assert_awaited_once_with(
        group_id="654321",
        user_ids=["1", "2"],
        reject_add_request=None,
    )

    await adapter.leave_group(group_id="654321", is_dismiss=True)
    adapter.client.set_group_leave.assert_awaited_once_with(
        group_id="654321",
        is_dismiss=True,
    )

    await adapter.set_group_whole_ban(group_id="654321", enable=False)
    adapter.client.set_group_whole_ban.assert_awaited_once_with(
        group_id="654321",
        enable=False,
    )

    await adapter.set_essence_message(message_id="9001")
    adapter.client.set_essence_message.assert_awaited_once_with(message_id="9001")

    await adapter.delete_essence_message(
        message_id="9001",
        msg_seq="seq-1",
        msg_random="rand-1",
        group_id="654321",
    )
    adapter.client.delete_essence_message.assert_awaited_once_with(
        message_id="9001",
        msg_seq="seq-1",
        msg_random="rand-1",
        group_id="654321",
    )

    await adapter.send_group_notice(group_id="654321", content="notice")
    adapter.client.send_group_notice.assert_awaited_once_with(
        group_id="654321",
        content="notice",
        pinned=None,
        type_=None,
        confirm_required=None,
        is_show_edit_card=None,
        tip_window_type=None,
        image=None,
    )

    await adapter.send_like(user_id="445566", times=2)
    adapter.client.send_like.assert_awaited_once_with(user_id="445566", times=2)

    await adapter.send_poke(user_id="445566", group_id="654321", target_id="123456")
    adapter.client.group_poke.assert_awaited_once_with(
        user_id="445566",
        group_id="654321",
        target_id="123456",
    )

    await adapter.send_poke(user_id="445566", target_id="123456")
    adapter.client.friend_poke.assert_awaited_once_with(
        user_id="445566",
        target_id="123456",
    )

    await adapter.set_input_status(user_id="445566", event_type=2)
    adapter.client.set_input_status.assert_awaited_once_with(
        user_id="445566",
        event_type=2,
    )

    assert await adapter.get_group_msg_history(group_id="654321", count=10) == [
        {"message_id": 3001}
    ]
    adapter.client.get_group_msg_history.assert_awaited_once_with(
        group_id="654321",
        count=10,
        message_seq=None,
    )

    assert await adapter.get_friend_msg_history(user_id="445566", count=8) == [
        {"message_id": 3002}
    ]
    adapter.client.get_friend_msg_history.assert_awaited_once_with(
        user_id="445566",
        count=8,
        message_seq=None,
    )

    assert await adapter.fetch_custom_face(count=2) == [
        "https://example.com/face-2.png"
    ]
    adapter.client.fetch_custom_face.assert_awaited_once_with(count=2)

    assert await adapter.get_ai_characters(group_id="654321") == [
        {"type": "default", "characters": []}
    ]
    adapter.client.get_ai_characters.assert_awaited_once_with(
        group_id="654321",
        chat_type=1,
    )

    await adapter.send_group_ai_record(
        group_id="654321",
        character="voice-1",
        text="你好",
    )
    adapter.client.send_group_ai_record.assert_awaited_once_with(
        group_id="654321",
        character="voice-1",
        text="你好",
        chat_type=1,
        timeout_seconds=10.0,
    )


def test_napcat_event_outline_includes_new_component_placeholders():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(
        adapter,
        message=[
            Anonymous(ignore=1),
            MFace(
                emoji_package_id=1152,
                emoji_id="987654321",
                key="market-face-key",
                summary="[HappyFace]",
            ),
            OnlineFile(
                msg_id="msg-1",
                element_id="element-1",
                file_name="demo.zip",
                file_size="1024",
                is_dir=False,
            ),
            FlashTransfer(file_set_id="flash-set-1"),
            Markdown(content="# Demo"),
            MiniApp(data='{"app":"demo"}'),
        ],
    )

    outline = event.get_message_outline()
    assert "[匿名]" in outline
    assert "[商城表情:[HappyFace]]" in outline
    assert "[在线文件:demo.zip]" in outline
    assert "[闪传]" in outline
    assert "[Markdown]" in outline
    assert "[小程序]" in outline
