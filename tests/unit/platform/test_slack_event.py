from unittest.mock import AsyncMock, patch

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.sources.slack.slack_event import SlackMessageEvent


def _build_event(*, group_id: str | None = None) -> SlackMessageEvent:
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE if group_id else MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(user_id="U1", nickname="Sender")
    message.self_id = "B1"
    message.session_id = group_id or "U1"
    message.message_id = "msg-1"
    message.message = [Plain("hello")]
    message.message_str = "hello"
    if group_id:
        message.group_id = group_id

    return SlackMessageEvent(
        message_str=message.message_str,
        message_obj=message,
        platform_meta=PlatformMetadata(
            name="slack",
            description="Slack",
            id="test_slack",
            support_streaming_message=False,
        ),
        session_id=message.session_id,
        web_client=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_slack_from_segment_to_block_uploads_local_image_and_returns_slack_file():
    web_client = AsyncMock()
    web_client.files_upload_v2.return_value = {
        "ok": True,
        "files": [{"url_private": "https://slack.example/files/local.png"}],
    }

    with patch.object(
        Image, "convert_to_file_path", AsyncMock(return_value="C:/tmp/local.png")
    ) as convert_to_file_path:
        block = await SlackMessageEvent._from_segment_to_slack_block(
            Image(file="local.png"),
            web_client,
        )

    convert_to_file_path.assert_awaited_once()
    web_client.files_upload_v2.assert_awaited_once_with(
        file="C:/tmp/local.png",
        filename="local.png",
    )
    assert block == {
        "type": "image",
        "slack_file": {"url": "https://slack.example/files/local.png"},
        "alt_text": "图片",
    }


@pytest.mark.asyncio
async def test_slack_from_segment_to_block_uses_remote_image_url_without_upload():
    web_client = AsyncMock()

    block = await SlackMessageEvent._from_segment_to_slack_block(
        Image.fromURL("https://example.com/remote.png"),
        web_client,
    )

    web_client.files_upload_v2.assert_not_awaited()
    assert block == {
        "type": "image",
        "image_url": "https://example.com/remote.png",
        "alt_text": "图片",
    }


@pytest.mark.asyncio
async def test_slack_from_segment_to_block_returns_failure_block_for_file_upload_error():
    web_client = AsyncMock()
    web_client.files_upload_v2.return_value = {"ok": False, "error": "upload failed"}

    block = await SlackMessageEvent._from_segment_to_slack_block(
        File(name="report.pdf", url="https://example.com/report.pdf"),
        web_client,
    )

    web_client.files_upload_v2.assert_awaited_once_with(
        file="https://example.com/report.pdf",
        filename="report.pdf",
    )
    assert block == {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "文件上传失败"},
    }


@pytest.mark.asyncio
async def test_slack_from_segment_to_block_returns_failure_block_for_local_image_upload_error():
    web_client = AsyncMock()
    web_client.files_upload_v2.return_value = {"ok": False, "error": "upload failed"}

    with patch.object(
        Image, "convert_to_file_path", AsyncMock(return_value="C:/tmp/local.png")
    ):
        block = await SlackMessageEvent._from_segment_to_slack_block(
            Image(file="local.png"),
            web_client,
        )

    web_client.files_upload_v2.assert_awaited_once_with(
        file="C:/tmp/local.png",
        filename="local.png",
    )
    assert block == {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "图片上传失败"},
    }


@pytest.mark.asyncio
async def test_slack_from_segment_to_block_returns_permalink_block_for_file_upload_success():
    web_client = AsyncMock()
    web_client.files_upload_v2.return_value = {
        "ok": True,
        "files": [{"permalink": "https://slack.example/files/report.pdf"}],
    }

    block = await SlackMessageEvent._from_segment_to_slack_block(
        File(name="report.pdf", url="C:/tmp/report.pdf"),
        web_client,
    )

    web_client.files_upload_v2.assert_awaited_once_with(
        file="C:/tmp/report.pdf",
        filename="report.pdf",
    )
    assert block == {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "文件: <https://slack.example/files/report.pdf|report.pdf>",
        },
    }


@pytest.mark.asyncio
async def test_slack_parse_slack_blocks_flushes_plain_segments_and_plain_only_text():
    web_client = AsyncMock()
    image = Image.fromURL("https://example.com/image.png")

    blocks, text = await SlackMessageEvent._parse_slack_blocks(
        MessageChain([Plain("Hello "), Plain("world"), image]),
        web_client,
    )
    plain_blocks, plain_text = await SlackMessageEvent._parse_slack_blocks(
        MessageChain([Plain("Only text")]),
        web_client,
    )

    assert blocks == [
        {"type": "section", "text": {"type": "mrkdwn", "text": "Hello world"}},
        {
            "type": "image",
            "image_url": "https://example.com/image.png",
            "alt_text": "图片",
        },
    ]
    assert text == ""
    assert plain_blocks == [
        {"type": "section", "text": {"type": "mrkdwn", "text": "Only text"}}
    ]
    assert plain_text == ""


