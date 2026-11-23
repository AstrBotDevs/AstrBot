"""Test Telegram UTF-16 entity offsets through the real adapter parser."""

import pytest
from telegram import MessageEntity

from astrbot.core.message.components import At, Plain
from astrbot.core.platform.sources.telegram.tg_adapter import TelegramPlatformAdapter


@pytest.mark.parametrize(
    "strip_self,expected",
    [(False, "😀 @Bot hello @Alice"), (True, "😀  hello @Alice")],
)
def test_mentions_after_emoji_preserve_order_and_display_names(strip_self, expected):
    entities = [
        MessageEntity("mention", offset=14, length=6),
        MessageEntity("mention", offset=3, length=4),
    ]

    text, components = TelegramPlatformAdapter._parse_text_entities(
        "😀 @Bot hello @Alice", entities, "bot", strip_self_mention=strip_self
    )

    assert text == expected
    assert [type(component) for component in components] == [Plain, At, Plain, At]
    assert components[0].text == "😀 "
    assert components[1].qq == "bot"
    assert components[1].name == "Bot"
    assert components[2].text == " hello "
    assert components[3].qq == "Alice"
    assert components[3].name == "Alice"


def test_link_after_emoji_keeps_label_and_url():
    entity = MessageEntity(
        "text_link", offset=3, length=4, url="https://docs.example.test"
    )

    text, components = TelegramPlatformAdapter._parse_text_entities(
        "😀 docs", [entity], "bot"
    )

    assert text == "😀 docs (https://docs.example.test)"
    assert len(components) == 1
    assert isinstance(components[0], Plain)
    assert components[0].text == text


def test_formatting_entities_do_not_duplicate_or_remove_plain_text():
    text, components = TelegramPlatformAdapter._parse_text_entities(
        "hello world", [MessageEntity("bold", offset=0, length=5)], "bot"
    )

    assert text == "hello world"
    assert len(components) == 1
    assert components[0].text == "hello world"
