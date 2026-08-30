import json
from types import SimpleNamespace

import pytest

import astrbot.api.message_components as Comp
from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mention_open_id", "mention_name", "message_text", "expected_text"),
    [
        ("bot-open-id", "AstrBot", "/stop", "/stop"),
        ("bot-open-id", "AstrBot", "/plugin_command", "/plugin_command"),
        ("bot-open-id", "AstrBot", "hello", "hello"),
        ("other-open-id", "AstrBot", "/stop", "@AstrBot /stop"),
    ],
)
async def test_convert_msg_normalizes_leading_mentions(
    mention_open_id,
    mention_name,
    message_text,
    expected_text,
):
    adapter = object.__new__(LarkPlatformAdapter)
    adapter.bot_open_id = "bot-open-id"
    adapter.bot_name = "AstrBot"
    captured_messages = []

    async def capture_message(message):
        captured_messages.append(message)

    adapter.handle_msg = capture_message
    mention = SimpleNamespace(
        key="@_user_1",
        id=SimpleNamespace(open_id=mention_open_id),
        name=mention_name,
    )
    message = SimpleNamespace(
        create_time=None,
        chat_type="group",
        chat_id="chat-id",
        parent_id=None,
        mentions=[mention],
        content=json.dumps({"text": f"@_user_1 {message_text}"}),
        message_id="message-id",
        message_type="text",
    )
    event = SimpleNamespace(
        event=SimpleNamespace(
            message=message,
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(open_id="sender-open-id"),
            ),
        ),
    )

    await adapter.convert_msg(event)

    assert len(captured_messages) == 1
    converted_message = captured_messages[0]
    assert converted_message.message_str == expected_text
    assert isinstance(converted_message.message[0], Comp.At)
    assert converted_message.message[0].qq == mention_open_id


def test_build_message_str_preserves_non_self_mentions():
    components = [
        Comp.At(qq="other-open-id", name="Alice"),
        Comp.Plain("/stop"),
        Comp.At(qq="bot-open-id", name="AstrBot"),
    ]

    message_str = LarkPlatformAdapter._build_message_str_from_components(
        components,
        bot_self_id="bot-open-id",
        bot_name="AstrBot",
    )

    assert message_str == "@Alice /stop @AstrBot"


def test_build_message_str_uses_name_only_when_mention_id_is_missing():
    self_mention_without_id = [
        Comp.At(qq="", name="AstrBot"),
        Comp.Plain("hello"),
    ]
    same_name_with_different_id = [
        Comp.At(qq="other-open-id", name="AstrBot"),
        Comp.Plain("hello"),
    ]

    assert (
        LarkPlatformAdapter._build_message_str_from_components(
            self_mention_without_id,
            bot_self_id="bot-open-id",
            bot_name="AstrBot",
        )
        == "hello"
    )
    assert (
        LarkPlatformAdapter._build_message_str_from_components(
            same_name_with_different_id,
            bot_self_id="bot-open-id",
            bot_name="AstrBot",
        )
        == "@AstrBot hello"
    )


def test_build_message_str_keeps_previous_behavior_without_bot_identity():
    components = [
        Comp.At(qq="bot-open-id", name="AstrBot"),
        Comp.Plain("/stop"),
    ]

    message_str = LarkPlatformAdapter._build_message_str_from_components(components)

    assert message_str == "@AstrBot /stop"
    assert LarkPlatformAdapter._build_message_str_from_components([]) == ""
