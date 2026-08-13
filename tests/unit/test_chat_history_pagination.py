from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from inspect import signature
from types import SimpleNamespace

import pytest

from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.dashboard.api.auth import AuthContext
from astrbot.dashboard.api.chat import (
    get_chat_message,
    get_chat_session,
    get_chat_thread,
)
from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.services.chat_service import (
    ChatService,
    ChatServiceError,
    serialize_history_entry,
)


class FakeHistory:
    def __init__(
        self, content: dict, *, record_id: int = 1, platform_id: str = "webchat"
    ):
        self.id = record_id
        self.platform_id = platform_id
        self.user_id = "session-1"
        self.sender_id = "bot"
        self.sender_name = "bot"
        self.content = content
        self.llm_checkpoint_id = "checkpoint"
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "platform_id": self.platform_id,
            "user_id": self.user_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "content": deepcopy(self.content),
            "llm_checkpoint_id": self.llm_checkpoint_id,
        }


def test_serializer_strips_both_reasoning_shapes_without_mutating_input():
    content = {
        "type": "bot",
        "message": [
            {"type": "plain", "text": "answer"},
            {"type": "think", "think": "abc"},
            {"type": "reasoning", "text": "de"},
            {"type": "tool_call", "tool_calls": [{"id": "tool-1"}]},
        ],
        "reasoning": "ignored-fallback",
    }
    original = deepcopy(content)
    record = FakeHistory(content)

    stripped = serialize_history_entry(record, strip_reasoning=True)

    assert stripped["content"]["message"] == [
        {"type": "plain", "text": "answer"},
        {"type": "tool_call", "tool_calls": [{"id": "tool-1"}]},
    ]
    assert stripped["content"].get("reasoning") is None
    assert stripped["has_reasoning"] is True
    assert stripped["reasoning_len"] == 5
    assert content == original

    full = serialize_history_entry(record)
    assert full["content"] == original


def test_serializer_falls_back_to_top_level_reasoning_and_preserves_user():
    bot = FakeHistory(
        {
            "type": "bot",
            "message": [{"type": "plain", "text": "x"}],
            "reasoning": "fallback",
        }
    )
    stripped = serialize_history_entry(bot, strip_reasoning=True)
    assert stripped["has_reasoning"] is True
    assert stripped["reasoning_len"] == len("fallback")
    assert "reasoning" not in stripped["content"]

    user = FakeHistory({"type": "user", "message": [{"type": "plain", "text": "hi"}]})
    user_data = serialize_history_entry(user, strip_reasoning=True)
    assert user_data["content"] == user.content
    assert "has_reasoning" not in user_data


def test_v1_history_routes_keep_legacy_default_page_size():
    assert signature(get_chat_session).parameters["page_size"].default.default == 1000
    assert signature(get_chat_thread).parameters["page_size"].default.default == 1000


@pytest.mark.asyncio
async def test_get_session_forwards_page_and_count_metadata():
    history = [FakeHistory({"type": "user", "message": []}, record_id=2)]

    class Manager:
        async def get(self, **kwargs):
            assert kwargs == {
                "platform_id": "webchat",
                "user_id": "session-1",
                "page": 2,
                "page_size": 1,
            }
            return history

        async def count(self, **kwargs):
            assert kwargs == {"platform_id": "webchat", "user_id": "session-1"}
            return 3

    class Database:
        async def get_platform_session_by_id(self, session_id):
            return SimpleNamespace(
                session_id=session_id, platform_id="webchat", creator="owner"
            )

        async def get_project_by_session(self, **kwargs):
            return None

        async def get_webchat_threads_by_parent_session(self, **kwargs):
            return []

    service = object.__new__(ChatService)
    service.db = Database()
    service.platform_history_mgr = Manager()
    service.running_convs = {}
    service.get_active_chat_runs = lambda _username, _session_id: []

    result = await service.get_session("owner", "session-1", page=2, page_size=1)
    assert result["total"] == 3
    assert result["page"] == 2
    assert result["page_size"] == 1
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_message_route_uses_api_key_username_but_ignores_jwt_query():
    seen: list[str] = []

    class Service:
        async def get_message(self, username, _message_id):
            seen.append(username)
            return {"message": {"id": 1}}

    service = Service()
    api_key_auth = AuthContext("api-key-user", [], via="api_key")
    jwt_auth = AuthContext("jwt-user", [], via="jwt")

    await get_chat_message(1, "api-key-user", api_key_auth, service)
    await get_chat_message(1, "spoofed", jwt_auth, service)
    assert seen == ["api-key-user", "jwt-user"]

    with pytest.raises(ApiError) as missing_username:
        await get_chat_message(1, None, api_key_auth, service)
    assert missing_username.value.status_code == 404

    class MissingService:
        async def get_message(self, _username, _message_id):
            raise ChatServiceError("Message not found")

    with pytest.raises(ApiError) as foreign:
        await get_chat_message(1, "owner", jwt_auth, MissingService())
    assert foreign.value.status_code == 404


@pytest.mark.asyncio
async def test_message_route_rejects_reserved_admin_username_without_subscope():
    class Service:
        core_lifecycle = SimpleNamespace(
            astrbot_config_mgr=SimpleNamespace(
                confs={"default": {"admins_id": ["admin-user"]}}
            )
        )

        async def get_message(self, _username, _message_id):
            return {"message": {"id": 1}}

    with pytest.raises(ApiError) as reserved:
        await get_chat_message(
            1,
            "admin-user",
            AuthContext("key-owner", ["chat"], via="api_key"),
            Service(),
        )
    assert reserved.value.status_code == 404


