"""Tests for Telegram Business support in the Telegram adapter.

These tests use the same mocked Telegram modules as ``test_telegram_adapter.py``
and therefore never touch the network.
"""

import importlib
import json
import sys
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.event import MessageChain
from astrbot.api.platform import MessageType
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.register import unregister_platform_adapters_by_module
from tests.fixtures.helpers import create_mock_update
from tests.fixtures.mocks.telegram import (
    MockTelegramBuilder,
    create_mock_telegram_modules,
)

_MODULES: dict[str, object] = {}


def _patched_modules() -> dict[str, object]:
    mocks = create_mock_telegram_modules()
    return {
        "telegram": mocks["telegram"],
        "telegram.constants": mocks["telegram"].constants,
        "telegram.error": mocks["telegram"].error,
        "telegram.ext": mocks["telegram.ext"],
        "telegramify_markdown": mocks["telegramify_markdown"],
        "apscheduler": mocks["apscheduler"],
        "apscheduler.schedulers": mocks["apscheduler"].schedulers,
        "apscheduler.schedulers.asyncio": mocks["apscheduler"].schedulers.asyncio,
        "apscheduler.schedulers.background": mocks["apscheduler"].schedulers.background,
    }


def _load_module(module_name: str):
    module = _MODULES.get(module_name)
    if module is not None:
        return module
    with patch.dict(sys.modules, _patched_modules()):
        if module_name == "astrbot.core.platform.sources.telegram.tg_adapter":
            unregister_platform_adapters_by_module(module_name)
        sys.modules.pop(module_name, None)
        module = importlib.import_module(module_name)
    sys.modules[module_name] = module
    _MODULES[module_name] = module
    return module


def _adapter():
    module = _load_module("astrbot.core.platform.sources.telegram.tg_adapter")
    return module.TelegramPlatformAdapter


def _event():
    module = _load_module("astrbot.core.platform.sources.telegram.tg_event")
    return module.TelegramPlatformEvent


def _context() -> MagicMock:
    context = MagicMock()
    context.bot.username = "test_bot"
    context.bot.id = 12345678
    return context


def _business_message(business_connection_id="bc_123", update_id=5, **kwargs):
    update = create_mock_update(**kwargs)
    source = update.message
    source.business_connection_id = business_connection_id
    business_update = MagicMock()
    business_update.update_id = update_id
    business_update.message = None
    business_update.business_message = source
    return business_update


@pytest.mark.asyncio
async def test_business_message_conversion_tags_connection_and_isolates_session():
    adapter = object.__new__(_adapter())
    adapter._business_connections = {}

    update = _business_message(message_text="你好", chat_id=987654321)
    result = await adapter.convert_business_message(update, _context())

    assert result is not None
    assert result.business_connection_id == "bc_123"
    assert result.session_id == "biz:987654321:bc_123"
    assert result.type == MessageType.FRIEND_MESSAGE
    assert result.message_str == "你好"


@pytest.mark.asyncio
async def test_business_message_is_skipped_when_connection_disabled():
    adapter = object.__new__(_adapter())
    adapter._business_connections = {
        "bc_123": {"is_enabled": False, "can_reply": True},
    }

    result = await adapter.convert_business_message(
        _business_message(message_text="你好"), _context()
    )

    assert result is None


@pytest.mark.asyncio
async def test_business_connection_handler_records_and_persists_state(tmp_path):
    adapter = object.__new__(_adapter())
    adapter._business_connections = {}
    adapter._business_state_path = str(tmp_path / "business.json")
    adapter._seen_update_ids = deque(maxlen=1024)

    connection = MagicMock()
    connection.id = "bc_1"
    connection.is_enabled = True
    connection.user_chat_id = 111
    connection.user.id = 222
    connection.user.username = "owner"
    connection.rights = MagicMock(can_reply=True)
    update = MagicMock(update_id=1, business_connection=connection, message=None)

    await adapter.business_connection_handler(update, _context())

    assert adapter._business_connections["bc_1"]["is_enabled"] is True
    assert adapter._business_connections["bc_1"]["can_reply"] is True
    assert adapter._business_connections["bc_1"]["user_id"] == 222

    with open(adapter._business_state_path, encoding="utf-8") as f:
        persisted = json.load(f)
    assert persisted["bc_1"]["is_enabled"] is True


@pytest.mark.asyncio
async def test_send_with_client_includes_business_connection_id():
    TelegramPlatformEvent = _event()
    client = MockTelegramBuilder.create_bot()
    chain = MessageChain([Comp.Plain("hi")])

    await TelegramPlatformEvent.send_with_client(
        client, chain, "987654321", business_connection_id="bc_123"
    )

    client.send_message.assert_awaited_once()
    kwargs = client.send_message.await_args.kwargs
    assert kwargs["chat_id"] == "987654321"
    assert kwargs["business_connection_id"] == "bc_123"


