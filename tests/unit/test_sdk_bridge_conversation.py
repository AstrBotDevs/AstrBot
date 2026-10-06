from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from astrbot_sdk.conversations import ConversationPage, ConversationPatch, Message
from astrbot_sdk.errors import NotFound
from astrbot_sdk.events import UMO, MessageType

from astrbot.core.star.sdk_bridge import SDKPluginBridge
from astrbot.core.star.sdk_bridge.services.conversation import (
    ConversationReadService,
    ConversationWriteService,
    to_sdk_conversation,
)
from astrbot.core.star.star_handler import star_handlers_registry
from tests.unit.test_sdk_bridge import FakeCoreEvent, FakeKVStore


class FakeConversationManager:
    """In-memory stand-in for ConversationManager."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._current: dict[str, str] = {}
        self._seq = 0

    class _PO:
        def __init__(self, cid, user_id, title, persona_id, content):
            self.cid = cid
            self.platform_id = user_id.split(":")[0]
            self.user_id = user_id
            self.title = title
            self.persona_id = persona_id
            self.history = json.dumps(content)
            self.created_at = 1
            self.updated_at = 2

    async def get_curr_conversation_id(self, umo):
        return self._current.get(umo)

    async def get_conversation(self, umo, cid, create_if_not_exists=False):
        return self._store.get(cid)

    async def get_conversations(self, umo):
        return [c for c in self._store.values() if c.user_id == umo]

    async def new_conversation(self, umo, content=None, title=None, persona_id=None):
        self._seq += 1
        cid = f"conv-{self._seq}"
        self._store[cid] = self._PO(cid, umo, title, persona_id, content or [])
        self._current[umo] = cid
        return cid

    async def switch_conversation(self, umo, cid):
        self._current[umo] = cid

    async def update_conversation(
        self,
        umo,
        cid,
        history=None,
        title=None,
        persona_id=None,
        token_usage=None,
    ):
        conv = self._store[cid]
        if title is not None:
            conv.title = title
        if persona_id is not None:
            conv.persona_id = persona_id
        if history is not None:
            conv.history = json.dumps(history)

    async def delete_conversation(self, umo, cid=None):
        self._store.pop(cid, None)
        if self._current.get(umo) == cid:
            self._current.pop(umo, None)


def make_context() -> Any:
    context = MagicMock()
    context.conversation_manager = FakeConversationManager()
    return context


UMO_STR = "webchat:FriendMessage:user-1"
SDK_UMO = UMO("webchat", MessageType.PRIVATE, "user-1")


def test_to_sdk_conversation_parses_history() -> None:
    po = FakeConversationManager._PO(
        "conv-1",
        UMO_STR,
        "title",
        "",
        [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "hello"}],
            },
        ],
    )
    conv = to_sdk_conversation(po)
    assert conv.id == "conv-1"
    assert conv.title == "title"
    assert conv.persona_id is None
    assert [m.role for m in conv.messages] == ["user", "assistant"]
    assert conv.messages[1].content == "hello"


@pytest.mark.asyncio
async def test_read_service_operations() -> None:
    context = make_context()
    manager = context.conversation_manager
    service = ConversationReadService(context)

    cid = await manager.new_conversation(UMO_STR, title="t")

    result = await service.handle("current", {"umo": SDK_UMO})
    assert result["conversation"].id == cid

    result = await service.handle("get", {"umo": SDK_UMO, "conversation_id": cid})
    assert result["conversation"].title == "t"

    result = await service.handle(
        "list",
        {"umo": SDK_UMO, "cursor": None, "limit": 50},
    )
    page = result["page"]
    assert isinstance(page, ConversationPage)
    assert [item.id for item in page.items] == [cid]
    assert page.next_cursor is None

    result = await service.handle(
        "get",
        {"umo": SDK_UMO, "conversation_id": "missing"},
    )
    assert result["conversation"] is None


@pytest.mark.asyncio
async def test_write_service_operations() -> None:
    context = make_context()
    manager = context.conversation_manager
    service = ConversationWriteService(context)

    result = await service.handle(
        "create",
        {
            "umo": SDK_UMO,
            "title": "notes",
            "persona_id": None,
            "messages": [],
        },
    )
    conversation = result["conversation"]
    assert conversation.title == "notes"
    assert await manager.get_curr_conversation_id(UMO_STR) == conversation.id

    await service.handle(
        "append",
        {
            "umo": SDK_UMO,
            "conversation_id": conversation.id,
            "messages": [
                Message(role="user", content="milk"),
            ],
        },
    )
    stored = await manager.get_conversation(UMO_STR, conversation.id)
    assert json.loads(stored.history) == [{"role": "user", "content": "milk"}]

    result = await service.handle(
        "update",
        {
            "umo": SDK_UMO,
            "conversation_id": conversation.id,
            "patch": ConversationPatch(title="renamed"),
        },
    )
    assert result["conversation"].title == "renamed"

    with pytest.raises(NotFound):
        await service.handle(
            "append",
            {"umo": SDK_UMO, "conversation_id": "missing", "messages": []},
        )

    await service.handle(
        "delete",
        {"umo": SDK_UMO, "conversation_id": conversation.id},
    )
    assert await manager.get_conversation(UMO_STR, conversation.id) is None


def write_conv_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "name": f"plugin_{plugin_root.name}",
                "desc": "conversation bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:TestPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {
                    "required": [
                        {"id": "conversation.read"},
                        {"id": "conversation.write"},
                    ],
                },
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(
        """
from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.conversations import Message

class TestPlugin(Plugin):
    @on.command("remember")
    async def remember(self, event: MessageEvent, note: str):
        conv = await self.ctx.conversations.create(
            event.umo,
            title="notes",
            messages=(Message(role="user", content=note),),
        )
        await self.ctx.conversations.append(
            event.umo,
            conv.id,
            (Message(role="assistant", content="got it"),),
        )
        current = await self.ctx.conversations.current(event.umo)
        yield event.reply(f"{current.title}:{len(current.messages)}")
""",
        "utf-8",
    )


@pytest.mark.asyncio
async def test_bridge_conversation_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "conv_bridge_e2e"
    write_conv_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )

    context = make_context()
    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()
        handler = star_handlers_registry.star_handlers_map[
            f"sdk_bridge.{plugin_root.name}_remember"
        ]

        event = FakeCoreEvent("remember milk")
        assert handler.event_filters[0].filter(event, None)
        params = event.get_extra("parsed_params")

        replies = []
        async for _ in handler.handler(event, **params):
            result = event.get_result()
            if result:
                replies.append(result.chain[0].text)
            event.clear_result()
        assert replies == ["notes:2"]

        manager = context.conversation_manager
        cid = await manager.get_curr_conversation_id(UMO_STR)
        stored = await manager.get_conversation(UMO_STR, cid)
        assert json.loads(stored.history) == [
            {"role": "user", "content": "milk"},
            {"role": "assistant", "content": "got it"},
        ]
    finally:
        await bridge.stop()
