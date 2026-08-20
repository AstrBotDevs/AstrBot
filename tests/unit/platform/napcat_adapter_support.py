import asyncio
import json
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from websockets.exceptions import InvalidStatus

from astrbot.core.command import CommandCatalogStore
from astrbot.core.message.components import (
    RPS,
    Anonymous,
    Contact,
    Dice,
    Face,
    File,
    FlashTransfer,
    Forward,
    Image,
    Json,
    Location,
    Markdown,
    MFace,
    MiniApp,
    Music,
    Node,
    Nodes,
    OnlineFile,
    Plain,
    Poke,
    Record,
    Reply,
    Shake,
    Share,
    Unknown,
    Video,
    Xml,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.platform.sources.napcat import forward_ws_client
from astrbot.core.platform.sources.napcat.exceptions import (
    NapCatApiError,
    NapCatTransportError,
)
from astrbot.core.platform.sources.napcat.generated.ob11_events import OB11AllEvent
from astrbot.core.platform.sources.napcat.napcat_platform_adapter import (
    NapCatPlatformAdapter,
)
from astrbot.core.platform.sources.napcat.types import NapCatFetchedMessage
from astrbot.core.runtime_catalogs import RuntimeCatalogs

pytestmark = pytest.mark.platform


class _ControlledForwardSocket:
    """A deterministic async WebSocket double for transport lifecycle tests."""

    def __init__(
        self,
        payloads: tuple[str, ...] = (),
        *,
        disconnect_error: Exception | None = None,
    ) -> None:
        self._payloads = deque(payloads)
        self._release_event = asyncio.Event()
        self._disconnect_error = disconnect_error
        self.entered = asyncio.Event()
        self.closed = asyncio.Event()
        self.exited = asyncio.Event()
        self.sent_payloads: list[dict[str, object]] = []

    async def send(self, payload: str) -> None:
        self.sent_payloads.append(json.loads(payload))

    async def close(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.closed.set()
        self._release_event.set()

    def release(self) -> None:
        self._release_event.set()

    def __aiter__(self) -> _ControlledForwardSocket:
        return self

    async def __anext__(self) -> str:
        if self._payloads:
            return self._payloads.popleft()
        await self._release_event.wait()
        if self._disconnect_error is not None:
            raise self._disconnect_error
        raise StopAsyncIteration


class _ControlledForwardConnection:
    """Async context manager yielding a controlled forward WebSocket."""

    def __init__(self, socket: _ControlledForwardSocket) -> None:
        self.socket = socket

    async def __aenter__(self) -> _ControlledForwardSocket:
        self.socket.entered.set()
        return self.socket

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        self.socket.exited.set()


def _make_adapter(event_queue: asyncio.Queue) -> NapCatPlatformAdapter:
    adapter = NapCatPlatformAdapter(
        {
            "id": "napcat-test",
            "ws_url": "ws://127.0.0.1:3001",
            "timeout_seconds": 5,
            "verify_ssl": True,
            "reconnect_interval_seconds": 1,
            "max_frame_size_mb": 8,
        },
        {},
        event_queue,
    )
    return adapter


def _make_forward_ws_adapter(event_queue: asyncio.Queue) -> NapCatPlatformAdapter:
    adapter = NapCatPlatformAdapter(
        {
            "id": "napcat-forward-ws-test",
            "ws_url": "ws://127.0.0.1:3001/ws",
            "timeout_seconds": 5,
            "verify_ssl": True,
            "token": " forward-secret ",
            "reconnect_interval_seconds": 3,
            "max_frame_size_mb": 8,
        },
        {},
        event_queue,
    )
    return adapter


def _make_manual_event(
    adapter: NapCatPlatformAdapter,
    *,
    sender_id: str = "111222",
    message_type: MessageType = MessageType.FRIEND_MESSAGE,
    group_id: str | None = None,
    message: list | None = None,
):
    message_obj = AstrBotMessage()
    message_obj.type = message_type
    message_obj.self_id = "123456"
    message_obj.session_id = group_id or sender_id
    message_obj.message_id = "local-message-id"
    message_obj.sender = MessageMember(sender_id, "tester")
    message_obj.group_id = group_id
    message_obj.message = message or []
    message_obj.message_str = ""
    message_obj.raw_message = None
    return adapter.create_event(message_obj)


__all__ = [name for name in globals() if not name.startswith("__")]