@pytest.mark.asyncio
async def test_real_history_pagination_and_count_are_scope_isolated(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "history.db"))
    await db.initialize()
    manager = PlatformMessageHistoryManager(db)
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with db.get_db() as session:
        async with session.begin():
            session.add_all(
                [
                    PlatformMessageHistory(
                        platform_id="webchat",
                        user_id="session-1",
                        content={
                            "type": "user",
                            "message": [{"type": "plain", "text": "m1"}],
                        },
                        created_at=base_time,
                        updated_at=base_time,
                    ),
                    PlatformMessageHistory(
                        platform_id="webchat",
                        user_id="session-1",
                        content={
                            "type": "user",
                            "message": [{"type": "plain", "text": "m2"}],
                        },
                        created_at=base_time.replace(minute=1),
                        updated_at=base_time.replace(minute=1),
                    ),
                    PlatformMessageHistory(
                        platform_id="webchat",
                        user_id="session-1",
                        content={
                            "type": "user",
                            "message": [{"type": "plain", "text": "m3"}],
                        },
                        created_at=base_time.replace(minute=2),
                        updated_at=base_time.replace(minute=2),
                    ),
                    PlatformMessageHistory(
                        platform_id="webchat",
                        user_id="session-1",
                        content={
                            "type": "user",
                            "message": [{"type": "plain", "text": "m4"}],
                        },
                        created_at=base_time.replace(minute=3),
                        updated_at=base_time.replace(minute=3),
                    ),
                    PlatformMessageHistory(
                        platform_id="webchat",
                        user_id="session-2",
                        content={
                            "type": "user",
                            "message": [{"type": "plain", "text": "other"}],
                        },
                        created_at=base_time,
                        updated_at=base_time,
                    ),
                    PlatformMessageHistory(
                        platform_id="webchat_thread",
                        user_id="thread-1",
                        content={
                            "type": "user",
                            "message": [{"type": "plain", "text": "t1"}],
                        },
                        created_at=base_time,
                        updated_at=base_time,
                    ),
                ]
            )

    page_one = await manager.get("webchat", "session-1", page=1, page_size=2)
    page_two = await manager.get("webchat", "session-1", page=2, page_size=2)
    assert [item.content["message"][0]["text"] for item in page_one] == ["m3", "m4"]
    assert [item.content["message"][0]["text"] for item in page_two] == ["m1", "m2"]
    assert await manager.count("webchat", "session-1") == 4
    assert await manager.count("webchat", "session-2") == 1
    assert await manager.get("webchat", "session-1", page=3, page_size=2) == []
    assert await manager.get("webchat", "session-1", page=99, page_size=2) == []
    thread_page = await manager.get("webchat_thread", "thread-1", page=1, page_size=2)
    assert [item.content["message"][0]["text"] for item in thread_page] == ["t1"]
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_get_message_ownership_matrix_uses_real_database(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "ownership.db"))
    await db.initialize()
    owner_session = await db.create_platform_session(
        creator="owner", session_id="owned-session"
    )
    foreign_session = await db.create_platform_session(
        creator="foreign", session_id="foreign-session"
    )
    owner_thread = await db.create_webchat_thread(
        creator="owner",
        parent_session_id=owner_session.session_id,
        parent_message_id=1,
        base_checkpoint_id="checkpoint-owner",
        selected_text="owner thread",
    )
    foreign_thread = await db.create_webchat_thread(
        creator="foreign",
        parent_session_id=foreign_session.session_id,
        parent_message_id=1,
        base_checkpoint_id="checkpoint-foreign",
        selected_text="foreign thread",
    )
    content = {
        "type": "bot",
        "message": [
            {"type": "think", "think": "private"},
            {"type": "plain", "text": "answer"},
        ],
        "reasoning": "private",
    }
    owned_webchat = await db.insert_platform_message_history(
        platform_id="webchat", user_id=owner_session.session_id, content=content
    )
    owned_thread = await db.insert_platform_message_history(
        platform_id="webchat_thread", user_id=owner_thread.thread_id, content=content
    )
    foreign_webchat = await db.insert_platform_message_history(
        platform_id="webchat", user_id=foreign_session.session_id, content=content
    )
    foreign_thread_record = await db.insert_platform_message_history(
        platform_id="webchat_thread", user_id=foreign_thread.thread_id, content=content
    )
    orphan = await db.insert_platform_message_history(
        platform_id="webchat", user_id="missing-session", content=content
    )
    unsupported = await db.insert_platform_message_history(
        platform_id="qq", user_id="qq-user", content=content
    )

    service = object.__new__(ChatService)
    service.db = db
    webchat_result = await service.get_message("owner", owned_webchat.id)
    thread_result = await service.get_message("owner", owned_thread.id)
    assert webchat_result["message"]["content"] == content
    assert thread_result["message"]["content"] == content

    for record_id in (
        foreign_webchat.id,
        foreign_thread_record.id,
        orphan.id,
        unsupported.id,
        999999,
    ):
        with pytest.raises(ChatServiceError, match="^Message not found$"):
            await service.get_message("owner", record_id)
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_v1_session_route_passes_list_stripping_contract():
    seen = {}

    class Service:
        async def get_session(self, username, session_id, **kwargs):
            seen.update(username=username, session_id=session_id, **kwargs)
            return {"history": [{"has_reasoning": True}]}

    result = await get_chat_session(
        "session-1",
        page=2,
        page_size=50,
        auth=AuthContext("owner", ["chat"], via="jwt"),
        service=Service(),
    )
    assert result["status"] == "ok"
    assert seen == {
        "username": "owner",
        "session_id": "session-1",
        "page": 2,
        "page_size": 50,
        "strip_reasoning": True,
    }
