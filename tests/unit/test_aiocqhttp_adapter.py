from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.command import CommandCatalogStore
from astrbot.core.message.components import Plain, Reply
from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.runtime_catalogs import RuntimeCatalogs

pytestmark = pytest.mark.platform


class _FakeEvent(dict):
    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class _FakeCQHttp:
    def __init__(self, *args, **kwargs) -> None:
        self.request_handler = None
        self.notice_handler = None
        self.group_handler = None
        self.private_handler = None
        self.websocket_connection_handler = None

    def on_request(self):
        def decorator(func):
            self.request_handler = func
            return func

        return decorator

    def on_notice(self):
        def decorator(func):
            self.notice_handler = func
            return func

        return decorator

    def on_message(self, message_type):
        def decorator(func):
            if message_type == "group":
                self.group_handler = func
            elif message_type == "private":
                self.private_handler = func
            return func

        return decorator

    def on_websocket_connection(self, func):
        self.websocket_connection_handler = func
        return func


@pytest.mark.asyncio
async def test_aiocqhttp_group_at_conversion_skips_member_lookup(
    monkeypatch,
):
    from tests.fixtures.mocks.aiocqhttp import create_mock_aiocqhttp_modules

    mock_aiocqhttp = create_mock_aiocqhttp_modules()
    mock_aiocqhttp.CQHttp = _FakeCQHttp
    monkeypatch.setitem(sys.modules, "aiocqhttp", mock_aiocqhttp)
    monkeypatch.setitem(sys.modules, "aiocqhttp.exceptions", mock_aiocqhttp.exceptions)

    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
        AiocqhttpAdapter,
    )

    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    adapter.bot = AsyncMock()
    adapter.bot.call_action = AsyncMock()

    event = _FakeEvent(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 654321,
            "group_name": "test-group",
            "self_id": 123456,
            "message_id": 778,
            "message": [
                {"type": "at", "data": {"qq": "123456"}},
                {"type": "text", "data": {"text": " /sid "}},
                {"type": "at", "data": {"qq": "999999"}},
            ],
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
            },
        }
    )

    abm = await adapter._convert_handle_message_event(event)

    assert abm.message_str.strip() == "/sid @999999"
    assert [component.qq for component in abm.message if hasattr(component, "qq")] == [
        "123456",
        "999999",
    ]
    adapter.bot.call_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_aiocqhttp_group_handler_background_dispatches_processing(monkeypatch):
    from astrbot.core.platform.sources.aiocqhttp import aiocqhttp_platform_adapter

    monkeypatch.setattr(aiocqhttp_platform_adapter, "CQHttp", _FakeCQHttp)
    AiocqhttpAdapter = aiocqhttp_platform_adapter.AiocqhttpAdapter

    adapter = AiocqhttpAdapter(
        {
            "id": "aiocqhttp-test",
            "ws_reverse_host": "127.0.0.1",
            "ws_reverse_port": 6199,
        },
        {},
        asyncio.Queue(),
    )

    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def _convert(_event):
        started.set()
        await release.wait()
        return _FakeEvent({"sender": {"user_id": "1"}})

    async def _handle(_abm):
        finished.set()

    adapter.convert_message = _convert  # type: ignore[method-assign]
    adapter.handle_msg = _handle  # type: ignore[method-assign]

    await adapter.bot.group_handler(_FakeEvent({"post_type": "message"}))

    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert finished.is_set() is False
    release.set()
    await asyncio.wait_for(finished.wait(), timeout=1.0)
    if adapter._inbound_tasks:
        await asyncio.gather(*list(adapter._inbound_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_aiocqhttp_file_conversion_defers_file_url_lookup(monkeypatch):
    from tests.fixtures.mocks.aiocqhttp import create_mock_aiocqhttp_modules

    mock_aiocqhttp = create_mock_aiocqhttp_modules()
    mock_aiocqhttp.CQHttp = _FakeCQHttp
    monkeypatch.setitem(sys.modules, "aiocqhttp", mock_aiocqhttp)
    monkeypatch.setitem(sys.modules, "aiocqhttp.exceptions", mock_aiocqhttp.exceptions)

    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
        AiocqhttpAdapter,
    )

    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    adapter.bot = AsyncMock()
    adapter.bot.call_action = AsyncMock(
        return_value={
            "url": "https://files.example.com/demo.zip",
            "file_name": "demo.zip",
        }
    )

    event = _FakeEvent(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 654321,
            "self_id": 123456,
            "message_id": 779,
            "message": [
                {"type": "file", "data": {"file_id": "file-1", "file": "demo.zip"}},
            ],
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
            },
        }
    )

    abm = await adapter._convert_handle_message_event(event)

    file_seg = abm.message[0]
    assert file_seg.name == "demo.zip"
    assert file_seg.url == ""
    adapter.bot.call_action.assert_not_awaited()

    resolved = await file_seg.get_file(allow_return_url=True)

    assert resolved == "https://files.example.com/demo.zip"
    assert file_seg.url == "https://files.example.com/demo.zip"
    adapter.bot.call_action.assert_awaited_once_with(
        "get_group_file_url",
        file_id="file-1",
        group_id=654321,
        self_id=123456,
    )


