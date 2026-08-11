from types import SimpleNamespace

import pytest

from astrbot.core.execution_context import CoreExecutionContext
from astrbot.core.message.components import File, Image, Plain
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.pipeline.group_message_history.stage import GroupMessageHistoryStage
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.send_result import DeliveryAttempt, DeliveryReceipt
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.tools.message_tools import GetGroupMessageHistoryTool


class _GroupHistoryEvent:
    def __init__(
        self, message_chain: list, *, result: MessageEventResult | None = None
    ):
        self._message_chain = message_chain
        self._result = result
        self._extras: dict[str, object] = {}
        self.unified_msg_origin = "telegram:GroupMessage:group-1"

    def get_message_type(self):
        return MessageType.GROUP_MESSAGE

    def get_platform_id(self):
        return "telegram"

    def get_platform_name(self):
        return "telegram"

    def get_messages(self):
        return self._message_chain

    def get_sender_id(self):
        return "alice"

    def get_sender_name(self):
        return "Alice"

    def get_self_id(self):
        return "astrbot"

    def get_result(self):
        return self._result

    def get_extra(self, key, default=None):
        return self._extras.get(key, default)

    def set_extra(self, key, value):
        self._extras[key] = value


def _history_context(manager: PlatformMessageHistoryManager) -> CoreExecutionContext:
    context = CoreExecutionContext.__new__(CoreExecutionContext)
    context.message_history_manager = manager
    context.get_config = lambda *, umo=None: {
        "provider_ltm_settings": {
            "group_message_history_enable": True,
            "group_message_history_max_cnt": 10,
        }
    }
    return context


@pytest.mark.asyncio
async def test_group_history_sanitizes_media_and_retains_only_group_scope(temp_db):
    manager = PlatformMessageHistoryManager(temp_db)
    image = Image.fromURL("https://secret.example.invalid/private.png")
    file = File("private.txt", "/home/alice/private.txt")

    await manager.insert_message_chain(
        platform_id="onebot",
        user_id="onebot:GroupMessage:group-1",
        message_chain=MessageChain([Plain("hello"), image, file]),
        role="user",
        is_group=True,
        sender_id="u1",
        sender_name="Alice",
        max_messages=1,
    )
    await manager.insert_message_chain(
        platform_id="onebot",
        user_id="onebot:GroupMessage:group-2",
        message_chain=MessageChain([Plain("other")]),
        role="user",
        is_group=True,
        sender_id="u2",
        sender_name="Bob",
    )

    rows = await manager.get_group(
        "onebot",
        "onebot:GroupMessage:group-1",
        limit=20,
    )
    assert len(rows) == 1
    assert rows[0].is_group is True
    assert rows[0].role == "user"
    assert rows[0].content["message"] == [
        {"type": "plain", "text": "hello"},
        {"type": "image", "text": "[Image]"},
        {"type": "file", "text": "[File]"},
    ]
    assert "secret.example" not in str(rows[0].content)
    assert "/home/alice" not in str(rows[0].content)


@pytest.mark.asyncio
async def test_group_history_stage_persists_inbound_message_before_plugins(temp_db):
    manager = PlatformMessageHistoryManager(temp_db)
    event = _GroupHistoryEvent([Plain("hello")])
    stage = GroupMessageHistoryStage()
    await stage.initialize(
        SimpleNamespace(execution_context=_history_context(manager)),
    )

    await stage.process(event)

    rows = await manager.get_group("telegram", event.unified_msg_origin)
    assert [row.content["message"] for row in rows] == [
        [{"type": "plain", "text": "hello"}],
    ]
    assert event.get_extra("_group_history_current_id") == rows[0].id


@pytest.mark.asyncio
async def test_group_history_persists_only_accepted_response_content(temp_db):
    manager = PlatformMessageHistoryManager(temp_db)
    event = _GroupHistoryEvent(
        [],
        result=MessageEventResult(chain=[Plain("first"), Plain("second")]),
    )
    receipt = DeliveryReceipt.aggregate(
        [
            DeliveryAttempt(status="accepted", semantic_text="first"),
            DeliveryAttempt(status="failed", semantic_text="second"),
        ],
        platform_id="telegram",
    )

    await _history_context(manager).persist_accepted_group_response(event, receipt)

    rows = await manager.get_group("telegram", event.unified_msg_origin)
    assert [row.content["message"] for row in rows] == [
        [{"type": "plain", "text": "first"}],
    ]
    assert event.get_extra("_group_history_assistant_persisted") is True


