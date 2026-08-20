from __future__ import annotations

import pytest

from tests.unit.platform.napcat_adapter_support import *  # noqa: F403

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_ignores_extra_event_fields():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()

    await adapter.client._handle_ws_payload(
        """
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
            "nickname": "tester"
          },
          "message": [
            {"type": "text", "data": {"text": "/sid"}}
          ],
          "unexpected_top_level": "ignored"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "/sid"


@pytest.mark.asyncio
async def test_napcat_unknown_array_segment_degrades_without_dropping_message():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 779,
          "font": 14,
          "raw_message": "before unknown after",
          "sender": {"user_id": 111222, "nickname": "tester"},
          "message": [
            {"type": "text", "data": {"text": "before "}},
            {"type": "future_segment", "data": {"value": "mock"}},
            {"type": "text", "data": {"text": " after"}}
          ]
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == (
        "before [Unsupported NapCat segment: future_segment] after"
    )
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Plain",
        "Plain",
        "Plain",
    ]


@pytest.mark.asyncio
async def test_napcat_unknown_notice_is_queued_as_generic_event():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "notice",
          "notice_type": "future_notice",
          "sub_type": "mock",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "future_value": "preserved"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "[notice:future_notice:mock] user 111222"
    assert queued.get_extra("onebot_notice_type") == "future_notice"
    assert queued.get_extra("napcat_event")["future_value"] == "preserved"


@pytest.mark.asyncio
async def test_napcat_unknown_request_is_queued_as_generic_event():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "request",
          "request_type": "future_request",
          "sub_type": "mock",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "comment": "mock request",
          "flag": "mock-flag"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == (
        "[request:future_request:mock] user 111222 comment mock request flag mock-flag"
    )
    assert queued.get_extra("onebot_request_type") == "future_request"


@pytest.mark.asyncio
async def test_napcat_unknown_meta_event_is_ignored():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "meta_event",
          "meta_event_type": "future_meta",
          "time": 1720000000,
          "self_id": 123456
        }
        """
    )

    assert queue.empty()