@pytest.mark.asyncio
async def test_aiocqhttp_reply_conversion_skips_eager_get_msg(monkeypatch):
    from tests.fixtures.mocks.aiocqhttp import create_mock_aiocqhttp_modules

    mock_aiocqhttp = create_mock_aiocqhttp_modules()
    mock_aiocqhttp.CQHttp = _FakeCQHttp
    monkeypatch.setitem(sys.modules, "aiocqhttp", mock_aiocqhttp)
    monkeypatch.setitem(sys.modules, "aiocqhttp.exceptions", mock_aiocqhttp.exceptions)

    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
        AiocqhttpAdapter,
    )

    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    adapter.bot = AsyncMock()
    adapter.bot.call_action = AsyncMock()

    event = _FakeEvent(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 654321,
            "self_id": 123456,
            "message_id": 778,
            "message": [
                {"type": "reply", "data": {"id": "9001"}},
                {"type": "text", "data": {"text": " hello"}},
            ],
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
            },
        }
    )

    abm = await adapter._convert_handle_message_event(event)

    assert isinstance(abm.message[0], Reply)
    assert abm.message[0].id == "9001"
    assert abm.message[0].sender_id == 0
    assert not abm.message[0].chain
    adapter.bot.call_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_aiocqhttp_reply_only_wake_resolves_sender_lazily(monkeypatch):
    from astrbot.core.platform.sources.aiocqhttp import aiocqhttp_platform_adapter

    monkeypatch.setattr(aiocqhttp_platform_adapter, "CQHttp", _FakeCQHttp)
    AiocqhttpAdapter = aiocqhttp_platform_adapter.AiocqhttpAdapter

    adapter = AiocqhttpAdapter(
        {
            "id": "aiocqhttp-test",
            "ws_reverse_host": "127.0.0.1",
            "ws_reverse_port": 6199,
        },
        {},
        asyncio.Queue(),
    )
    adapter.bot.call_action = AsyncMock(
        return_value={
            "status": "ok",
            "retcode": 0,
            "data": {
                "sender": {"user_id": "123456"},
            },
        }
    )

    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.self_id = "123456"
    message.group_id = "654321"
    message.session_id = "654321"
    message.message_id = "778"
    message.sender = MessageMember("111222", "tester")
    message.message = [Reply(id="9001"), Plain("hello")]
    message.message_str = "hello"
    event = adapter.create_event(message)

    stage = WakingCheckStage()
    catalogs = RuntimeCatalogs()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "wake_prefix": ["/"],
                "platform_settings": {
                    "no_permission_reply": True,
                    "friend_message_needs_wake_prefix": False,
                    "ignore_bot_self_message": False,
                    "ignore_at_all": False,
                    "unique_session": False,
                    "group_wake_policy": {
                        "mention_bot": True,
                        "reply_to_bot": True,
                    },
                },
                "plugin_set": ["*"],
            },
            astrbot_config_id="default",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: CommandCatalogStore(),
            ),
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
            handlers=catalogs.handlers,
            plugins=catalogs.plugins,
        )
    )

    await stage.process(event)

    assert event.is_wake is True
    assert event.is_at_or_wake_command is True
    assert event.get_messages()[0].sender_id == "123456"
    adapter.bot.call_action.assert_awaited_once_with("get_msg", message_id="9001")