@pytest.mark.asyncio
async def test_slack_send_falls_back_to_plain_text_when_block_send_fails():
    event = _build_event(group_id="C1")
    event.web_client.chat_postMessage = AsyncMock(
        side_effect=[RuntimeError("boom"), None]
    )
    chain = MessageChain(
        [
            Plain("Hello"),
            File(name="report.pdf", file="C:/tmp/report.pdf"),
            Image.fromURL("https://example.com/image.png"),
        ]
    )

    await event.send(chain)

    assert event.web_client.chat_postMessage.await_count == 2
    first_call = event.web_client.chat_postMessage.await_args_list[0]
    second_call = event.web_client.chat_postMessage.await_args_list[1]
    assert first_call.kwargs["channel"] == "C1"
    assert first_call.kwargs["blocks"] is not None
    assert second_call.kwargs == {
        "channel": "C1",
        "text": "Hello [文件: report.pdf]  [图片] ",
    }


@pytest.mark.asyncio
async def test_slack_send_uses_sender_id_for_direct_messages():
    event = _build_event()
    event.web_client.chat_postMessage = AsyncMock()

    await event.send(MessageChain([Plain("hello direct")]))

    event.web_client.chat_postMessage.assert_awaited_once_with(
        channel="U1",
        text="",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "hello direct"},
            }
        ],
    )


@pytest.mark.asyncio
async def test_slack_send_streaming_aggregates_non_fallback_output():
    event = _build_event()
    event.send = AsyncMock()

    async def generator():
        yield MessageChain().message("Hello ")
        yield MessageChain().message("world")

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value="stream-finished"),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator())

    assert result == "stream-finished"
    event.send.assert_awaited_once()
    sent_chain = event.send.await_args.args[0]
    assert len(sent_chain.chain) == 1
    assert isinstance(sent_chain.chain[0], Plain)
    assert sent_chain.chain[0].text == "Hello world"
    parent_send_streaming.assert_awaited_once()


@pytest.mark.asyncio
async def test_slack_send_streaming_fallback_sends_text_chunks_and_non_plain_segments():
    event = _build_event()
    event.send = AsyncMock()
    image = Image.fromURL("https://example.com/image.png")

    async def generator():
        yield MessageChain([Plain("First~Second")])
        yield MessageChain([Plain(" last~")])
        yield MessageChain([image])

    with (
        patch.object(
            AstrMessageEvent,
            "send_streaming",
            AsyncMock(return_value="fallback-finished"),
        ) as parent_send_streaming,
        patch(
            "astrbot.core.platform.sources.slack.slack_event.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        result = await event.send_streaming(generator(), use_fallback=True)

    assert result == "fallback-finished"
    assert event.send.await_count == 3
    first_chain = event.send.await_args_list[0].args[0]
    second_chain = event.send.await_args_list[1].args[0]
    third_chain = event.send.await_args_list[2].args[0]
    assert first_chain.chain[0].text == "First~"
    assert second_chain.chain[0].text == "Second last~"
    assert third_chain.chain == [image]
    parent_send_streaming.assert_awaited_once()


@pytest.mark.asyncio
async def test_slack_send_streaming_fallback_flushes_trailing_plain_text_without_punctuation():
    event = _build_event()
    event.send = AsyncMock()

    async def generator():
        yield MessageChain([Plain("tail without terminator")])

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value="fallback-finished"),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator(), use_fallback=True)

    assert result == "fallback-finished"
    event.send.assert_awaited_once()
    sent_chain = event.send.await_args.args[0]
    assert sent_chain.chain[0].text == "tail without terminator"
    parent_send_streaming.assert_awaited_once()


@pytest.mark.asyncio
async def test_slack_send_streaming_non_fallback_ignores_empty_generator():
    event = _build_event()
    event.send = AsyncMock()

    async def generator():
        if False:
            yield MessageChain().message("never")

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value="stream-empty"),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator())

    assert result is None
    event.send.assert_not_awaited()
    parent_send_streaming.assert_not_awaited()


@pytest.mark.asyncio
async def test_slack_get_group_builds_members_and_falls_back_on_member_lookup_failure():
    event = _build_event(group_id="C1")
    event.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"name": "general", "creator": "owner-1"}}
    )
    event.web_client.conversations_members = AsyncMock(
        return_value={"members": ["U1", "U2"]}
    )

    async def users_info(*, user: str):
        if user == "U1":
            return {"user": {"real_name": "Alice"}}
        raise RuntimeError("lookup failed")

    event.web_client.users_info = AsyncMock(side_effect=users_info)

    group = await event.get_group()

    assert group is not None
    assert group.group_id == "C1"
    assert group.group_name == "general"
    assert group.group_owner == "owner-1"
    assert [member.nickname for member in group.members] == ["Alice", "U2"]


@pytest.mark.asyncio
async def test_slack_get_group_returns_none_when_channel_lookup_fails():
    event = _build_event(group_id="C1")
    event.web_client.conversations_info = AsyncMock(side_effect=RuntimeError("boom"))

    group = await event.get_group()

    assert group is None


@pytest.mark.asyncio
async def test_slack_get_group_uses_explicit_group_id_without_event_group_context():
    event = _build_event()
    event.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"name": "alerts", "creator": "owner-2"}}
    )
    event.web_client.conversations_members = AsyncMock(return_value={"members": ["U3"]})
    event.web_client.users_info = AsyncMock(
        return_value={"user": {"name": "botops-user"}}
    )

    group = await event.get_group("C-explicit")

    assert group is not None
    assert group.group_id == "C-explicit"
    assert group.group_name == "alerts"
    assert group.group_owner == "owner-2"
    assert [member.nickname for member in group.members] == ["botops-user"]


@pytest.mark.asyncio
async def test_slack_get_group_returns_none_without_any_group_context():
    event = _build_event()

    group = await event.get_group()

    assert group is None
