from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from astrbot.dashboard.services.config_service import ConfigProfileService


def test_get_system_config_includes_effective_server_time() -> None:
    fixed_time = datetime(2026, 8, 7, 2, 31, tzinfo=UTC)
    service = ConfigProfileService(
        config_manager=SimpleNamespace(
            confs={"default": {"timezone": "Asia/Shanghai"}},
        ),
        config_router=SimpleNamespace(),
        core_control=SimpleNamespace(),
        totp_runtime_state=SimpleNamespace(),
    )

    with patch("astrbot.dashboard.services.config_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_time
        result = service.get_system_config()

    assert result["server_utc_time"] == "2026-08-07T02:31:00+00:00"
    assert result["server_utc_offset_minutes"] == 480
    assert result["server_timezone"] == "Asia/Shanghai"
