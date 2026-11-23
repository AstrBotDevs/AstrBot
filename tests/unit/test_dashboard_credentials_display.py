"""Dashboard startup credentials are redacted once without persisting a secret."""

from copy import deepcopy
from pathlib import Path

import pytest

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.dashboard.server import AstrBotDashboard


@pytest.mark.parametrize(
    ("configured_username", "expected_username"),
    [("test-admin", "test-admin"), (None, "astrbot")],
)
def test_generated_credentials_are_displayed_once_with_real_config(
    astrbot_config: AstrBotConfig,
    configured_username: str | None,
    expected_username: str,
) -> None:
    if configured_username is None:
        astrbot_config["dashboard"].pop("username", None)
    else:
        astrbot_config["dashboard"]["username"] = configured_username
    before_config = deepcopy(dict(astrbot_config))
    config_file = Path(astrbot_config.config_path)
    before_file = config_file.read_bytes()
    secret = "SecretStartupPassword123"
    object.__setattr__(astrbot_config, "_generated_dashboard_password", secret)
    dashboard = object.__new__(AstrBotDashboard)
    dashboard.config = astrbot_config

    first_display = dashboard._build_dashboard_credentials_display()

    assert f"Initial username: {expected_username}" in first_display
    assert "Initial password: [REDACTED - not logged]" in first_display
    assert secret not in first_display
    assert astrbot_config._generated_dashboard_password is None

    second_display = dashboard._build_dashboard_credentials_display()

    assert f"Username: {expected_username}" in second_display
    assert "Initial password:" not in second_display
    assert "Initial username:" not in second_display
    assert secret not in second_display
    assert astrbot_config._generated_dashboard_password is None
    assert dict(astrbot_config) == before_config
    assert config_file.read_bytes() == before_file
