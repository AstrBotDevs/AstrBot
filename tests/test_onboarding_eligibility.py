"""First-install eligibility must not be inferred from missing providers."""

import copy
import json
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.dashboard.services.auth_service import AuthService


def test_onboarding_marker_survives_restart_but_does_not_migrate_to_old_configs(
    tmp_path,
):
    """Only creating a new global config opts into automatic onboarding."""
    path = tmp_path / "cmd_config.json"
    config = AstrBotConfig(str(path))
    assert config["dashboard"]["onboarding_pending"] is True
    assert DEFAULT_CONFIG["dashboard"]["onboarding_pending"] is False
    assert AstrBotConfig(str(path))["dashboard"]["onboarding_pending"] is True

    del config["dashboard"]["onboarding_pending"]
    config.save_config()
    assert AstrBotConfig(str(path))["dashboard"]["onboarding_pending"] is False

    path.write_text("{}", encoding="utf-8")
    assert AstrBotConfig(str(path))["dashboard"]["onboarding_pending"] is False
    profile = AstrBotConfig(str(tmp_path / "profile.json"), schema={})
    assert "dashboard" not in profile


@pytest.mark.asyncio
@pytest.mark.parametrize("pending", [True, False, None, "true"])
@pytest.mark.parametrize("existing", [None, "platform", "provider", "provider_sources"])
async def test_setup_consumes_explicit_eligibility_only_after_success(
    tmp_path, pending, existing
):
    """Old, partial and disabled configurations never trigger the guide."""
    path = tmp_path / "cmd_config.json"
    data = copy.deepcopy(DEFAULT_CONFIG)
    data["dashboard"]["onboarding_pending"] = pending
    if existing:
        data[existing] = [{"id": "existing", "enable": False}]
    path.write_text(json.dumps(data), encoding="utf-8")
    config = AstrBotConfig(str(path))
    config["dashboard"]["jwt_secret"] = "onboarding-unit-test-secret-at-least-32-bytes"
    service = AuthService(AsyncMock(), config, demo_mode=False)

    rejected = await service.complete_setup(
        {
            "username": "tester",
            "password": "Test-password-123",
            "confirm_password": "wrong",
        }
    )
    assert rejected.message != "Setup completed successfully"
    original_pending = config["dashboard"]["onboarding_pending"]
    assert original_pending == (False if pending is None else pending)
    with (
        patch(
            "astrbot.dashboard.services.auth_service.set_password_storage_upgraded",
            new_callable=AsyncMock,
        ),
        patch(
            "astrbot.dashboard.services.auth_service.set_password_change_required",
            new_callable=AsyncMock,
        ),
    ):
        result = await service.complete_setup(
            {
                "username": "tester",
                "password": "Test-password-123",
                "confirm_password": "Test-password-123",
            }
        )
        assert result.data["onboarding_required"] is (
            pending is True and existing is None
        )
        assert AstrBotConfig(str(path))["dashboard"]["onboarding_pending"] is False
        repeated = await service.complete_setup(
            {
                "username": "tester",
                "password": "Test-password-456",
                "confirm_password": "Test-password-456",
            }
        )
        assert repeated.data["onboarding_required"] is False
