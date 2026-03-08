"""Tests for _discover_bay_credentials() auto-discovery and _log_computer_config_changes()."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from astrbot.core.computer.computer_client import _discover_bay_credentials
from astrbot.dashboard.routes.config import _log_computer_config_changes


# ═══════════════════════════════════════════════════════════════
# _discover_bay_credentials
# ═══════════════════════════════════════════════════════════════


class TestDiscoverBayCredentials:
    """Test Bay API key auto-discovery from credentials.json."""

    def _write_creds(
        self,
        path: Path,
        api_key: str = "sk-bay-abc123",
        endpoint: str = "http://127.0.0.1:8114",
    ) -> None:
        """Helper: write a credentials.json file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "api_key": api_key,
                    "endpoint": endpoint,
                    "generated_at": "2026-02-17T00:00:00+00:00",
                }
            )
        )

    def test_discover_from_bay_data_dir_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BAY_DATA_DIR env var takes highest priority."""
        data_dir = tmp_path / "bay_data"
        cred_file = data_dir / "credentials.json"
        self._write_creds(cred_file, api_key="sk-bay-from-env-dir")
        monkeypatch.setenv("BAY_DATA_DIR", str(data_dir))

        result = _discover_bay_credentials("http://127.0.0.1:8114")
        assert result == "sk-bay-from-env-dir"

    def test_discover_from_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to current working directory."""
        cred_file = tmp_path / "credentials.json"
        self._write_creds(cred_file, api_key="sk-bay-from-cwd")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("BAY_DATA_DIR", raising=False)

        result = _discover_bay_credentials("http://127.0.0.1:8114")
        assert result == "sk-bay-from-cwd"

    def test_returns_empty_when_no_credentials_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns empty string when no credentials.json exists anywhere."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("BAY_DATA_DIR", raising=False)

        result = _discover_bay_credentials("http://127.0.0.1:8114")
        assert result == ""

    def test_skips_empty_api_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Skips credentials.json when api_key is empty."""
        cred_file = tmp_path / "credentials.json"
        self._write_creds(cred_file, api_key="")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("BAY_DATA_DIR", raising=False)

        result = _discover_bay_credentials("http://127.0.0.1:8114")
        assert result == ""

    def test_skips_malformed_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Handles malformed JSON gracefully."""
        cred_file = tmp_path / "credentials.json"
        cred_file.parent.mkdir(parents=True, exist_ok=True)
        cred_file.write_text("not valid json {{{")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("BAY_DATA_DIR", raising=False)

        result = _discover_bay_credentials("http://127.0.0.1:8114")
        assert result == ""

    @patch("astrbot.core.computer.computer_client.logger")
    def test_endpoint_mismatch_still_returns_key(
        self, mock_logger, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns key even if endpoint doesn't match, but logs a warning."""
        data_dir = tmp_path / "bay_data"
        cred_file = data_dir / "credentials.json"
        self._write_creds(
            cred_file, api_key="sk-bay-mismatch", endpoint="http://other-host:9000"
        )
        monkeypatch.setenv("BAY_DATA_DIR", str(data_dir))

        result = _discover_bay_credentials("http://127.0.0.1:8114")

        assert result == "sk-bay-mismatch"
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "endpoint mismatch" in warning_msg

    def test_endpoint_match_no_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No warning when endpoints match."""
        data_dir = tmp_path / "bay_data"
        cred_file = data_dir / "credentials.json"
        self._write_creds(
            cred_file, api_key="sk-bay-match", endpoint="http://127.0.0.1:8114"
        )
        monkeypatch.setenv("BAY_DATA_DIR", str(data_dir))

        with patch("astrbot.core.computer.computer_client.logger") as mock_logger:
            result = _discover_bay_credentials("http://127.0.0.1:8114")

        assert result == "sk-bay-match"
        mock_logger.warning.assert_not_called()

    def test_bay_data_dir_priority_over_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BAY_DATA_DIR takes priority over cwd."""
        env_dir = tmp_path / "env_dir"
        cwd_dir = tmp_path / "cwd_dir"
        self._write_creds(env_dir / "credentials.json", api_key="sk-bay-env-wins")
        self._write_creds(cwd_dir / "credentials.json", api_key="sk-bay-cwd-loses")
        monkeypatch.setenv("BAY_DATA_DIR", str(env_dir))
        monkeypatch.chdir(cwd_dir)

        result = _discover_bay_credentials("http://127.0.0.1:8114")
        assert result == "sk-bay-env-wins"

    def test_trailing_slash_normalization(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Trailing slashes on endpoints are normalized before comparison."""
        data_dir = tmp_path / "bay_data"
        cred_file = data_dir / "credentials.json"
        self._write_creds(
            cred_file, api_key="sk-bay-slash", endpoint="http://127.0.0.1:8114/"
        )
        monkeypatch.setenv("BAY_DATA_DIR", str(data_dir))

        with patch("astrbot.core.computer.computer_client.logger") as mock_logger:
            result = _discover_bay_credentials("http://127.0.0.1:8114")

        assert result == "sk-bay-slash"
        mock_logger.warning.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# _log_computer_config_changes
# ═══════════════════════════════════════════════════════════════


class TestLogComputerConfigChanges:
    """Test config change detection and logging."""

    @patch("astrbot.dashboard.routes.config.logger")
    def test_logs_runtime_change(self, mock_logger) -> None:
        """Detects computer_use_runtime change."""
        old = {"provider_settings": {"computer_use_runtime": "none"}}
        new = {"provider_settings": {"computer_use_runtime": "sandbox"}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args = [str(c) for c in mock_logger.info.call_args_list]
        assert any("computer_use_runtime" in c and "none" in c and "sandbox" in c for c in call_args)

    @patch("astrbot.dashboard.routes.config.logger")
    def test_no_log_when_runtime_unchanged(self, mock_logger) -> None:
        """No log when runtime stays the same."""
        old = {"provider_settings": {"computer_use_runtime": "sandbox"}}
        new = {"provider_settings": {"computer_use_runtime": "sandbox"}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_not_called()

    @patch("astrbot.dashboard.routes.config.logger")
    def test_logs_sandbox_key_change(self, mock_logger) -> None:
        """Detects sandbox sub-key change."""
        old = {"provider_settings": {"sandbox": {"booter": "shipyard"}}}
        new = {"provider_settings": {"sandbox": {"booter": "shipyard_neo"}}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        # logger.info("[Computer] Config changed: sandbox.%s %s -> %s", key, old, new)
        found = False
        for call in mock_logger.info.call_args_list:
            args = call[0]  # positional args: (fmt, key, old_val, new_val)
            if len(args) >= 4 and args[1] == "booter":
                assert args[2] == "shipyard"
                assert args[3] == "shipyard_neo"
                found = True
                break
        assert found, f"Expected booter change in log calls: {mock_logger.info.call_args_list}"

    @patch("astrbot.dashboard.routes.config.logger")
    def test_masks_token_values(self, mock_logger) -> None:
        """Token/secret values are masked in log output."""
        old = {"provider_settings": {"sandbox": {"shipyard_neo_access_token": ""}}}
        new = {
            "provider_settings": {
                "sandbox": {"shipyard_neo_access_token": "sk-bay-secret123"}
            }
        }

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "***" in call_args_str
        assert "sk-bay-secret123" not in call_args_str

    @patch("astrbot.dashboard.routes.config.logger")
    def test_masks_empty_token_as_empty_label(self, mock_logger) -> None:
        """Empty token values show as '(empty)' not '***'."""
        old = {
            "provider_settings": {
                "sandbox": {"shipyard_neo_access_token": "old-key"}
            }
        }
        new = {"provider_settings": {"sandbox": {"shipyard_neo_access_token": ""}}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "(empty)" in call_args_str

    @patch("astrbot.dashboard.routes.config.logger")
    def test_no_log_when_nothing_changed(self, mock_logger) -> None:
        """No logs at all when config is identical."""
        cfg = {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {
                    "booter": "shipyard_neo",
                    "shipyard_neo_endpoint": "http://127.0.0.1:8114",
                },
            }
        }

        _log_computer_config_changes(cfg, cfg)

        mock_logger.info.assert_not_called()

    @patch("astrbot.dashboard.routes.config.logger")
    def test_handles_missing_provider_settings(self, mock_logger) -> None:
        """Gracefully handles configs without provider_settings."""
        _log_computer_config_changes(
            {}, {"provider_settings": {"computer_use_runtime": "sandbox"}}
        )

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "computer_use_runtime" in call_args_str

    @patch("astrbot.dashboard.routes.config.logger")
    def test_detects_new_sandbox_key(self, mock_logger) -> None:
        """Detects a newly added sandbox key."""
        old = {"provider_settings": {"sandbox": {}}}
        new = {
            "provider_settings": {
                "sandbox": {"shipyard_neo_endpoint": "http://127.0.0.1:8114"}
            }
        }

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "shipyard_neo_endpoint" in call_args_str

    @patch("astrbot.dashboard.routes.config.logger")
    def test_detects_removed_sandbox_key(self, mock_logger) -> None:
        """Detects a removed sandbox key."""
        old = {
            "provider_settings": {
                "sandbox": {"shipyard_neo_endpoint": "http://127.0.0.1:8114"}
            }
        }
        new = {"provider_settings": {"sandbox": {}}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "shipyard_neo_endpoint" in call_args_str

    @patch("astrbot.dashboard.routes.config.logger")
    def test_secret_key_masked(self, mock_logger) -> None:
        """Any key containing 'secret' is also masked."""
        old = {"provider_settings": {"sandbox": {"my_secret_key": ""}}}
        new = {
            "provider_settings": {"sandbox": {"my_secret_key": "very-secret-value"}}
        }

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "***" in call_args_str
        assert "very-secret-value" not in call_args_str
