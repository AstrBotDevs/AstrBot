from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from astrbot_sdk.errors import CapabilityDenied, NotFound

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
            self.conversation_id = cid
            self.platform_id = user_id.split(":")[0]
            self.user_id = user_id
            self.title = title
            self.persona_id = persona_id
            self.history = json.dumps(content)
            self.content = content
            self.token_usage = 0
            self.created_at = 0
            self.updated_at = 0
            self.revision = None

    async def get_curr_conversation_id(self, umo):
        return self._current.get(umo)

    async def get_conversation(self, umo, cid, create_if_not_exists=False):
        if cid not in self._store and create_if_not_exists:
            cid = await self.new_conversation(umo)
        return self._store.get(cid)

    async def get_conversations(self, umo, platform_id=None):
        return [
            conv
            for conv in self._store.values()
            if conv.user_id == umo and (platform_id is None or platform_id == conv.platform_id)
        ]

    async def new_conversation(
        self, umo, platform_id=None, content=None, title=None, persona_id=None
    ):
        self._seq += 1
        cid = f"conv-{self._seq}"
        self._store[cid] = self._PO(cid, umo, title, persona_id, content or [])
        self._current[umo] = cid
        return cid

    async def add_message_pair(self, cid, user_message, assistant_message):
        conv = self._store[cid]
        history = json.loads(conv.history)
        conv.history = json.dumps([*history, user_message, assistant_message])

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
SESSION = {"unified_msg_origin": UMO_STR}


def test_to_sdk_conversation_preserves_core_fields() -> None:
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
    assert conv.cid == po.cid
    assert conv.user_id == po.user_id
    assert conv.platform_id == po.platform_id
    assert conv.title == po.title
    assert conv.persona_id == ""
    assert conv.history == po.history
    assert conv.token_usage == po.token_usage
    assert conv.created_at == 0


@pytest.mark.asyncio
async def test_read_service_operations() -> None:
    context = make_context()
    manager = context.conversation_manager
    service = ConversationReadService(context)

    assert await service.handle("get_curr_conversation_id", SESSION) is None

    cid = await manager.new_conversation(UMO_STR, title="t")
    assert await service.handle("get_curr_conversation_id", SESSION) == cid

    conv = await service.handle("get_conversation", {**SESSION, "conversation_id": cid})
    assert conv.cid == cid
    assert conv.title == "t"
    assert await service.handle(
        "get_conversations", {**SESSION, "platform_id": "webchat"}
    ) == [conv]

    missing = {**SESSION, "conversation_id": "missing"}
    assert await service.handle("get_conversation", missing) is None
    with pytest.raises(CapabilityDenied):
        await service.handle("get_conversation", {**missing, "create_if_not_exists": True})
    writable = ConversationReadService(context, allow_create=True)
    created = await writable.handle(
        "get_conversation", {**missing, "create_if_not_exists": True}
    )
    assert created.cid == await manager.get_curr_conversation_id(UMO_STR)


@pytest.mark.asyncio
async def test_write_service_operations() -> None:
    context = make_context()
    manager = context.conversation_manager
    service = ConversationWriteService(context)

    cid = await service.handle(
        "new_conversation",
        {**SESSION, "title": "notes"},
    )
    assert await manager.get_curr_conversation_id(UMO_STR) == cid
    assert await service.handle(
        "add_message_pair",
        {
            **SESSION,
            "cid": cid,
            "user_message": {"role": "user", "content": "milk"},
            "assistant_message": {"role": "assistant", "content": "got it"},
        },
    ) is None
    stored = await manager.get_conversation(UMO_STR, cid)
    assert json.loads(stored.history) == [
        {"role": "user", "content": "milk"},
        {"role": "assistant", "content": "got it"},
    ]

    assert await service.handle(
        "update_conversation", {**SESSION, "title": "renamed"}
    ) is None
    assert stored.title == "renamed"

    with pytest.raises(NotFound):
        await service.handle(
            "add_message_pair", {**SESSION, "cid": "missing"},
        )

    await service.handle("delete_conversation", SESSION)
    assert await manager.get_conversation(UMO_STR, cid) is None


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
import json

from astrbot_sdk import MessageEvent, Plugin, on

class TestPlugin(Plugin):
    @on.command("remember")
    async def remember(self, event: MessageEvent, note: str):
        umo = event.unified_msg_origin
        cid = await self.ctx.conversations.new_conversation(umo, title="notes")
        await self.ctx.conversations.add_message_pair(
            cid,
            {"role": "user", "content": note},
            {"role": "assistant", "content": "got it"},
        )
        assert await self.ctx.conversations.get_curr_conversation_id(umo) == cid
        assert (await self.ctx.conversations.get_conversations())[0].cid == cid
        current = await self.ctx.conversations.get_conversation(umo, cid)
        yield event.reply(f"{current.title}:{len(json.loads(current.history))}")
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
        assert handler.event_filters[0].filter(event, {})
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