@pytest.mark.asyncio
async def test_send_reads_business_connection_id_from_message_object():
    TelegramPlatformEvent = _event()
    event = object.__new__(TelegramPlatformEvent)
    event.message_obj = MagicMock(
        type=MessageType.FRIEND_MESSAGE,
        business_connection_id="bc_123",
        sender=MagicMock(user_id="987654321"),
    )
    event.client = MockTelegramBuilder.create_bot()
    chain = MessageChain([Comp.Plain("hi")])

    with (
        patch.object(
            TelegramPlatformEvent,
            "send_with_client",
            AsyncMock(),
        ) as send_mock,
        patch(
            "astrbot.core.platform.astr_message_event.AstrMessageEvent.send",
            AsyncMock(),
        ) as super_send,
    ):
        await event.send(chain)

    send_mock.assert_awaited_once()
    assert send_mock.await_args.args[1:] == (chain, "987654321")
    assert send_mock.await_args.kwargs["business_connection_id"] == "bc_123"
    super_send.assert_awaited_once_with(chain)


@pytest.mark.asyncio
async def test_send_by_session_decodes_business_session_id():
    adapter = object.__new__(_adapter())
    adapter.client = MockTelegramBuilder.create_bot()
    adapter._business_connections = {"bc_123": {"is_enabled": True, "can_reply": True}}
    session = MessageSession(
        platform_name="telegram",
        message_type=MessageType.FRIEND_MESSAGE,
        session_id="biz:987654321:bc_123",
    )
    chain = MessageChain([Comp.Plain("hi")])

    with (
        patch(
            "astrbot.core.platform.sources.telegram.tg_adapter.TelegramPlatformEvent.send_with_client",
            AsyncMock(),
        ) as send_mock,
        patch(
            "astrbot.core.platform.platform.Platform.send_by_session",
            AsyncMock(),
        ) as super_send,
    ):
        await adapter.send_by_session(session, chain)

    send_mock.assert_awaited_once()
    assert send_mock.await_args.args[1:] == (chain, "987654321")
    assert send_mock.await_args.kwargs["business_connection_id"] == "bc_123"
    super_send.assert_awaited_once_with(session, chain)


@pytest.mark.asyncio
async def test_send_by_session_skips_disabled_connection():
    adapter = object.__new__(_adapter())
    adapter.client = MockTelegramBuilder.create_bot()
    adapter._business_connections = {"bc_123": {"is_enabled": False}}
    session = MessageSession(
        platform_name="telegram",
        message_type=MessageType.FRIEND_MESSAGE,
        session_id="biz:987654321:bc_123",
    )
    chain = MessageChain([Comp.Plain("hi")])

    with patch(
        "astrbot.core.platform.sources.telegram.tg_adapter.TelegramPlatformEvent.send_with_client",
        AsyncMock(),
    ) as send_mock:
        await adapter.send_by_session(session, chain)

    send_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_parse_business_session():
    adapter = object.__new__(_adapter())
    assert adapter._parse_business_session("biz:123:bc_1") == ("123", "bc_1")
    assert adapter._parse_business_session("biz:123:bc:with:colons") == (
        "123",
        "bc:with:colons",
    )
    assert adapter._parse_business_session("123") is None
    assert adapter._parse_business_session("biz:") is None


@pytest.mark.asyncio
async def test_message_handler_routes_business_message_and_ignores_edits():
    adapter = object.__new__(_adapter())
    adapter.business_enabled = True
    adapter._seen_update_ids = deque(maxlen=1024)
    adapter.handle_msg = AsyncMock()
    adapter.handle_media_group_message = AsyncMock()
    converted = MagicMock()
    adapter.convert_message = AsyncMock()
    adapter.convert_business_message = AsyncMock(return_value=converted)

    business_update = _business_message(message_text="你好")
    context = _context()
    await adapter.message_handler(business_update, context)

    adapter.convert_business_message.assert_awaited_once_with(business_update, context)
    adapter.handle_msg.assert_awaited_once_with(converted)
    adapter.convert_message.assert_not_awaited()

    adapter.handle_msg.reset_mock()
    adapter.convert_business_message.reset_mock()

    edited_update = MagicMock(
        update_id=6,
        message=None,
        business_message=None,
        edited_business_message=MagicMock(),
        edited_message=None,
    )
    await adapter.message_handler(edited_update, _context())

    adapter.convert_business_message.assert_not_awaited()
    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_update_is_ignored():
    adapter = object.__new__(_adapter())
    adapter.business_enabled = True
    adapter._seen_update_ids = deque(maxlen=1024)
    adapter.handle_msg = AsyncMock()
    adapter.convert_business_message = AsyncMock(return_value=MagicMock())

    update = _business_message(message_text="你好", update_id=42)
    await adapter.message_handler(update, _context())
    await adapter.message_handler(update, _context())

    assert adapter.convert_business_message.await_count == 1
    assert adapter.handle_msg.await_count == 1
