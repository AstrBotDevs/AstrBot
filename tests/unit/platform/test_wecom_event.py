from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wechatpy.exceptions import WeChatClientException

from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Image, Plain, Record, Video
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.sources.wecom.wecom_event import WecomPlatformEvent
from astrbot.core.platform.sources.wecom.wecom_kf_message import WeChatKFMessage


def _build_message() -> AstrBotMessage:
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(user_id="user-1", nickname="Sender")
    message.self_id = "bot-1"
    message.session_id = "user-1"
    message.message_id = "msg-1"
    message.message = [Plain("hello")]
    message.message_str = "hello"
    return message


def _build_event(client) -> WecomPlatformEvent:
    return WecomPlatformEvent(
        message_str="hello",
        message_obj=_build_message(),
        platform_meta=PlatformMetadata(
            name="wecom",
            description="WeCom",
            id="wecom-test",
            support_streaming_message=False,
        ),
        session_id="user-1",
        client=client,
    )


class FakeKFMessage(WeChatKFMessage):
    def __init__(self) -> None:
        super().__init__(client=SimpleNamespace())
        self.send_text = MagicMock()
        self.send_image = MagicMock()


@pytest.mark.asyncio
async def test_wecom_event_split_plain_prefers_punctuation_boundaries():
    event = _build_event(SimpleNamespace())
    text = ("a" * 2047) + "。" + ("b" * 10)

    chunks = await event.split_plain(text)

    assert chunks == [("a" * 2047) + "。", "b" * 10]


@pytest.mark.asyncio
async def test_wecom_event_send_kf_text_falls_back_on_40096():
    kf_message = FakeKFMessage()
    kf_message.send_text.side_effect = WeChatClientException(
        40096,
        "invalid external userid",
    )
    client = SimpleNamespace(
        kf_message=kf_message,
        message=SimpleNamespace(send_text=MagicMock()),
    )
    event = _build_event(client)

    with (
        patch(
            "astrbot.core.platform.sources.wecom.wecom_event.asyncio.sleep",
            new_callable=AsyncMock,
        ),
        patch.object(
            AstrMessageEvent,
            "send",
            AsyncMock(return_value=None),
        ) as parent_send,
    ):
        await event.send(MessageChain([Plain("hello")]))

    kf_message.send_text.assert_called_once_with("user-1", "bot-1", "hello")
    client.message.send_text.assert_called_once_with("bot-1", "user-1", "hello")
    parent_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_wecom_event_send_kf_text_falls_back_on_40096_for_each_split_chunk():
    kf_message = FakeKFMessage()
    kf_message.send_text.side_effect = WeChatClientException(
        40096,
        "invalid external userid",
    )
    client = SimpleNamespace(
        kf_message=kf_message,
        message=SimpleNamespace(send_text=MagicMock()),
    )
    event = _build_event(client)

    with (
        patch.object(
            event, "split_plain", AsyncMock(return_value=["part 1", "part 2"])
        ),
        patch(
            "astrbot.core.platform.sources.wecom.wecom_event.asyncio.sleep",
            new_callable=AsyncMock,
        ),
        patch.object(
            AstrMessageEvent,
            "send",
            AsyncMock(return_value=None),
        ) as parent_send,
    ):
        await event.send(MessageChain([Plain("long text")]))

    assert kf_message.send_text.call_args_list == [
        (("user-1", "bot-1", "part 1"),),
        (("user-1", "bot-1", "part 2"),),
    ]
    assert client.message.send_text.call_args_list == [
        (("bot-1", "user-1", "part 1"),),
        (("bot-1", "user-1", "part 2"),),
    ]
    parent_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_wecom_event_send_kf_image_failure_sends_error_text(
    monkeypatch, tmp_path
):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"png")
    image = Image(file=str(image_path))
    kf_message = FakeKFMessage()
    client = SimpleNamespace(
        kf_message=kf_message,
        media=SimpleNamespace(
            upload=MagicMock(side_effect=RuntimeError("upload failed"))
        ),
    )
    event = _build_event(client)

    with (
        patch.object(
            Image,
            "convert_to_file_path",
            AsyncMock(return_value=str(image_path)),
        ),
        patch.object(
            AstrMessageEvent,
            "send",
            AsyncMock(return_value=None),
        ),
        patch.object(
            WecomPlatformEvent,
            "send",
            wraps=event.send,
        ) as recursive_send,
    ):
        await event.send(MessageChain([image]))

    assert recursive_send.await_count == 1
    kf_message.send_text.assert_called_once_with(
        "user-1", "bot-1", "微信客服上传图片失败: upload failed"
    )
    kf_message.send_image.assert_not_called()


