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
