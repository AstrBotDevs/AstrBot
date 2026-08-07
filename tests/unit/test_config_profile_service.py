from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.dashboard.services.config_service import ConfigProfileService


def test_get_system_config_includes_effective_server_time() -> None:
    """Verify that the response includes server UTC time and configured offset."""
    fixed_time = datetime(2026, 8, 7, 2, 31, tzinfo=timezone.utc)
    service = ConfigProfileService(
        SimpleNamespace(
            astrbot_config_mgr=SimpleNamespace(
                confs={"default": {"timezone": "Asia/Shanghai"}}
            )
        )
    )

    with patch("astrbot.dashboard.services.config_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_time
        result = service.get_system_config()

    assert result["server_utc_time"] == "2026-08-07T02:31:00+00:00"
    assert result["server_utc_offset_minutes"] == 480
    assert result["config"]["timezone"] == "Asia/Shanghai"


@pytest.mark.asyncio
async def test_profile_mutations_await_config_manager() -> None:
    """Verify profile mutations use the config manager's async methods."""
    config_manager = SimpleNamespace(
        create_conf=AsyncMock(return_value="profile-id"),
        update_conf_info=AsyncMock(return_value=True),
        delete_conf=AsyncMock(return_value=True),
    )
    lifecycle = SimpleNamespace(
        astrbot_config_mgr=config_manager,
        reload_pipeline_scheduler=AsyncMock(),
        pipeline_scheduler_mapping={"profile-id": object()},
    )
    service = ConfigProfileService(lifecycle)

    result = await service.create_profile("Profile", {"timezone": "UTC"})
    await service.rename_profile("profile-id", "Renamed")
    await service.delete_profile("profile-id")

    assert result == {"conf_id": "profile-id"}
    config_manager.create_conf.assert_awaited_once_with(
        name="Profile",
        config={"timezone": "UTC"},
    )
    lifecycle.reload_pipeline_scheduler.assert_awaited_once_with("profile-id")
    config_manager.update_conf_info.assert_awaited_once_with(
        "profile-id",
        name="Renamed",
    )
    config_manager.delete_conf.assert_awaited_once_with("profile-id")
    assert "profile-id" not in lifecycle.pipeline_scheduler_mapping
