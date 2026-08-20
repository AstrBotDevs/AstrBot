"""Tests for the wake-prefix decision in WakingCheckStage.

Regression tests for #9341: mobile QQ yellow-face emojis are serialized by
some OneBot implementations as a ``face`` segment followed by a text segment
holding the face's display name (e.g. ``/干饭``). Because ``message_str`` only
concatenates text segments, that face-attached text used to be mistaken for a
wake prefix and woke the LLM.
"""

import pytest
import pytest_asyncio

from astrbot.core.message.components import At, Face, Image, Plain, Reply
from astrbot.core.pipeline.waking_check import stage as waking_stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata

SELF_ID = "123456"


class FakeContext:
    """Minimal PipelineContext substitute for WakingCheckStage."""

    def __init__(self) -> None:
        self.astrbot_config = {
            "platform_settings": {},
            "admins_id": [],
            "wake_prefix": ["/"],
            "plugin_set": ["*"],
        }
        self.plugin_manager = None


def make_event(
    components: list,
    message_str: str,
    message_type: MessageType = MessageType.GROUP_MESSAGE,
) -> AstrMessageEvent:
    abm = AstrBotMessage()
    abm.type = message_type
    abm.self_id = SELF_ID
    abm.session_id = "test-session"
    abm.message_id = "1"
    abm.sender = MessageMember(user_id="10000", nickname="tester")
    abm.message = components
    abm.message_str = message_str
    abm.raw_message = None
    if message_type == MessageType.GROUP_MESSAGE:
        abm.group_id = "654321"
    meta = PlatformMetadata(name="aiocqhttp", description="test", id="aiocqhttp")
    return AstrMessageEvent(
        message_str=message_str,
        message_obj=abm,
        platform_meta=meta,
        session_id="test-session",
    )


@pytest_asyncio.fixture
async def stage(monkeypatch) -> waking_stage.WakingCheckStage:
    inst = waking_stage.WakingCheckStage()
    await inst.initialize(FakeContext())

    async def passthrough(event, handlers):
        return handlers

    monkeypatch.setattr(
        waking_stage.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        waking_stage.SessionPluginManager,
        "filter_handlers_by_session",
        passthrough,
    )
    return inst


@pytest.mark.asyncio
async def test_face_attached_text_does_not_wake(stage):
    """A face segment's auto-attached name text must not count as a prefix."""
    event = make_event([Face(id=475), Plain("/干饭")], "/干饭")
    await stage.process(event)
    assert not event.is_wake
    assert not event.is_at_or_wake_command


@pytest.mark.asyncio
async def test_reply_then_face_attached_text_does_not_wake(stage):
    """Replying to a non-bot message with a face emoji must not wake either."""
    event = make_event(
        [Reply(id="42", sender_id="20000"), Face(id=475), Plain("/干饭")],
        "/干饭",
    )
    await stage.process(event)
    assert not event.is_wake


@pytest.mark.asyncio
async def test_plain_command_still_wakes(stage):
    event = make_event([Plain("/help")], "/help")
    await stage.process(event)
    assert event.is_wake
    assert event.message_str == "help"


@pytest.mark.asyncio
async def test_media_with_command_caption_still_wakes(stage):
    """Pasting an image and then typing a command must keep waking the bot."""
    event = make_event([Image(file="a.png"), Plain("/ocr")], "/ocr")
    await stage.process(event)
    assert event.is_wake
    assert event.message_str == "ocr"


@pytest.mark.asyncio
async def test_at_bot_then_command_still_wakes(stage):
    event = make_event([At(qq=SELF_ID), Plain("/help")], "/help")
    await stage.process(event)
    assert event.is_wake


@pytest.mark.asyncio
async def test_face_text_then_at_bot_still_wakes(stage):
    """`[表情] 你好 @bot`: the prefix path skips the face text, yet the At
    branch must still wake the bot."""
    event = make_event(
        [Face(id=475), Plain("/干饭 你好"), At(qq=SELF_ID)],
        "/干饭 你好",
    )
    await stage.process(event)
    assert event.is_wake
    assert event.is_at_or_wake_command


@pytest.mark.asyncio
async def test_face_text_then_at_other_does_not_wake(stage):
    """`[表情] 你好 @someone-else`: face-attached text is not a command and
    the At targets another member, so the bot must stay asleep."""
    event = make_event(
        [Face(id=475), Plain("/干饭 你好"), At(qq="99999")],
        "/干饭 你好",
    )
    await stage.process(event)
    assert not event.is_wake


@pytest.mark.asyncio
async def test_face_after_command_text_still_wakes(stage):
    """A trailing face emoji after a real command must not block waking."""
    event = make_event([Plain("/help"), Face(id=475)], "/help")
    await stage.process(event)
    assert event.is_wake


@pytest.mark.asyncio
async def test_private_face_attached_text_needs_no_false_wake(stage):
    """With friend_message_needs_wake_prefix, face text must not satisfy it."""
    stage.friend_message_needs_wake_prefix = True
    event = make_event(
        [Face(id=475), Plain("/干饭")],
        "/干饭",
        message_type=MessageType.FRIEND_MESSAGE,
    )
    await stage.process(event)
    assert not event.is_wake