@pytest.mark.asyncio
async def test_group_history_retention_is_atomic_and_excludes_non_group_rows(temp_db):
    manager = PlatformMessageHistoryManager(temp_db)
    await manager.insert_message_chain(
        platform_id="onebot",
        user_id="onebot:GroupMessage:group-1",
        message_chain=MessageChain([Plain("first")]),
        role="user",
        is_group=True,
        max_messages=2,
    )
    await manager.insert_message_chain(
        platform_id="onebot",
        user_id="onebot:GroupMessage:group-1",
        message_chain=MessageChain([Plain("second")]),
        role="assistant",
        is_group=True,
        max_messages=2,
    )
    await manager.insert(
        "onebot",
        "onebot:GroupMessage:group-1",
        {"message": [{"type": "plain", "text": "legacy"}]},
        role="user",
        is_group=False,
    )

    group_rows = await manager.get_group("onebot", "onebot:GroupMessage:group-1")
    all_rows = await manager.get("onebot", "onebot:GroupMessage:group-1")
    assert [row.content["message"][0]["text"] for row in group_rows] == [
        "first",
        "second",
    ]
    assert {row.content["message"][0]["text"] for row in all_rows} == {
        "legacy",
        "first",
        "second",
    }


@pytest.mark.asyncio
async def test_group_history_tool_scopes_paginates_and_disambiguates_senders(temp_db):
    manager = PlatformMessageHistoryManager(temp_db)
    group_id = "telegram:GroupMessage:group-1"
    for text, sender_id in (
        ("oldest", "alice-1"),
        ("middle", "alice-2"),
        ("newest", "bob-1"),
    ):
        await manager.insert_message_chain(
            platform_id="telegram",
            user_id=group_id,
            message_chain=MessageChain([Plain(text)]),
            role="user",
            is_group=True,
            sender_id=sender_id,
            sender_name="Alice" if sender_id.startswith("alice") else "Bob",
        )

    extras = {"_group_history_current_id": None}
    event = type(
        "Event",
        (),
        {
            "unified_msg_origin": group_id,
            "get_message_type": lambda self: MessageType.GROUP_MESSAGE,
            "get_platform_id": lambda self: "telegram",
            "get_extra": lambda self, key, default=None: extras.get(key, default),
        },
    )()
    context = type(
        "Context",
        (),
        {
            "context": type(
                "Runtime",
                (),
                {
                    "event": event,
                    "context": type(
                        "Services",
                        (),
                        {
                            "get_config": lambda self, umo: {
                                "provider_ltm_settings": {
                                    "group_message_history_enable": True
                                }
                            },
                            "message_history_manager": manager,
                        },
                    )(),
                },
            )()
        },
    )()

    result = await GetGroupMessageHistoryTool().call(
        context,
        limit=2,
        sender="alice",
    )
    assert "Alice [alice-2" in result
    assert "middle" in result
    assert "newest" not in result
    assert "has_more=false" in result
    assert "untrusted data" in result

    inserted_rows = await manager.get_group("telegram", group_id, limit=20)
    extras["_group_history_current_id"] = inserted_rows[-1].id
    result = await GetGroupMessageHistoryTool().call(context, limit=20)
    assert "newest" not in result


@pytest.mark.asyncio
async def test_group_history_tool_rejects_non_group_and_disabled_context(temp_db):
    manager = PlatformMessageHistoryManager(temp_db)
    event = type(
        "Event",
        (),
        {
            "unified_msg_origin": "telegram:PrivateMessage:user-1",
            "get_message_type": lambda self: MessageType.FRIEND_MESSAGE,
        },
    )()
    context = type(
        "Context",
        (),
        {
            "context": type(
                "Runtime",
                (),
                {
                    "event": event,
                    "context": type(
                        "Services", (), {"message_history_manager": manager}
                    )(),
                },
            )()
        },
    )()
    tool = GetGroupMessageHistoryTool()
    assert "only available in group chats" in await tool.call(context)

    event.get_message_type = lambda: MessageType.GROUP_MESSAGE
    context.context.context.get_config = lambda umo: {
        "provider_ltm_settings": {"group_message_history_enable": False}
    }
    event.get_platform_id = lambda: "telegram"
    assert "disabled" in await tool.call(context)
