from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core import sp
from astrbot.core.db.po import ConversationV3, UmoAlias, UmoSender
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
)


@pytest.mark.asyncio
async def test_get_groups_preserves_legacy_preference_scope(monkeypatch):
    get_async = AsyncMock(return_value=None)
    monkeypatch.setattr(sp, "get_async", get_async)
    service = SessionManagementService(MagicMock(), MagicMock())

    assert await service.get_groups() == {}
    get_async.assert_awaited_once_with(
        "unknown",
        "unknown",
        "session_groups",
        {},
    )


@pytest.mark.asyncio
async def test_save_groups_preserves_legacy_preference_scope(monkeypatch):
    put_async = AsyncMock()
    monkeypatch.setattr(sp, "put_async", put_async)
    service = SessionManagementService(MagicMock(), MagicMock())
    groups = {"group-id": {"name": "Group", "umos": []}}

    await service.save_groups(groups)

    put_async.assert_awaited_once_with(
        "unknown",
        "unknown",
        "session_groups",
        groups,
    )


@pytest.mark.asyncio
async def test_known_umos_include_senders_and_filter_exact_platform(temp_db):
    """Keep sender-only sessions and filter by instance rather than a prefix."""
    for umo in ("qq:GroupMessage:1", "qq-2:GroupMessage:2", "QQ:FriendMessage:3"):
        await temp_db.upsert_umo_sender(umo, "sender", "Alice")
    await temp_db.upsert_umo_auto_name("qq:GroupMessage:4", "sender", "Team")
    service = SessionManagementService(MagicMock(), temp_db)
    result = await service.list_active_umos(platform_id="qq")
    assert result["umos"] == ["qq:GroupMessage:4", "qq:GroupMessage:1"]
    assert {info["platform"] for info in result["umo_infos"]} == {"qq"}
    assert len((await service.list_active_umos())["umos"]) == 4


@pytest.mark.asyncio
async def test_known_umos_sort_by_latest_update_across_all_sources(temp_db):
    """Aggregate duplicates, preserve source-only UMOs and break equal timestamps stably."""
    start = datetime(2026, 1, 1)
    records = [
        ConversationV3(
            platform_id="qq",
            umo="qq:GroupMessage:combined",
            updated_at=start + timedelta(seconds=4),
        ),
        ConversationV3(
            platform_id="qq", umo="qq:GroupMessage:old", updated_at=start
        ),
        ConversationV3(
            platform_id="qq", umo="", updated_at=start + timedelta(seconds=99)
        ),
        UmoAlias(
            umo="qq:GroupMessage:combined",
            creator_sender_id="123",
            updated_at=start + timedelta(seconds=1),
        ),
        UmoAlias(
            umo="qq:GroupMessage:a",
            creator_sender_id="123",
            updated_at=start + timedelta(seconds=5),
        ),
        UmoAlias(
            umo="legacy",
            creator_sender_id="123",
            updated_at=start + timedelta(seconds=2),
        ),
        UmoSender(
            umo="qq:GroupMessage:b",
            sender_id="123",
            updated_at=start + timedelta(seconds=5),
        ),
        UmoSender(
            umo="qq:GroupMessage:combined",
            sender_id="123",
            updated_at=start + timedelta(seconds=3),
        ),
        UmoSender(
            umo="qq:GroupMessage:new",
            sender_id="123",
            updated_at=start + timedelta(seconds=1),
        ),
        UmoSender(
            umo="qq:GroupMessage:new",
            sender_id="456",
            updated_at=start + timedelta(seconds=6),
        ),
    ]
    async with temp_db.get_db() as session:
        async with session.begin():
            session.add_all(records)
    service = SessionManagementService(MagicMock(), temp_db)
    expected = [
        "qq:GroupMessage:new",
        "qq:GroupMessage:a",
        "qq:GroupMessage:b",
        "qq:GroupMessage:combined",
        "legacy",
        "qq:GroupMessage:old",
    ]
    assert await service.list_known_umos() == expected
    result = await service.list_active_umos(platform_id="qq")
    assert result["umos"] == [umo for umo in expected if umo.startswith("qq:")]
    assert [info["umo"] for info in result["umo_infos"]] == result["umos"]
