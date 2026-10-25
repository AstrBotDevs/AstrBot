from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core import sp
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
    assert result["umos"] == ["qq:GroupMessage:1", "qq:GroupMessage:4"]
    assert {info["platform"] for info in result["umo_infos"]} == {"qq"}
    assert len((await service.list_active_umos())["umos"]) == 4