@pytest.mark.asyncio
async def test_napcat_forward_ws_only_ignores_message_sent_events():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message_sent",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 123456,
          "target_id": 123456,
          "message_id": 779,
          "font": 14,
          "raw_message": "echo",
          "sender": {
            "user_id": 123456,
            "nickname": "bot-self"
          },
          "message": [
            {"type": "text", "data": {"text": "echo"}}
          ]
        }
        """
    )

    assert queue.empty()


@pytest.mark.asyncio
async def test_napcat_forward_ws_only_ignores_self_sent_message_events():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 123456,
          "target_id": 123456,
          "message_id": 780,
          "font": 14,
          "raw_message": "self-echo",
          "sender": {
            "user_id": 123456,
            "nickname": "bot-self"
          },
          "message": [
            {"type": "text", "data": {"text": "self-echo"}}
          ]
        }
        """
    )

    assert queue.empty()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_accepts_heartbeat_meta_event(caplog):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    with caplog.at_level("WARNING"):
        await adapter.client._handle_ws_payload(
            """
            {
              "time": 1782950187,
              "self_id": 1507533037,
              "post_type": "meta_event",
              "meta_event_type": "heartbeat",
              "status": {
                "online": true,
                "good": true
              },
              "interval": 30000
            }
            """
        )

    assert queue.empty()
    assert not any("rejected event payload" in message for message in caplog.messages)


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_defaults_missing_group_sender_role(caplog):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    with caplog.at_level("INFO"):
        await adapter.client._handle_ws_payload(
            """
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
              "raw_message": "hello",
              "sender": {
                "user_id": 111222,
                "nickname": "tester-card"
              },
              "message": [
                {"type": "text", "data": {"text": "hello"}}
              ]
            }
            """
        )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "hello"
    assert queued.platform_member_role == "member"
    assert any(
        "defaulted sender.role to member" in message for message in caplog.messages
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_napcat_private_sender_role_cannot_grant_group_privilege(role):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        json.dumps(
            {
                "post_type": "message",
                "message_type": "private",
                "sub_type": "friend",
                "time": 1720000000,
                "self_id": 123456,
                "user_id": 111222,
                "message_id": 784,
                "font": 14,
                "raw_message": "hello",
                "sender": {
                    "user_id": 111222,
                    "nickname": "tester",
                    "role": role,
                },
                "message": [{"type": "text", "data": {"text": "hello"}}],
            }
        )
    )

    queued = queue.get_nowait()
    assert queued.is_private_chat()
    assert queued.platform_member_role == "member"


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_drops_sender_extra_fields(caplog):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    with caplog.at_level("INFO"):
        await adapter.client._handle_ws_payload(
            """
            {
              "post_type": "message",
              "message_type": "private",
              "sub_type": "friend",
              "time": 1720000000,
              "self_id": 123456,
              "user_id": 111222,
              "message_id": 781,
              "font": 14,
              "raw_message": "hello",
              "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "uid": "unexpected-uid",
                "tiny_id": "unexpected-tiny-id"
              },
              "message": [
                {"type": "text", "data": {"text": "hello"}}
              ]
            }
            """
        )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "hello"
    assert any(
        "dropped sender extra fields: tiny_id, uid" in message
        for message in caplog.messages
    )


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_preserves_temp_private_payload_fields(
    caplog,
):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    with caplog.at_level("INFO"):
        await adapter.client._handle_ws_payload(
            """
            {
              "post_type": "message",
              "message_type": "private",
              "sub_type": "group",
              "time": 1720000000,
              "self_id": 123456,
              "group_id": 654321,
              "group_name": "temp-group",
              "user_id": 111222,
              "message_id": 782,
              "font": 14,
              "raw_message": "temp hello",
              "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "temp-card"
              },
              "message": [
                {"type": "text", "data": {"text": "temp hello"}}
              ]
            }
            """
        )

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.get_message_str() == "temp hello"
    assert queued.get_sender_name() == "temp-card"
    assert queued.get_group_id() == "654321"
    assert queued.session.session_id == "111222"
    assert queued.get_extra("onebot_sub_type") == "group"
    assert queued.get_extra("napcat_group_id") == 654321
    assert queued.get_extra("napcat_event")["group_name"] == "temp-group"
    assert not any(
        "coerced private sub_type to friend" in message for message in caplog.messages
    )


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_accepts_private_string_message_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "target_id": 123456,
          "message_id": 783,
          "message_seq": 783,
          "real_id": 783,
          "real_seq": "783",
          "font": 14,
          "message_format": "string",
          "message_sent_type": "self",
          "raw_message": "hello string",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": "hello string"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "hello string"
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Plain"
    ]
    assert queued.get_messages()[0].text == "hello string"
    assert queued.get_extra("napcat_event")["message_format"] == "string"
    assert queued.get_extra("napcat_notice_message") is None


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_accepts_group_string_message_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "group",
          "sub_type": "normal",
          "time": 1720000000,
          "self_id": 123456,
          "group_id": 654321,
          "group_name": "napcat-group",
          "user_id": 111222,
          "message_id": 784,
          "message_seq": 784,
          "real_id": 784,
          "real_seq": "784",
          "font": 14,
          "message_format": "string",
          "raw_message": "@bot hello group string",
          "sender": {
            "user_id": 111222,
            "nickname": "tester",
            "role": "member"
          },
          "message": "@bot hello group string"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.get_group_id() == "654321"
    assert queued.get_message_str() == "@bot hello group string"
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Plain"
    ]
    assert queued.get_extra("napcat_event")["group_name"] == "napcat-group"
    assert queued.get_extra("napcat_event")["message_format"] == "string"


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_parses_group_string_cq_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "group",
          "sub_type": "normal",
          "time": 1720000000,
          "self_id": 123456,
          "group_id": 654321,
          "group_name": "napcat-group",
          "user_id": 111222,
          "message_id": 785,
          "message_seq": 785,
          "real_id": 785,
          "real_seq": "785",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:at,qq=123456,name=bot] hello [CQ:reply,id=9004]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester",
            "role": "member"
          },
          "message": "[CQ:at,qq=123456,name=bot] hello [CQ:reply,id=9004]"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "hello"
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "At",
        "Plain",
        "Reply",
    ]
    reply = queued.get_messages()[-1]
    assert reply.id == "9004"
    assert reply.sender_id == 0
    assert reply.sender_nickname == ""
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_keeps_group_string_at_targets_without_lookup():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    adapter.client.get_group_member_info = AsyncMock()
    adapter.client.get_stranger_info = AsyncMock()

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "group",
          "sub_type": "normal",
          "time": 1720000000,
          "self_id": 123456,
          "group_id": 654321,
          "user_id": 111222,
          "message_id": 785,
          "message_seq": 785,
          "real_id": 785,
          "real_seq": "785",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:at,qq=999999] hi [CQ:at,qq=888888][CQ:at,qq=all][CQ:at,qq=777777,name=inline-name]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester",
            "role": "member"
          },
          "message": "[CQ:at,qq=999999] hi [CQ:at,qq=888888][CQ:at,qq=all][CQ:at,qq=777777,name=inline-name]"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "@999999  hi  @888888  @all  @inline-name"
    messages = queued.get_messages()
    assert [type(component).__name__ for component in messages] == [
        "At",
        "Plain",
        "At",
        "AtAll",
        "At",
    ]
    assert messages[0].name == ""
    assert messages[2].name == ""
    assert messages[4].name == "inline-name"
    adapter.client.get_group_member_info.assert_not_awaited()
    adapter.client.get_stranger_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_keeps_group_string_at_targets_from_raw_message_fallback():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    adapter.client.get_group_member_info = AsyncMock()
    adapter.client.get_stranger_info = AsyncMock()

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "group",
          "sub_type": "normal",
          "time": 1720000000,
          "self_id": 123456,
          "group_id": 654321,
          "user_id": 111222,
          "message_id": 786,
          "message_seq": 786,
          "real_id": 786,
          "real_seq": "786",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:at,qq=999999] hello",
          "sender": {
            "user_id": 111222,
            "nickname": "tester",
            "role": "member"
          },
          "message": ""
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "@999999  hello"
    messages = queued.get_messages()
    assert [type(component).__name__ for component in messages] == ["At", "Plain"]
    assert messages[0].name == ""
    adapter.client.get_group_member_info.assert_not_awaited()
    adapter.client.get_stranger_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_parses_string_nonstandard_and_forward_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 786,
          "message_seq": 786,
          "real_id": 786,
          "real_seq": "786",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:mface,emoji_package_id=1152,emoji_id=987654321,key=market-face-key,summary=&#91;HappyFace&#93;][CQ:onlinefile,msgId=msg-1,elementId=element-1,fileName=demo.zip,fileSize=2048,isDir=false][CQ:flashtransfer,fileSetId=flash-set-1][CQ:forward,id=forward-1]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": "[CQ:mface,emoji_package_id=1152,emoji_id=987654321,key=market-face-key,summary=&#91;HappyFace&#93;][CQ:onlinefile,msgId=msg-1,elementId=element-1,fileName=demo.zip,fileSize=2048,isDir=false][CQ:flashtransfer,fileSetId=flash-set-1][CQ:forward,id=forward-1]"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "MFace",
        "OnlineFile",
        "FlashTransfer",
        "Forward",
    ]
    assert queued.get_messages()[0].summary == "[HappyFace]"
    assert queued.get_messages()[1].file_name == "demo.zip"
    assert queued.get_messages()[1].is_dir is False
    assert queued.get_messages()[2].file_set_id == "flash-set-1"
    assert queued.get_messages()[3].id == "forward-1"


