"""Tests for platform_settings.keep_wake_word_in_prompt.

The option keeps the wake word (wake prefix or @ mention of the bot) in the
message content handed to the AI, while command matching keeps using the
stripped message string.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.config.default import (
    CONFIG_METADATA_2,
    CONFIG_METADATA_3,
    DEFAULT_CONFIG,
)
from astrbot.core.message.components import At, AtAll
from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
from astrbot.core.star.session_plugin_manager import SessionPluginManager

KEY = "keep_wake_word_in_prompt"


async def make_stage(
    keep_wake_word: bool, wake_prefixes: list[str]
) -> WakingCheckStage:
    """Initialize a waking stage with the requested wake-word settings.

    Args:
        keep_wake_word: Value of platform_settings.keep_wake_word_in_prompt.
        wake_prefixes: Configured wake prefixes.

    Returns:
        Initialized waking stage.
    """
    stage = WakingCheckStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "admins_id": [],
                "wake_prefix": wake_prefixes,
                "plugin_set": ["*"],
                "platform_settings": {
                    "friend_message_needs_wake_prefix": False,
                    "keep_wake_word_in_prompt": keep_wake_word,
                },
            },
            astrbot_config_id="test-conf-id",
            db_helper=MagicMock(),
        )
    )
    return stage


def make_event(message_str: str, messages: list | None = None) -> MagicMock:
    """Create a group event mock carrying the given message content.

    Args:
        message_str: Text content delivered by the platform adapter.
        messages: Structured message components, defaulting to none.

    Returns:
        Mocked group message event backed by a real extras mapping.
    """
    extras: dict = {}
    event = MagicMock()
    event.message_str = message_str
    event.extras = extras
    event.is_wake = False
    event.role = "member"
    event.get_sender_id.return_value = "sender-1"
    event.get_self_id.return_value = "bot-1"
    event.get_messages.return_value = messages if messages is not None else []
    event.is_private_chat.return_value = False
    event.get_platform_name.return_value = "test-platform"
    event.set_extra.side_effect = lambda key, value: extras.__setitem__(key, value)
    event.get_extra.side_effect = lambda key=None, default=None: (
        extras if key is None else extras.get(key, default)
    )
    return event


@pytest.fixture(autouse=True)
def no_registered_handlers(monkeypatch):
    """Keep the handler filter loop out of the way of the wake checks."""
    monkeypatch.setattr(
        "astrbot.core.pipeline.waking_check.stage.star_handlers_registry.get_handlers_by_event_type",
        lambda *_args, **_kwargs: [],
    )

    async def return_handlers(_event, handlers):
        return handlers

    monkeypatch.setattr(
        SessionPluginManager,
        "filter_handlers_by_session",
        return_handlers,
    )


@pytest.mark.asyncio
async def test_wake_prefix_is_kept_when_enabled():
    """Store the consumed wake prefix so the AI request can restore it."""
    stage = await make_stage(keep_wake_word=True, wake_prefixes=["/"])

    event = make_event("/help me", messages=[MagicMock()])

    await stage.process(event)

    assert event.is_at_or_wake_command is True
    assert event.message_str == "help me"
    assert event.extras.get("_wake_word") == "/"


@pytest.mark.asyncio
async def test_wake_prefix_is_not_kept_when_disabled():
    """Keep the stripped message string untouched when the option is off."""
    stage = await make_stage(keep_wake_word=False, wake_prefixes=["/"])

    event = make_event("/help me", messages=[MagicMock()])

    await stage.process(event)

    assert event.message_str == "help me"
    assert event.extras.get("_wake_word") == ""


@pytest.mark.asyncio
async def test_bot_mention_is_kept_when_enabled():
    """Restore an @ mention of the bot, which never enters message_str."""
    stage = await make_stage(keep_wake_word=True, wake_prefixes=[])

    event = make_event("", messages=[At(qq="bot-1", name="MyBot")])

    await stage.process(event)

    assert event.is_at_or_wake_command is True
    assert event.extras.get("_wake_word") == "@MyBot"


@pytest.mark.asyncio
async def test_bot_mention_falls_back_to_bot_id_without_name():
    """Fall back to the bot ID when the platform sends an unnamed mention."""
    stage = await make_stage(keep_wake_word=True, wake_prefixes=[])

    event = make_event("", messages=[At(qq="bot-1", name="")])

    await stage.process(event)

    assert event.extras.get("_wake_word") == "@bot-1"


@pytest.mark.asyncio
async def test_at_all_message_does_not_contribute_a_wake_word():
    """Never treat an @all broadcast as a wake word addressed to the bot."""
    stage = await make_stage(keep_wake_word=True, wake_prefixes=[])

    event = make_event("", messages=[AtAll()])

    await stage.process(event)

    assert event.is_wake is True
    assert event.extras.get("_wake_word") == ""


@pytest.mark.asyncio
async def test_private_chat_without_wake_prefix_has_no_wake_word():
    """Private chats woken without a prefix consume no wake word."""
    stage = await make_stage(keep_wake_word=True, wake_prefixes=["/"])

    event = make_event("hello", messages=[MagicMock()])
    event.is_private_chat.return_value = True

    await stage.process(event)

    assert event.extras.get("_wake_word") == ""


def test_option_is_exposed_in_config_and_metadata():
    """Expose the option in defaults and both metadata sets."""
    assert DEFAULT_CONFIG["platform_settings"][KEY] is False
    assert (
        KEY
        in CONFIG_METADATA_2["platform_group"]["metadata"]["platform_settings"]["items"]
    )
    qualified = f"platform_settings.{KEY}"
    assert (
        qualified in CONFIG_METADATA_3["platform_group"]["metadata"]["general"]["items"]
    )


@pytest.mark.parametrize("locale", ["zh-CN", "en-US", "ru-RU", "ja-JP"])
def test_option_is_translated_in_every_locale(locale):
    """Require dashboard translations to describe the option in each locale."""
    path = (
        Path(__file__).resolve().parents[2]
        / "dashboard/src/i18n/locales"
        / locale
        / "features"
    )
    metadata = json.loads((path / "config-metadata.json").read_text(encoding="utf-8"))
    entry = metadata["platform_group"]["general"]["platform_settings"][KEY]

    assert entry["description"]
    assert entry["hint"]

    if locale == "zh-CN":
        assert (
            entry["hint"]
            == CONFIG_METADATA_3["platform_group"]["metadata"]["general"]["items"][
                f"platform_settings.{KEY}"
            ]["hint"]
        )
