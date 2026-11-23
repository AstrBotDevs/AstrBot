"""Exercise the text-to-image command against real config and event state."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, create_autospec

import pytest

from astrbot.builtin_stars.builtin_commands.commands.t2i import T2ICommand
from astrbot.core.message.components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial,expected_message",
    [(False, "已开启文本转图片模式｡"), (True, "已关闭文本转图片模式｡")],
)
async def test_t2i_toggles_and_persists_only_the_requested_config(
    astrbot_config, monkeypatch, initial, expected_message
):
    astrbot_config["t2i"] = initial
    original_save = type(astrbot_config).save_config
    save = create_autospec(original_save, side_effect=original_save)
    monkeypatch.setattr(type(astrbot_config), "save_config", save)
    context = SimpleNamespace(get_config=Mock(return_value=astrbot_config))
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(user_id="user", nickname="User")
    message.message = [Plain("/t2i")]
    message.message_str = "/t2i"
    event = AstrMessageEvent(
        "/t2i",
        message,
        PlatformMetadata(name="test", description="Test", id="test-instance"),
        "user",
    )

    await T2ICommand(context).t2i(event)

    context.get_config.assert_called_once_with(umo=event.unified_msg_origin)
    assert astrbot_config["t2i"] is (not initial)
    save.assert_called_once_with(astrbot_config)
    persisted = json.loads(
        Path(astrbot_config.config_path).read_text(encoding="utf-8-sig")
    )
    assert persisted["t2i"] is (not initial)
    result = event.get_result()
    assert result is not None
    assert len(result.chain) == 1
    assert result.chain[0].text == expected_message