@pytest.mark.asyncio
async def test_napcat_unknown_string_segment_becomes_unknown_component():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 790,
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:future_segment,value=mock]tail",
          "sender": {"user_id": 111222, "nickname": "tester"},
          "message": "[CQ:future_segment,value=mock]tail"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == (
        "[Unsupported NapCat segment: future_segment]tail"
    )
    assert isinstance(queued.get_messages()[0], Unknown)
    assert queued.get_messages()[0].segment_type == "future_segment"
    assert isinstance(queued.get_messages()[1], Plain)


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_parses_string_file_like_and_rich_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 787,
          "message_seq": 787,
          "real_id": 787,
          "real_seq": "787",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:image,file=napcat-image.png,url=https://example.com/napcat-image.png,sub_type=1][CQ:record,file=napcat-record.amr,path=C:/NapCat/cache/napcat-record.amr,url=file:///C:/NapCat/cache/napcat-record.amr][CQ:video,file=encoded-video-token,url=file:///C:/NapCat/cache/napcat-video.mp4][CQ:file,file=napcat-doc.zip,url=https://example.com/napcat-doc.zip][CQ:json,data={\\\"app\\\":\\\"demo\\\"}][CQ:xml,data=<msg serviceID='1'>demo</msg>]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": "[CQ:image,file=napcat-image.png,url=https://example.com/napcat-image.png,sub_type=1][CQ:record,file=napcat-record.amr,path=C:/NapCat/cache/napcat-record.amr,url=file:///C:/NapCat/cache/napcat-record.amr][CQ:video,file=encoded-video-token,url=file:///C:/NapCat/cache/napcat-video.mp4][CQ:file,file=napcat-doc.zip,url=https://example.com/napcat-doc.zip][CQ:json,data={\\\"app\\\":\\\"demo\\\"}][CQ:xml,data=<msg serviceID='1'>demo</msg>]"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Image",
        "Record",
        "Video",
        "File",
        "Json",
        "Xml",
    ]
    assert queued.get_messages()[0].file == "napcat-image.png"
    assert queued.get_messages()[0].url == "https://example.com/napcat-image.png"
    assert queued.get_messages()[0].sub_type == "1"
    assert queued.get_messages()[1].path == "C:/NapCat/cache/napcat-record.amr"
    assert queued.get_messages()[2].url == "file:///C:/NapCat/cache/napcat-video.mp4"
    assert queued.get_messages()[3].name == "napcat-doc.zip"
    assert queued.get_messages()[4].data == {"app": "demo"}
    assert queued.get_messages()[5].data == "<msg serviceID='1'>demo</msg>"


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_unescapes_commas_in_string_rich_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 788,
          "message_seq": 788,
          "real_id": 788,
          "real_seq": "788",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:json,data={\\\"app\\\":\\\"demo\\\"&#44;\\\"text\\\":\\\"hello&#44;world\\\"}][CQ:xml,data=<msg serviceID='1' brief='a&#44;b'>demo</msg>]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": "[CQ:json,data={\\\"app\\\":\\\"demo\\\"&#44;\\\"text\\\":\\\"hello&#44;world\\\"}][CQ:xml,data=<msg serviceID='1' brief='a&#44;b'>demo</msg>]"
        }
        """
    )

    queued = queue.get_nowait()
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Json",
        "Xml",
    ]
    assert queued.get_messages()[0].data == {"app": "demo", "text": "hello,world"}
    assert queued.get_messages()[1].data == "<msg serviceID='1' brief='a,b'>demo</msg>"


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_parses_string_misc_segments_including_custom_music():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 789,
          "message_seq": 789,
          "real_id": 789,
          "real_seq": "789",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:music,type=qq,id=12345][CQ:music,type=custom,url=https://example.com/song,image=https://example.com/cover.jpg,content=hello][CQ:contact,type=qq,id=10001][CQ:location,lat=30.123,lon=120.456,title=Hangzhou,content=West Lake][CQ:poke,type=2000,id=10001][CQ:dice][CQ:rps]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": "[CQ:music,type=qq,id=12345][CQ:music,type=custom,url=https://example.com/song,image=https://example.com/cover.jpg,content=hello][CQ:contact,type=qq,id=10001][CQ:location,lat=30.123,lon=120.456,title=Hangzhou,content=West Lake][CQ:poke,type=2000,id=10001][CQ:dice][CQ:rps]"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Music",
        "Music",
        "Contact",
        "Location",
        "Poke",
        "Dice",
        "RPS",
    ]
    assert queued.get_messages()[0].sub_type == "qq"
    assert queued.get_messages()[0].id == 12345
    assert queued.get_messages()[1].sub_type == "custom"
    assert queued.get_messages()[1].url == "https://example.com/song"
    assert queued.get_messages()[1].image == "https://example.com/cover.jpg"
    assert queued.get_messages()[1].audio is None
    assert queued.get_messages()[1].title is None
    assert queued.get_messages()[2].sub_type == "qq"
    assert queued.get_messages()[2].id == 10001
    assert queued.get_messages()[3].lat == 30.123
    assert queued.get_messages()[3].lon == 120.456
    assert queued.get_messages()[3].title == "Hangzhou"
    assert queued.get_messages()[3].content == "West Lake"
    assert str(queued.get_messages()[4].id) == "10001"
    assert queued.get_messages()[4].poke_type == "2000"


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_supports_nonstandard_live_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 783,
          "font": 14,
          "raw_message": "nonstandard payload",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": [
            {
              "type": "mface",
              "data": {
                "emoji_package_id": 1152,
                "emoji_id": "987654321",
                "key": "market-face-key",
                "summary": "[HappyFace]"
              }
            },
            {
              "type": "markdown",
              "data": {
                "content": "# Demo"
              }
            },
            {
              "type": "miniapp",
              "data": {
                "data": "{\\\"app\\\":\\\"demo\\\"}"
              }
            },
            {
              "type": "onlinefile",
              "data": {
                "msgId": "msg-1",
                "elementId": "element-1",
                "fileName": "demo.zip",
                "fileSize": "2048",
                "isDir": false
              }
            },
            {
              "type": "flashtransfer",
              "data": {
                "fileSetId": "flash-set-1"
              }
            }
          ]
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "MFace",
        "Markdown",
        "MiniApp",
        "OnlineFile",
        "FlashTransfer",
    ]
    assert queued.get_messages()[0].summary == "[HappyFace]"
    assert queued.get_messages()[1].content == "# Demo"
    assert queued.get_messages()[2].data == '{"app":"demo"}'
    assert queued.get_messages()[3].file_name == "demo.zip"
    assert queued.get_messages()[4].file_set_id == "flash-set-1"