@pytest.mark.asyncio
async def test_wecom_event_send_plain_in_app_mode_splits_and_sends_chunks():
    client = SimpleNamespace(
        message=SimpleNamespace(send_text=MagicMock()),
    )
    event = _build_event(client)

    with (
        patch.object(
            event, "split_plain", AsyncMock(return_value=["part 1", "part 2"])
        ),
        patch(
            "astrbot.core.platform.sources.wecom.wecom_event.asyncio.sleep",
            new_callable=AsyncMock,
        ),
        patch.object(
            AstrMessageEvent,
            "send",
            AsyncMock(return_value=None),
        ) as parent_send,
    ):
        await event.send(MessageChain([Plain("long text")]))

    assert client.message.send_text.call_args_list == [
        (("bot-1", "user-1", "part 1"),),
        (("bot-1", "user-1", "part 2"),),
    ]
    parent_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_wecom_event_send_app_image_failure_sends_error_text(
    monkeypatch, tmp_path
):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"png")
    image = Image(file=str(image_path))
    client = SimpleNamespace(
        message=SimpleNamespace(send_image=MagicMock(), send_text=MagicMock()),
        media=SimpleNamespace(
            upload=MagicMock(side_effect=RuntimeError("upload failed"))
        ),
    )
    event = _build_event(client)

    with (
        patch.object(
            Image,
            "convert_to_file_path",
            AsyncMock(return_value=str(image_path)),
        ),
        patch.object(
            AstrMessageEvent,
            "send",
            AsyncMock(return_value=None),
        ),
        patch.object(
            WecomPlatformEvent,
            "send",
            wraps=event.send,
        ) as recursive_send,
    ):
        await event.send(MessageChain([image]))

    assert recursive_send.await_count == 1
    client.message.send_text.assert_called_once_with(
        "bot-1", "user-1", "企业微信上传图片失败: upload failed"
    )
    client.message.send_image.assert_not_called()


@pytest.mark.asyncio
async def test_wecom_event_send_kf_record_removes_temp_amr_and_warns_on_cleanup_failure(
    monkeypatch,
    tmp_path,
):
    source_path = tmp_path / "source.wav"
    source_path.write_bytes(b"wav")
    amr_path = tmp_path / "converted.amr"
    amr_path.write_bytes(b"amr")
    record = Record(file=str(source_path), url=str(source_path))
    kf_message = FakeKFMessage()
    kf_message.send_voice = MagicMock()
    client = SimpleNamespace(
        kf_message=kf_message,
        media=SimpleNamespace(upload=MagicMock(return_value={"media_id": "voice-1"})),
    )
    event = _build_event(client)
    logger_warning = MagicMock()

    with (
        patch.object(
            Record,
            "convert_to_file_path",
            AsyncMock(return_value=str(source_path)),
        ),
        patch(
            "astrbot.core.platform.sources.wecom.wecom_event.convert_audio_to_amr",
            AsyncMock(return_value=str(amr_path)),
        ),
        patch(
            "astrbot.core.platform.sources.wecom.wecom_event.os.remove",
            side_effect=OSError("cleanup failed"),
        ),
        patch.object(
            AstrMessageEvent,
            "send",
            AsyncMock(return_value=None),
        ) as parent_send,
        patch(
            "astrbot.core.platform.sources.wecom.wecom_event.logger.warning",
            logger_warning,
        ),
    ):
        await event.send(MessageChain([record]))

    kf_message.send_voice.assert_called_once_with("user-1", "bot-1", "voice-1")
    logger_warning.assert_called_once()
    parent_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_wecom_event_send_app_file_failure_sends_error_text(
    monkeypatch, tmp_path
):
    file_path = tmp_path / "report.txt"
    file_path.write_bytes(b"report")
    file_comp = File(name="report.txt", file=str(file_path))
    client = SimpleNamespace(
        message=SimpleNamespace(send_file=MagicMock(), send_text=MagicMock()),
        media=SimpleNamespace(
            upload=MagicMock(side_effect=RuntimeError("upload failed"))
        ),
    )
    event = _build_event(client)

    with (
        patch.object(
            File,
            "get_file",
            AsyncMock(return_value=str(file_path)),
        ),
        patch.object(
            AstrMessageEvent,
            "send",
            AsyncMock(return_value=None),
        ),
        patch.object(
            WecomPlatformEvent,
            "send",
            wraps=event.send,
        ) as recursive_send,
    ):
        await event.send(MessageChain([file_comp]))

    assert recursive_send.await_count == 1
    client.message.send_text.assert_called_once_with(
        "bot-1", "user-1", "企业微信上传文件失败: upload failed"
    )
    client.message.send_file.assert_not_called()


