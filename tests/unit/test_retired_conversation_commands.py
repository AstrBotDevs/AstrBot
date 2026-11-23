"""Legacy chat commands remain callable after conversation views move to WebUI."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.builtin_stars.builtin_commands.main import Main
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "command"), [("his", "history"), ("convs", "ls")])
async def test_retired_command_explains_current_location_without_legacy_delegate(
    method: str, command: str
) -> None:
    plugin = Main.__new__(Main)
    plugin.conversation_c = object()
    event = SimpleNamespace(
        send=AsyncMock(),
        plain_result=lambda text: MessageChain([Plain(text)]),
    )

    await getattr(plugin, method)(event, page=3)

    event.send.assert_awaited_once()
    response = event.send.await_args.args[0]
    assert len(response.chain) == 1
    assert isinstance(response.chain[0], Plain)
    text = response.chain[0].text
    assert f"/{command}" in text
    assert "WebUI" in text
    assert "对话管理" in text
