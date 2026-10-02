"""Tests for dashboard startup credential redaction."""

from unittest.mock import MagicMock

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.dashboard.server import AstrBotDashboard


def test_generated_dashboard_password_is_redacted_and_cleared() -> None:
    dashboard = AstrBotDashboard.__new__(AstrBotDashboard)
    dashboard.config = MagicMock(spec=AstrBotConfig)
    dashboard.config.__getitem__.return_value = {"username": "test-admin"}
    generated_password = "SecretStartupPassword123"
    dashboard.config._generated_dashboard_password = generated_password

    display = dashboard._build_dashboard_credentials_display()

    assert "test-admin" in display
    assert generated_password not in display
    assert "[REDACTED - not logged]" in display
    assert dashboard.config._generated_dashboard_password is None

    subsequent_display = dashboard._build_dashboard_credentials_display()
    assert "test-admin" in subsequent_display
    assert generated_password not in subsequent_display
    assert "Initial password:" not in subsequent_display
