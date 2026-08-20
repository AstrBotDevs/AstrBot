from __future__ import annotations

import pytest

from tests.unit.platform.napcat_adapter_support import *  # noqa: F403

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_napcat_group_message_event_is_queued_with_expected_components():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock(
        return_value=NapCatFetchedMessage(
            message_id=9001,
            sender_id=333444,
            sender_nickname="quoted-user",
            time=1719999999,
            message_str="quoted text",
            raw_message="quoted text",
            message_payload=[
                {"type": "text", "data": {"text": "quoted text"}},
                {
                    "type": "image",
                    "data": {
                        "file": "https://example.com/quoted.jpg",
                        "url": "https://example.com/quoted.jpg",
                    },
                },
            ],
        )
    )
    adapter.client.delete_message = AsyncMock()
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
            "raw_message": "@bot hello",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "admin",
            },
            "message": [
                {"type": "at", "data": {"qq": "123456", "name": "bot"}},
                {"type": "text", "data": {"text": " hello"}},
                {
                    "type": "image",
                    "data": {
                        "file": "https://example.com/a.jpg",
                        "url": "https://example.com/a.jpg",
                    },
                },
                {"type": "reply", "data": {"id": "9001"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == "hello"
    assert queued.platform_member_role == "admin"
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "At",
        "Plain",
        "Image",
        "Reply",
    ]
    reply = queued.get_messages()[-1]
    assert reply.id == "9001"
    assert reply.sender_id == 0
    assert reply.sender_nickname == ""
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()
    await queued.delete()
    adapter.client.delete_message.assert_awaited_once_with("777")


@pytest.mark.asyncio
async def test_napcat_group_message_reply_accepts_string_quoted_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 778,
            "font": 14,
            "raw_message": "hello [CQ:reply,id=9003]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "reply", "data": {"id": "9003"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[-1]
    assert reply.id == "9003"
    assert reply.sender_id == 0
    assert reply.sender_nickname == ""
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_reply_prefers_decoded_text_for_array_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 779,
            "font": 14,
            "raw_message": "hello [CQ:reply,id=9004]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "reply", "data": {"id": "9004"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[-1]
    assert reply.id == "9004"
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_reply_uses_decoded_text_for_runtime_string_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 779,
            "font": 14,
            "raw_message": "hello [CQ:reply,id=9005]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "reply", "data": {"id": "9005"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[-1]
    assert reply.id == "9005"
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_reply_keeps_missing_at_targets_without_group_lookup():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_group_member_info = AsyncMock()
    adapter.client.get_stranger_info = AsyncMock()
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 779,
            "font": 14,
            "raw_message": "hello [CQ:reply,id=9005]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "reply", "data": {"id": "9005"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[-1]
    assert reply.id == "9005"
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_group_member_info.assert_not_awaited()
    adapter.client.get_stranger_info.assert_not_awaited()
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_reply_keeps_nontext_runtime_string_payload_empty():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 780,
            "font": 14,
            "raw_message": "hello [CQ:reply,id=9006]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "reply", "data": {"id": "9006"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[-1]
    assert reply.id == "9006"
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_event_logs_inbound_summary(caplog):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "private",
            "sub_type": "friend",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 111222,
            "message_id": 778,
            "font": 14,
            "raw_message": "/sid",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
            },
            "message": [
                {"type": "text", "data": {"text": "/sid"}},
            ],
        }
    )

    with caplog.at_level("INFO"):
        await adapter.handle_forward_ws_event(event)

    assert any(
        "[NapCat] Received private message:" in message and "outline=/sid" in message
        for message in caplog.messages
    )


