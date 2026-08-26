"""Tests for _log_computer_config_changes()."""

from __future__ import annotations

from unittest.mock import patch

from astrbot.dashboard.services.config_service import _log_computer_config_changes


class TestLogComputerConfigChanges:
    """Test config change detection and logging."""

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_logs_runtime_change(self, mock_logger) -> None:
        """Detects computer_use_runtime change."""
        old = {"provider_settings": {"computer_use_runtime": "none"}}
        new = {"provider_settings": {"computer_use_runtime": "sandbox"}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args = [str(c) for c in mock_logger.info.call_args_list]
        assert any(
            "computer_use_runtime" in c and "none" in c and "sandbox" in c
            for c in call_args
        )

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_no_log_when_runtime_unchanged(self, mock_logger) -> None:
        """No log when runtime stays the same."""
        old = {"provider_settings": {"computer_use_runtime": "sandbox"}}
        new = {"provider_settings": {"computer_use_runtime": "sandbox"}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_not_called()

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_logs_sandbox_key_change(self, mock_logger) -> None:
        """Detects sandbox sub-key change."""
        old = {"provider_settings": {"sandbox": {"booter": "provider_a"}}}
        new = {"provider_settings": {"sandbox": {"booter": "provider_b"}}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        # logger.info("[Computer] Config changed: sandbox.%s %s -> %s", key, old, new)
        found = False
        for call in mock_logger.info.call_args_list:
            args = call[0]  # positional args: (fmt, key, old_val, new_val)
            if len(args) >= 4 and args[1] == "booter":
                assert args[2] == "provider_a"
                assert args[3] == "provider_b"
                found = True
                break
        assert found, (
            f"Expected booter change in log calls: {mock_logger.info.call_args_list}"
        )

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_masks_token_values(self, mock_logger) -> None:
        """Token/secret values are masked in log output."""
        old = {"provider_settings": {"sandbox": {"sandbox_access_token": ""}}}
        new = {
            "provider_settings": {"sandbox": {"sandbox_access_token": "sk-secret123"}}
        }

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "***" in call_args_str
        assert "sk-secret123" not in call_args_str

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_masks_empty_token_as_empty_label(self, mock_logger) -> None:
        """Empty token values show as '(empty)' not '***'."""
        old = {"provider_settings": {"sandbox": {"sandbox_access_token": "old-key"}}}
        new = {"provider_settings": {"sandbox": {"sandbox_access_token": ""}}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "(empty)" in call_args_str

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_no_log_when_nothing_changed(self, mock_logger) -> None:
        """No logs at all when config is identical."""
        cfg = {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {
                    "booter": "provider_a",
                    "sandbox_endpoint": "http://127.0.0.1:8114",
                },
            }
        }

        _log_computer_config_changes(cfg, cfg)

        mock_logger.info.assert_not_called()

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_handles_missing_provider_settings(self, mock_logger) -> None:
        """Gracefully handles configs without provider_settings."""
        _log_computer_config_changes(
            {}, {"provider_settings": {"computer_use_runtime": "sandbox"}}
        )

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "computer_use_runtime" in call_args_str

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_detects_new_sandbox_key(self, mock_logger) -> None:
        """Detects a newly added sandbox key."""
        old = {"provider_settings": {"sandbox": {}}}
        new = {
            "provider_settings": {
                "sandbox": {"sandbox_endpoint": "http://127.0.0.1:8114"}
            }
        }

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "sandbox_endpoint" in call_args_str

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_detects_removed_sandbox_key(self, mock_logger) -> None:
        """Detects a removed sandbox key."""
        old = {
            "provider_settings": {
                "sandbox": {"sandbox_endpoint": "http://127.0.0.1:8114"}
            }
        }
        new = {"provider_settings": {"sandbox": {}}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "sandbox_endpoint" in call_args_str

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_secret_key_masked(self, mock_logger) -> None:
        """Any key containing 'secret' is also masked."""
        old = {"provider_settings": {"sandbox": {"my_secret_key": ""}}}
        new = {"provider_settings": {"sandbox": {"my_secret_key": "very-secret-value"}}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "***" in call_args_str
        assert "very-secret-value" not in call_args_str
