from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfoNotFoundError

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
        ),
        runtime={"os": "windows", "sandbox": {"status": "unsupported"}},
    )

    with patch("astrbot.dashboard.services.config_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_time
        result = service.get_system_config()

    assert result["server_utc_time"] == "2026-08-07T02:31:00+00:00"
    assert result["server_utc_offset_minutes"] == 480
    assert result["config"]["timezone"] == "Asia/Shanghai"


@pytest.mark.parametrize(
    "timezone_error",
    [
        OSError(22, "Invalid argument"),
        ValueError("Invalid timezone path"),
        ZoneInfoNotFoundError("Unknown timezone"),
    ],
)
def test_get_system_config_falls_back_for_timezone_errors(timezone_error) -> None:
    """Keep system settings accessible when timezone lookup fails.

    Args:
        timezone_error: Lookup failure raised by the timezone database.
    """
    fixed_time = datetime(2026, 8, 7, 2, 31, tzinfo=timezone.utc)
    timezone_name = "America/Toronto\tEastern"
    service = ConfigProfileService(
        SimpleNamespace(
            astrbot_config_mgr=SimpleNamespace(
                confs={"default": {"timezone": timezone_name}}
            )
        ),
        runtime={},
    )

    with (
        patch("astrbot.dashboard.services.config_service.datetime") as mock_datetime,
        patch(
            "astrbot.dashboard.services.config_service.ZoneInfo",
            side_effect=timezone_error,
        ),
    ):
        mock_datetime.now.return_value = fixed_time
        result = service.get_system_config()

    assert result["config"]["timezone"] == timezone_name
    assert result["server_utc_time"] == fixed_time.isoformat()
    assert result["server_utc_offset_minutes"] == int(
        fixed_time.astimezone().utcoffset().total_seconds() / 60
    )


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
    service = ConfigProfileService(
        lifecycle, runtime={"os": "windows", "sandbox": {"status": "unsupported"}}
    )

    with pytest.raises(ValueError, match="Invalid local filesystem scope for member") as exc:
        await service.create_profile(
            "Invalid",
            {
                "provider_settings": {
                    "computer_use_runtime": "local",
                    "computer_use_local_permissions": {
                        role: {"filesystem_scope": "invalid"}
                        for role in ("member", "admin")
                    },
                }
            },
        )
    assert "Invalid local filesystem scope for admin" in str(exc.value)
    config_manager.create_conf.assert_not_awaited()
    lifecycle.reload_pipeline_scheduler.assert_not_awaited()

    result = await service.create_profile(
        "Profile", {"provider_settings": {"computer_use_runtime": "local"}}
    )
    await service.rename_profile("profile-id", "Renamed")
    await service.delete_profile("profile-id")

    assert result == {"conf_id": "profile-id"}
    config_manager.create_conf.assert_awaited_once_with(
        name="Profile",
        config={"provider_settings": {"computer_use_runtime": "local"}},
    )
    lifecycle.reload_pipeline_scheduler.assert_awaited_once_with("profile-id")
    config_manager.update_conf_info.assert_awaited_once_with(
        "profile-id",
        name="Renamed",
    )
    config_manager.delete_conf.assert_awaited_once_with("profile-id")
    assert "profile-id" not in lifecycle.pipeline_scheduler_mapping