@pytest.mark.asyncio
async def test_wecom_event_send_kf_file_failure_sends_error_text(monkeypatch, tmp_path):
    file_path = tmp_path / "report.txt"
    file_path.write_bytes(b"report")
    file_comp = File(name="report.txt", file=str(file_path))
    kf_message = FakeKFMessage()
    kf_message.send_file = MagicMock()
    client = SimpleNamespace(
        kf_message=kf_message,
        media=SimpleNamespace(
            upload=MagicMock(side_effect=RuntimeError("upload failed"))
        ),
    )
    event = _build_event(client)

    with (
        patch.object(
            File,
            "get_file",
            AsyncMock(return_value=str(file_path)),
        ),
        patch.object(
            AstrMessageEvent,
            "send",
            AsyncMock(return_value=None),
        ),
        patch.object(
            WecomPlatformEvent,
            "send",
            wraps=event.send,
        ) as recursive_send,
    ):
        await event.send(MessageChain([file_comp]))

    assert recursive_send.await_count == 1
    kf_message.send_text.assert_called_once_with(
        "user-1", "bot-1", "微信客服上传文件失败: upload failed"
    )
    kf_message.send_file.assert_not_called()


@pytest.mark.asyncio
async def test_wecom_event_send_kf_video_failure_sends_error_text(
    monkeypatch, tmp_path
):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    video_comp = Video(file=str(video_path))
    kf_message = FakeKFMessage()
    kf_message.send_video = MagicMock()
    client = SimpleNamespace(
        kf_message=kf_message,
        media=SimpleNamespace(
            upload=MagicMock(side_effect=RuntimeError("upload failed"))
        ),
    )
    event = _build_event(client)

    with (
        patch.object(
            Video,
            "convert_to_file_path",
            AsyncMock(return_value=str(video_path)),
        ),
        patch.object(
            AstrMessageEvent,
            "send",
            AsyncMock(return_value=None),
        ),
        patch.object(
            WecomPlatformEvent,
            "send",
            wraps=event.send,
        ) as recursive_send,
    ):
        await event.send(MessageChain([video_comp]))

    assert recursive_send.await_count == 1
    kf_message.send_text.assert_called_once_with(
        "user-1", "bot-1", "微信客服上传视频失败: upload failed"
    )
    kf_message.send_video.assert_not_called()


@pytest.mark.asyncio
async def test_wecom_event_send_warns_for_unsupported_component():
    client = SimpleNamespace(message=SimpleNamespace(send_text=MagicMock()))
    event = _build_event(client)
    logger_warning = MagicMock()
    unsupported = SimpleNamespace(type="unknown_component")

    with (
        patch.object(
            AstrMessageEvent,
            "send",
            AsyncMock(return_value=None),
        ) as parent_send,
        patch(
            "astrbot.core.platform.sources.wecom.wecom_event.logger.warning",
            logger_warning,
        ),
    ):
        await event.send(MessageChain([unsupported]))

    logger_warning.assert_called_once()
    parent_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_wecom_event_send_streaming_aggregates_plain_segments():
    event = _build_event(SimpleNamespace())
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
async def test_wecom_event_send_streaming_aggregates_mixed_segments_into_single_send():
    event = _build_event(SimpleNamespace())
    event.send = AsyncMock()

    async def generator():
        yield MessageChain([Plain("Hello "), Image(file="img.png", url="img.png")])
        yield MessageChain([Plain("world")])

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value="stream-finished"),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator())

    assert result == "stream-finished"
    event.send.assert_awaited_once()
    sent_chain = event.send.await_args.args[0]
    assert len(sent_chain.chain) == 2
    assert isinstance(sent_chain.chain[0], Plain)
    assert sent_chain.chain[0].text == "Hello world"
    assert isinstance(sent_chain.chain[1], Image)
    parent_send_streaming.assert_awaited_once()


@pytest.mark.asyncio
async def test_wecom_event_send_streaming_returns_none_for_empty_generator():
    event = _build_event(SimpleNamespace())
    event.send = AsyncMock()

    async def generator():
        if False:
            yield MessageChain().message("never")

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value="unused"),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator())

    assert result is None
    event.send.assert_not_awaited()
    parent_send_streaming.assert_not_awaited()
