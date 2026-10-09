from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from astrbot_sdk.errors import InvalidRequest, NotFound
from astrbot_sdk.message_components import Plain
from astrbot_sdk.messages import MessageChain

from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.sdk_bridge.services.db import DbService
from astrbot.core.star.sdk_bridge.services.event_inject import EventInjectService
from astrbot.core.star.sdk_bridge.services.handlers import HandlerRegisterService
from astrbot.core.star.sdk_bridge.services.plugins import PluginLifecycleService
from astrbot.core.star.star_handler import star_handlers_registry


def _row(data: dict) -> MagicMock:
    row = MagicMock()
    row.model_dump.return_value = dict(data)
    return row


@pytest.mark.asyncio
async def test_db_service_umo_aliases() -> None:
    context = MagicMock()
    context.get_db.return_value.get_umo_aliases = AsyncMock(
        return_value=[_row({"umo": "a:b:c", "user_alias": "Moon"})],
    )
    service = DbService(context)
    result = await service.handle("get_umo_aliases", {"umos": ["a:b:c"]})
    assert result["aliases"] == [{"umo": "a:b:c", "user_alias": "Moon"}]
    context.get_db.return_value.get_umo_aliases.assert_awaited_once_with(["a:b:c"])

    with pytest.raises(NotFound):
        await service.handle("drop_table", {})


@pytest.mark.asyncio
async def test_db_service_conversations_strip_content() -> None:
    context = MagicMock()
    context.get_db.return_value.get_conversations = AsyncMock(
        return_value=[
            _row(
                {
                    "conversation_id": "cid-1",
                    "user_id": "u1",
                    "content": [{"role": "user"}],
                }
            )
        ],
    )
    service = DbService(context)
    result = await service.handle(
        "get_conversations",
        {"user_id": "u1", "platform_id": None},
    )
    assert result["conversations"] == [{"conversation_id": "cid-1", "user_id": "u1"}]
    context.get_db.return_value.get_conversations.assert_awaited_once_with(
        user_id="u1",
        platform_id=None,
    )


@pytest.mark.asyncio
async def test_handler_register_service_command() -> None:
    bridge = MagicMock()
    bridge.module_path = "sdk_bridge.fake_plugin"
    bridge._handler_full_names = []
    bridge._make_command_stub.return_value = AsyncMock()
    service = HandlerRegisterService(bridge)

    result = await service.handle(
        "register",
        {"handler_id": "dyn_cmd_1", "command_name": "mycmd", "desc": "d"},
    )
    assert result == {"registered": True}
    full_name = "sdk_bridge.fake_plugin_dyn_cmd_1"
    try:
        handler_md = star_handlers_registry.star_handlers_map[full_name]
        assert isinstance(handler_md.event_filters[0], CommandFilter)
        assert full_name in bridge._handler_full_names
    finally:
        star_handlers_registry.star_handlers_map.pop(full_name, None)

    result = await service.handle(
        "register",
        {"handler_id": "dyn_cmd_2", "command_name": "^re", "use_regex": True},
    )
    assert result == {"registered": True}
    full_name = "sdk_bridge.fake_plugin_dyn_cmd_2"
    try:
        handler_md = star_handlers_registry.star_handlers_map[full_name]
        assert isinstance(handler_md.event_filters[0], RegexFilter)
    finally:
        star_handlers_registry.star_handlers_map.pop(full_name, None)

    with pytest.raises(InvalidRequest):
        await service.handle("register", {"handler_id": "", "command_name": "x"})
    with pytest.raises(NotFound):
        await service.handle("unregister", {})


@pytest.mark.asyncio
async def test_event_inject_service_queues_event() -> None:
    context = MagicMock()
    context.platform_manager.platform_insts = []
    context._event_queue = asyncio.Queue()
    service = EventInjectService(context)

    result = await service.handle(
        "inject",
        {
            "umo": "webchat:FriendMessage:u1",
            "chain": MessageChain(Plain("hello")),
            "message_str": "hello",
            "sender_id": "u1",
            "sender_name": "Moon",
            "self_id": "bot",
        },
    )
    assert result == {"queued": True}
    event = context._event_queue.get_nowait()
    assert event.message_str == "hello"
    assert event.unified_msg_origin == "webchat:FriendMessage:u1"
    assert event.get_sender_id() == "u1"

    with pytest.raises(InvalidRequest):
        await service.handle("inject", {"umo": "", "chain": MessageChain()})
    with pytest.raises(InvalidRequest):
        await service.handle("inject", {"umo": "bad-umo", "chain": MessageChain()})
    with pytest.raises(NotFound):
        await service.handle("peek", {})


@pytest.mark.asyncio
async def test_plugin_lifecycle_service_ops() -> None:
    context = MagicMock()
    manager = context._star_manager
    manager.turn_off_plugin = AsyncMock()
    manager.turn_on_plugin = AsyncMock()
    manager.update_plugin = AsyncMock()
    manager.install_plugin = AsyncMock(return_value={"name": "p"})
    service = PluginLifecycleService(context)

    await service.handle("turn_off", {"plugin_name": "p"})
    manager.turn_off_plugin.assert_awaited_once_with("p")
    await service.handle("turn_on", {"plugin_name": "p"})
    manager.turn_on_plugin.assert_awaited_once_with("p")
    await service.handle(
        "update",
        {"plugin_name": "p", "proxy": "", "download_url": "", "repo_url": ""},
    )
    manager.update_plugin.assert_awaited_once_with(
        "p", proxy="", download_url="", repo_url=""
    )
    result = await service.handle(
        "install",
        {"repo_url": "https://example.com/repo", "proxy": ""},
    )
    assert result["result"] == {"name": "p"}
    manager.install_plugin.assert_awaited_once()

    with pytest.raises(InvalidRequest):
        await service.handle("explode", {})
