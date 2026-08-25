import json

import pytest

from astrbot.api.platform import PlatformMetadata, Unknown
from astrbot.core.message.components import (
    ActionRow,
    At,
    AtAll,
    BaseMessageComponent,
    Button,
    ButtonStyle,
    CallbackAction,
    Image,
    Json,
    Plain,
    Reply,
    UrlAction,
    Video,
)
from astrbot.core.platform.button_interaction import decode_button_callback
from astrbot.core.platform.sources.kook.kook_event import KookEvent
from astrbot.core.platform.sources.kook.kook_types import KookMessageType, OrderMessage
from tests.test_kook.shared import (
    mock_astrbot_message,
    mock_file_message,
    mock_kook_client,
    mock_record_message,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input_message,upload_asset_return, expected_output, expected_error",
    [
        (
            Image("test image"),
            "test image",
            OrderMessage(
                index=1,
                text="test image",
                type=KookMessageType.IMAGE,
            ),
            None,
        ),
        (
            Video("test video"),
            "test video",
            OrderMessage(
                index=1,
                text="test video",
                type=KookMessageType.VIDEO,
            ),
            None,
        ),
        (
            mock_file_message("test file"),
            "test file",
            OrderMessage(
                index=1,
                text="test file",
                type=KookMessageType.FILE,
            ),
            None,
        ),
        (
            mock_record_message("./tests/file.wav"),
            "./tests/file.wav",
            OrderMessage(
                index=1,
                text='[{"type": "card", "modules": [{"type": "audio", "src": "./tests/file.wav", "title": "./tests/file.wav"}]}]',
                type=KookMessageType.CARD,
            ),
            None,
        ),
        (
            Plain("test plain"),
            "test plain",
            OrderMessage(
                index=1,
                text="test plain",
                type=KookMessageType.KMARKDOWN,
            ),
            None,
        ),
        (
            At(qq="test at"),
            "test at",
            OrderMessage(
                index=1,
                text="(met)test at(met)",
                type=KookMessageType.KMARKDOWN,
            ),
            None,
        ),
        (
            AtAll(qq="all"),
            "test atAll",
            OrderMessage(
                index=1,
                text="(met)all(met)",
                type=KookMessageType.KMARKDOWN,
            ),
            None,
        ),
        (
            Reply(id="test reply"),
            "test reply",
            OrderMessage(
                index=1,
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
                index=1,
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
    expected_error: type[BaseException] | None,
):
    client = mock_kook_client(
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

    expected_output_text: str | list | dict = expected_output.text
    is_json_text = False
    try:
        expected_output_text = json.loads(expected_output_text)
        is_json_text = True
    except (TypeError, json.JSONDecodeError):
        pass

    if is_json_text:
        assert json.loads(result.text) == expected_output_text
    else:
        assert result.text == expected_output_text

    assert result.index == expected_output.index
    assert result.type == expected_output.type
    assert result.reply_id == expected_output.reply_id


@pytest.mark.asyncio
async def test_kook_event_renders_portable_buttons():
    client = mock_kook_client("", "")
    event = KookEvent(
        "",
        mock_astrbot_message(),
        PlatformMetadata(name="test", id="test", description="test"),
        "",
        client,
    )
    row = ActionRow(
        buttons=[
            Button(
                id="approve",
                label="Approve",
                style=ButtonStyle.SUCCESS,
                action=CallbackAction(data={"request_id": 42}),
            ),
            Button(
                id="docs",
                label="Documentation",
                style=ButtonStyle.DANGER,
                action=UrlAction(url="https://example.com/docs"),
            ),
        ]
    )

    result = await event._wrap_message(0, row)

    assert result.type == KookMessageType.CARD
    card = json.loads(result.text)[0]
    callback_button, url_button = card["modules"][0]["elements"]
    assert callback_button["click"] == "return-val"
    assert callback_button["theme"] == "success"
    assert decode_button_callback(callback_button["value"]) == (
        "approve",
        {"request_id": 42},
    )
    assert url_button == {
        "type": "button",
        "text": "Documentation",
        "theme": "danger",
        "value": "https://example.com/docs",
        "click": "link",
    }


@pytest.mark.asyncio
async def test_kook_event_splits_action_rows_at_four_buttons():
    client = mock_kook_client("", "")
    event = KookEvent(
        "",
        mock_astrbot_message(),
        PlatformMetadata(name="test", id="test", description="test"),
        "",
        client,
    )
    row = ActionRow(
        buttons=[
            Button(id=f"button-{index}", label=str(index), action=CallbackAction())
            for index in range(5)
        ]
    )

    result = await event._wrap_message(0, row)

    modules = json.loads(result.text)[0]["modules"]
    assert [len(module["elements"]) for module in modules] == [4, 1]
