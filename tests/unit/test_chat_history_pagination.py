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
    get_chat_session,
)
from astrbot.dashboard.services.chat_service import (
    ChatService,
    ChatServiceError,
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


def test_v1_history_routes_keep_legacy_default_page_size():
    assert signature(get_chat_session).parameters["page_size"].default.default == 1000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("page", "total", "has_row", "has_more"),
    [(1, 0, False, False), (2, 3, True, True), (3, 3, True, False), (4, 3, False, False)],
)
async def test_get_session_returns_complete_content_and_pagination_metadata(
    page, total, has_row, has_more
):
    content = {
        "type": "bot",
        "message": [
            {"type": "think", "think": "first thought"},
            {
                "type": "tool_call",
                "tool_calls": [
                    {"id": "tool-1", "name": "search", "arguments": {"q": "x"}, "result": "full tool result"}
                ],
            },
            {"type": "plain", "text": "intermediate answer"},
            {"type": "reasoning", "text": "legacy thought"},
            {"type": "think", "think": "second thought"},
            {"type": "plain", "text": "final answer"},
        ],
        "reasoning": "top-level reasoning",
    }
    original = deepcopy(content)
    history = [FakeHistory(content, record_id=2)] if has_row else []

    class Manager:
        async def get(self, **kwargs):
            assert kwargs == {
                "platform_id": "webchat",
                "user_id": "session-1",
                "page": page,
                "page_size": 1,
            }
            return history

        async def count(self, **kwargs):
            assert kwargs == {"platform_id": "webchat", "user_id": "session-1"}
            return total

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

    result = await service.get_session("owner", "session-1", page=page, page_size=1)
    assert result["total"] == total
    assert result["page"] == page
    assert result["page_size"] == 1
    assert result["has_more"] is has_more
    if has_row:
        assert result["history"][0]["content"] == original
        assert "has_reasoning" not in result["history"][0]
        assert "reasoning_len" not in result["history"][0]
        assert history[0].content == original
    else:
        assert result["history"] == []


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
async def test_v1_session_route_forwards_pagination_parameters():
    seen = {}

    class Service:
        async def get_session(self, username, session_id, **kwargs):
            seen.update(username=username, session_id=session_id, **kwargs)
            return {"history": []}

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
    }
