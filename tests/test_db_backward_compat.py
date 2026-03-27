from __future__ import annotations

import datetime
import inspect
from typing import Any, cast

import pytest

from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import PlatformMessageHistory


class _ConversationCompatDB:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def update_conversation(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _make_legacy_db_class():
    def _build_placeholder(method_name: str):
        base_method = getattr(BaseDatabase, method_name)
        if inspect.iscoroutinefunction(base_method):

            async def _async_placeholder(self, *args, **kwargs):  # noqa: ANN001
                raise NotImplementedError(method_name)

            return _async_placeholder

        def _sync_placeholder(self, *args, **kwargs):  # noqa: ANN001
            raise NotImplementedError(method_name)

        return _sync_placeholder

    async def _get_platform_message_history(
        self,
        platform_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[PlatformMessageHistory]:
        rows = [
            item
            for item in self.rows
            if item.platform_id == platform_id and item.user_id == user_id
        ]
        start = (page - 1) * page_size
        return rows[start : start + page_size]

    async def _delete_platform_message_offset(
        self,
        platform_id: str,
        user_id: str,
        offset_sec: int = 86400,
    ) -> None:
        cutoff = self.now - datetime.timedelta(seconds=offset_sec)
        self.rows = [
            item
            for item in self.rows
            if not (
                item.platform_id == platform_id
                and item.user_id == user_id
                and item.created_at is not None
                and item.created_at >= cutoff
            )
        ]

    def __init__(
        self, rows: list[PlatformMessageHistory], now: datetime.datetime
    ) -> None:
        self.rows = list(rows)
        self.now = now

    namespace: dict[str, Any] = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "__init__": __init__,
        "get_platform_message_history": _get_platform_message_history,
        "delete_platform_message_offset": _delete_platform_message_offset,
    }
    for method_name in BaseDatabase.__abstractmethods__:
        namespace.setdefault(method_name, _build_placeholder(method_name))

    return type("LegacyCompatDatabase", (BaseDatabase,), namespace)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_manager_update_conversation_keeps_token_usage_position() -> (
    None
):
    fake_db = _ConversationCompatDB()
    manager = ConversationManager(cast(Any, fake_db))

    await manager.update_conversation(
        "telegram:private:user-1",
        "conv-1",
        [{"role": "user", "content": "hello"}],
        "Title",
        "persona-1",
        123,
    )

    assert fake_db.calls == [
        {
            "cid": "conv-1",
            "title": "Title",
            "persona_id": "persona-1",
            "clear_persona": False,
            "content": [{"role": "user", "content": "hello"}],
            "token_usage": 123,
        }
    ]


@pytest.mark.unit
def test_base_database_sdk_history_methods_are_not_abstract() -> None:
    abstract_methods = BaseDatabase.__abstractmethods__

    assert "list_sdk_platform_message_history" not in abstract_methods
    assert "delete_platform_message_before" not in abstract_methods
    assert "delete_platform_message_after" not in abstract_methods
    assert "delete_all_platform_message_history" not in abstract_methods
    assert "find_platform_message_history_by_idempotency_key" not in abstract_methods


@pytest.mark.unit
@pytest.mark.asyncio
async def test_base_database_legacy_history_fallbacks_keep_old_backends_usable() -> (
    None
):
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = [
        PlatformMessageHistory(
            id=1,
            platform_id="telegram",
            user_id="private:user-1",
            content={"message": [], "idempotency_key": "old-1"},
            created_at=now - datetime.timedelta(seconds=40),
            updated_at=now - datetime.timedelta(seconds=40),
        ),
        PlatformMessageHistory(
            id=3,
            platform_id="telegram",
            user_id="private:user-1",
            content={"message": [], "idempotency_key": "old-3"},
            created_at=now - datetime.timedelta(seconds=10),
            updated_at=now - datetime.timedelta(seconds=10),
        ),
        PlatformMessageHistory(
            id=2,
            platform_id="telegram",
            user_id="private:user-1",
            content={"message": [], "idempotency_key": "old-2"},
            created_at=now - datetime.timedelta(seconds=20),
            updated_at=now - datetime.timedelta(seconds=20),
        ),
    ]
    legacy_db = _make_legacy_db_class()(rows, now)

    listed, total = await legacy_db.list_sdk_platform_message_history(
        "telegram",
        "private:user-1",
        limit=2,
        include_total=True,
    )
    matched = await legacy_db.find_platform_message_history_by_idempotency_key(
        "telegram",
        "private:user-1",
        "old-2",
    )
    deleted_after = await legacy_db.delete_platform_message_after(
        "telegram",
        "private:user-1",
        now - datetime.timedelta(seconds=25),
    )
    deleted_all = await legacy_db.delete_all_platform_message_history(
        "telegram",
        "private:user-1",
    )

    assert [int(item.id or 0) for item in listed] == [3, 2]
    assert total == 3
    assert matched is not None
    assert int(matched.id or 0) == 2
    assert deleted_after == 2
    assert deleted_all == 1
    assert legacy_db.rows == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_base_database_delete_before_fallback_fails_lazily_for_legacy_backends() -> (
    None
):
    legacy_db = _make_legacy_db_class()(
        [], datetime.datetime.now(datetime.timezone.utc)
    )

    with pytest.raises(NotImplementedError, match="delete_platform_message_before"):
        await legacy_db.delete_platform_message_before(
            "telegram",
            "private:user-1",
            datetime.datetime.now(datetime.timezone.utc),
        )
