"""Verify KOOK mention parsing with isolated role-lookup transport."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.components import At, AtAll, Plain
from astrbot.core.platform.sources.kook.kook_adapter import KookPlatformAdapter


@pytest.mark.asyncio
async def test_user_and_everyone_mentions_preserve_component_order():
    adapter = KookPlatformAdapter.__new__(KookPlatformAdapter)
    adapter.client = SimpleNamespace(
        bot_id="bot-id", bot_nickname="Bot", bot_username="Bot"
    )
    lookup = AsyncMock()
    adapter._roles_cache = SimpleNamespace(has_role_in_channel=lookup)

    components, text = await adapter._convert_text_message_to_component(
        "hello (met)42(met) (met)all(met) world",
        "hello @Alice @all world",
        mention_name_map={"42": "Alice"},
    )

    assert [type(component) for component in components] == [Plain, At, AtAll, Plain]
    assert components[0].text == "hello"
    assert components[1].qq == 42
    assert components[1].name == "Alice"
    assert components[3].text == "world"
    assert text == "hello @Alice @all world"
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_matching_role_resolves_to_bot_and_strips_only_leading_mention():
    adapter = KookPlatformAdapter.__new__(KookPlatformAdapter)
    adapter.client = SimpleNamespace(
        bot_id="bot-id", bot_nickname="Bot", bot_username="Bot"
    )
    lookup = AsyncMock(return_value=True)
    adapter._roles_cache = SimpleNamespace(has_role_in_channel=lookup)

    components, text = await adapter._convert_text_message_to_component(
        "(rol)123(rol) hello", "@Helpers hello", guild_id="99"
    )

    assert len(components) == 2
    assert isinstance(components[0], At)
    assert components[0].qq == "bot-id"
    assert components[0].name == "123"
    assert components[1].text == "hello"
    assert text == "hello"
    lookup.assert_awaited_once_with(123, 99)