@pytest.mark.asyncio
async def test_napcat_group_message_at_segment_keeps_targets_without_client_lookup():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    adapter.client.get_group_member_info = AsyncMock()
    adapter.client.get_stranger_info = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 778,
            "font": 14,
            "raw_message": "@member @stranger hello",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "at", "data": {"qq": "999999"}},
                {"type": "text", "data": {"text": " hi "}},
                {"type": "at", "data": {"qq": "888888"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == "@999999  hi  @888888"
    messages = queued.get_messages()
    assert messages[0].name == ""
    assert messages[2].name == ""
    adapter.client.get_group_member_info.assert_not_awaited()
    adapter.client.get_stranger_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_event_supports_dice_rps_and_shake_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 779,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "dice"},
                {"type": "rps"},
                {"type": "shake", "data": {}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Dice",
        "RPS",
        "Shake",
    ]


@pytest.mark.asyncio
async def test_napcat_group_message_event_supports_anonymous_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 7791,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "anonymous", "data": {"ignore": 1}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert len(queued.get_messages()) == 1
    assert isinstance(queued.get_messages()[0], Anonymous)
    assert queued.get_messages()[0].ignore == 1


@pytest.mark.asyncio
async def test_napcat_group_message_event_supports_xml_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 780,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "xml", "data": {"data": "<msg serviceID='1'>demo</msg>"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert len(queued.get_messages()) == 1
    assert isinstance(queued.get_messages()[0], Xml)
    assert queued.get_messages()[0].data == "<msg serviceID='1'>demo</msg>"


@pytest.mark.asyncio
async def test_napcat_group_message_event_supports_custom_node_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
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
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {
                    "type": "node",
                    "data": {
                        "user_id": "10001",
                        "nickname": "forwarded-user",
                        "content": [
                            {"type": "text", "data": {"text": "nested text"}},
                            {"type": "face", "data": {"id": "123"}},
                        ],
                        "summary": "forward summary",
                    },
                }
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == "nested text"
    assert len(queued.get_messages()) == 1
    assert isinstance(queued.get_messages()[0], Node)
    assert queued.get_messages()[0].uin == "10001"
    assert queued.get_messages()[0].name == "forwarded-user"
    assert [
        type(component).__name__ for component in queued.get_messages()[0].content
    ] == [
        "Plain",
        "Face",
    ]


@pytest.mark.asyncio
async def test_napcat_custom_node_recursively_preserves_reply_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 782,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "role": "member",
            },
            "message": [
                {
                    "type": "node",
                    "data": {
                        "user_id": "10001",
                        "nickname": "Mock Node Sender",
                        "source": "Mock Source",
                        "summary": "Mock Summary",
                        "prompt": "Mock Prompt",
                        "news": [{"text": "Mock Preview"}],
                        "time": "1720000001",
                        "content": [
                            {"type": "reply", "data": {"id": "9001"}},
                            {"type": "text", "data": {"text": "nested"}},
                        ],
                    },
                }
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    node = queue.get_nowait().get_messages()[0]
    assert isinstance(node, Node)
    assert isinstance(node.content[0], Reply)
    assert node.content[0].id == "9001"
    assert node.source == "Mock Source"
    assert node.summary == "Mock Summary"
    assert node.prompt == "Mock Prompt"
    assert node.news == [{"text": "Mock Preview"}]
    assert node.time == 1720000001


@pytest.mark.asyncio
async def test_napcat_embedded_forward_content_becomes_structured_nodes():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 783,
            "font": 14,
            "raw_message": "[CQ:forward,id=9000000000000000001]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "role": "member",
            },
            "message": [
                {
                    "type": "forward",
                    "data": {
                        "id": "9000000000000000001",
                        "content": [
                            {
                                "user_id": 10001,
                                "sender": {
                                    "user_id": 10001,
                                    "nickname": "Mock Forward Sender",
                                },
                                "message": [
                                    {
                                        "type": "text",
                                        "data": {"text": "forwarded text"},
                                    },
                                    {"type": "reply", "data": {"id": "9002"}},
                                ],
                            }
                        ],
                    },
                }
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    forward = queue.get_nowait().get_messages()[0]
    assert isinstance(forward, Forward)
    assert forward.id == "9000000000000000001"
    assert forward.content
    assert isinstance(forward.content[0], Node)
    assert forward.content[0].name == "Mock Forward Sender"
    assert isinstance(forward.content[0].content[1], Reply)


@pytest.mark.asyncio
async def test_napcat_forward_ws_group_message_accepts_real_image_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
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
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {
                    "type": "image",
                    "data": {
                        "file": "napcat-image.png",
                        "url": "https://example.com/napcat-image.png",
                        "summary": "[Image]",
                        "sub_type": 1,
                        "file_size": 2048,
                    },
                }
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert len(queued.get_messages()) == 1
    assert isinstance(queued.get_messages()[0], Image)
    assert queued.get_messages()[0].file == "napcat-image.png"
    assert queued.get_messages()[0].url == "https://example.com/napcat-image.png"
    assert queued.get_messages()[0].sub_type == "1"


@pytest.mark.asyncio
async def test_napcat_forward_ws_group_message_accepts_real_file_like_payloads():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 782,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {
                    "type": "record",
                    "data": {
                        "file": "napcat-record.amr",
                        "path": "C:/NapCat/cache/napcat-record.amr",
                        "url": "file:///C:/NapCat/cache/napcat-record.amr",
                        "file_size": 1024,
                    },
                },
                {
                    "type": "video",
                    "data": {
                        "file": "encoded-video-token",
                        "url": "file:///C:/NapCat/cache/napcat-video.mp4",
                        "file_size": 4096,
                    },
                },
                {
                    "type": "file",
                    "data": {
                        "file": "napcat-doc.zip",
                        "file_id": "file-uuid-1",
                        "file_size": 8192,
                        "url": "https://example.com/napcat-doc.zip",
                    },
                },
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Record",
        "Video",
        "File",
    ]
    assert queued.get_messages()[0].path == "C:/NapCat/cache/napcat-record.amr"
    assert queued.get_messages()[0].url == "file:///C:/NapCat/cache/napcat-record.amr"
    assert queued.get_messages()[1].url == "file:///C:/NapCat/cache/napcat-video.mp4"
    assert queued.get_messages()[2].name == "napcat-doc.zip"
    assert queued.get_messages()[2].url == "https://example.com/napcat-doc.zip"


@pytest.mark.asyncio
async def test_napcat_group_message_reply_preserves_nonstandard_quoted_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 782,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "reply", "data": {"id": "9002"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[0]
    assert reply.id == "9002"
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_forward_ws_bot_offline_notice_is_queued_as_friend_message():
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
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.session.session_id == "123456"
    assert (
        queued.get_message_str()
        == "[notice:bot_offline] user 123456 tag gateway_disconnect message socket closed by remote peer"
    )
    assert queued.get_extra("onebot_notice_type") == "bot_offline"
    assert queued.get_extra("napcat_tag") == "gateway_disconnect"
    assert queued.get_extra("napcat_notice_message") == "socket closed by remote peer"
    assert queued.get_extra("skip_private_wake") is True
