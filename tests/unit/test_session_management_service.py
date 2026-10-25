from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core import sp
from astrbot.core.db.po import ConversationV2, Preference, UmoAlias, UmoSender
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("page", "page_size", "search", "expected_page", "expected_size", "total", "count"),
    [
        (1, -1, "", 1, -1, 125, 125),
        (7, -1, "", 1, -1, 125, 125),
        (1, -1, "team", 1, -1, 110, 110),
        (1, -1, "missing", 1, -1, 0, 0),
        (2, 10, "", 2, 10, 125, 10),
        (1, 200, "", 1, 100, 125, 100),
        (0, 0, "", 1, 10, 125, 10),
        (1, -2, "", 1, 10, 125, 10),
    ],
)
async def test_list_session_rules_pagination(
    temp_db, page, page_size, search, expected_page, expected_size, total, count
):
    """Return every matching rule for All while preserving normal pagination.

    Args:
        temp_db: Isolated SQLite database.
        page: Requested page number.
        page_size: Requested page size, including the All sentinel.
        search: Search filter for custom rule names.
        expected_page: Normalized response page.
        expected_size: Normalized response page size.
        total: Expected number of matching rules.
        count: Expected number of returned rules.
    """
    async with temp_db.get_db() as session:
        async with session.begin():
            session.add_all(
                Preference(
                    scope="umo",
                    scope_id=f"qq:GroupMessage:{index:03d}",
                    key="session_service_config",
                    value={"val": {"custom_name": "Team" if index < 110 else "Other"}},
                )
                for index in range(125)
            )
    service = SessionManagementService(MagicMock(spec=["provider_manager"]), temp_db)

    result = await service.list_session_rules(page=page, page_size=page_size, search=search)

    assert result["page"] == expected_page
    assert result["page_size"] == expected_size
    assert result["total"] == total
    assert len(result["rules"]) == count
    start = (expected_page - 1) * expected_size if expected_size != -1 else 0
    assert {rule["umo"] for rule in result["rules"]} == {
        f"qq:GroupMessage:{index:03d}" for index in range(start, start + count)
    }


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
        ConversationV2(
            platform_id="qq",
            user_id="qq:GroupMessage:combined",
            updated_at=start + timedelta(seconds=4),
        ),
        ConversationV2(
            platform_id="qq", user_id="qq:GroupMessage:old", updated_at=start
        ),
        ConversationV2(
            platform_id="qq", user_id="", updated_at=start + timedelta(seconds=99)
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
