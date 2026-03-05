from unittest.mock import AsyncMock, MagicMock

import pytest
from astrbot.api.platform import AstrBotMessage, MessageType, PlatformMetadata, Unknown
from astrbot.api.event import MessageChain
from astrbot.core.message.components import (
    File,
    Image,
    Plain,
    Video,
    At,
    AtAll,
    BaseMessageComponent,
    Json,
    Record,
    Reply,
)


from astrbot.core.platform.sources.kook.kook_event import KookEvent
from astrbot.core.platform.sources.kook.kook_types import KookMessageType, OrderMessage


async def mock_kook_client(upload_asset_return: str, send_text_return: str):
    # 1. Mock 掉整个 KookClient 类
    client = MagicMock()

    client.upload_asset = AsyncMock(return_value=upload_asset_return)
    client.send_text = AsyncMock(return_value=send_text_return)
    return client


def mock_file_message(input: str):
    message = MagicMock(spec=File)
    message.get_file = AsyncMock(return_value=input)
    return message


def mock_record_message(input: str):
    message = MagicMock(spec=Record)
    message.text = input
    message.convert_to_file_path = AsyncMock(return_value=input)
    return message


def mock_astrbot_message():
    message = AstrBotMessage()
    message.type = MessageType.OTHER_MESSAGE
    message.group_id = "test"
    message.session_id = "test"
    message.message_id = "test"
    return message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input_message,upload_asset_return, expected_output, expected_error",
    [
        (
            Image("test image"),
            "test image",
            OrderMessage(
                1,
                text="test image",
                type=KookMessageType.IMAGE,
            ),
            None,
        ),
        (
            Video("test video"),
            "test video",
            OrderMessage(
                1,
                text="test video",
                type=KookMessageType.VIDEO,
            ),
            None,
        ),
        (
            mock_file_message("test file"),
            "test file",
            OrderMessage(
                1,
                text="test file",
                type=KookMessageType.FILE,
            ),
            None,
        ),
        (
            mock_record_message("./tests/file.wav"),
            "./tests/file.wav",
            OrderMessage(
                1,
                text='[{"type": "card", "modules": [{"src": "./tests/file.wav", "title": "./tests/file.wav", "type": "audio"}]}]',
                type=KookMessageType.CARD,
            ),
            None,
        ),
        (
            Plain("test plain"),
            "test plain",
            OrderMessage(
                1,
                text="test plain",
                type=KookMessageType.KMARKDOWN,
            ),
            None,
        ),
        (
            At(qq="test at"),
            "test at",
            OrderMessage(
                1,
                text="(met)test at(met)",
                type=KookMessageType.KMARKDOWN,
            ),
            None,
        ),
        (
            AtAll(qq="all"),
            "test atAll",
            OrderMessage(
                1,
                text="(met)all(met)",
                type=KookMessageType.KMARKDOWN,
            ),
            None,
        ),
        (
            Reply(id="test reply"),
            "test reply",
            OrderMessage(
                1,
                text="",
                type=KookMessageType.KMARKDOWN,
                reply_id="test reply",
            ),
            None,
        ),
        (
            Json(data={"test": "json"}),
            "test json",
            OrderMessage(
                1,
                text='[{"test": "json"}]',
                type=KookMessageType.CARD,
            ),
            None,
        ),
        (
            Unknown(text="test unknown"),
            "test unknown",
            None,
            NotImplementedError,
        ),
    ],
)
async def test_kook_event_warp_message(
    input_message: BaseMessageComponent,
    upload_asset_return: str,
    expected_output: OrderMessage,
    expected_error: type[Exception] | None,
):
    client = await mock_kook_client(
        upload_asset_return,
        "",
    )

    event = KookEvent(
        "",
        mock_astrbot_message(),
        PlatformMetadata(
            name="test",
            id="test",
            description="test",
        ),
        "",
        client,
    )

    if expected_error:
        with pytest.raises(expected_error):
            await event._wrap_message(1, input_message)
        return

    result = await event._wrap_message(1, input_message)
    assert result == expected_output


# @pytest.mark.asyncio
# @pytest.mark.parametrize(
#     "message_chain,send_text_expected_output,expected_error",
#     [
#         (
#             MessageChain(
#                 chain=[
#                     Image(file="test image"),
#                     Plain(text="test plain"),
#                 ],
#             ),
#             ""
#         ),
#     ],
# )
# async def test_kook_event_send():
#     client = await mock_kook_client(
#         "",
#         "",
#     )

#     event = KookEvent(
#         "",
#         mock_astrbot_message(),
#         PlatformMetadata(
#             name="test",
#             id="test",
#             description="test",
#         ),
#         "",
#         client,
#     )

#     await event.send(message=mock_astrbot_message())
