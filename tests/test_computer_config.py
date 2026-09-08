"""Tests for _discover_bay_credentials() auto-discovery and _log_computer_config_changes()."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from astrbot.core.computer.computer_client import _discover_bay_credentials
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.dashboard.services.config_service import (
    _log_computer_config_changes,
    save_config,
    validate_config,
)


@pytest.mark.parametrize("role", ["member", "admin"])
@pytest.mark.parametrize("scope", ["none", "workspace", "host"])
@pytest.mark.parametrize("execution", [False, True])
@pytest.mark.parametrize("network", [False, True])
def test_saving_local_permissions_enforces_linked_permissions(
    role, scope, execution, network
):
    other_role = "member" if role == "admin" else "admin"
    unchanged_policy = {
        "filesystem_scope": "workspace",
        "allow_execution": True,
        "allow_network": False,
    }
    payload = {
        "provider_settings": {
            "computer_use_local_permissions": {
                role: {
                    "filesystem_scope": scope,
                    "allow_execution": execution,
                    "allow_network": network,
                },
                other_role: deepcopy(unchanged_policy),
            }
        }
    }
    payload["agent_runner"] = {"runner_type": "local"}
    config = Mock(keys=lambda: [])

    save_config(payload, config, is_core=True)

    saved = config.save_config.call_args.args[0]["provider_settings"][
        "computer_use_local_permissions"
    ]
    assert saved[role] == {
        "filesystem_scope": scope,
        "allow_execution": execution and scope != "none",
        "allow_network": network and execution and scope != "none",
    }
    assert saved[other_role] == unchanged_policy


@pytest.mark.parametrize(
    "policy",
    [
        None,
        {"filesystem_scope": "invalid"},
        {"filesystem_scope": []},
        {"allow_execution": "false"},
        {"allow_network": 1},
        {"filesystem_scope": "none", "allow_execution": "true"},
    ],
)
def test_local_permissions_reject_invalid_values(policy):
    payload = {
        "provider_settings": {"computer_use_local_permissions": {"member": policy}}
    }

    errors, _ = validate_config(payload, CONFIG_METADATA_2, is_core=True)

    assert errors


def test_local_permission_validation_does_not_inject_missing_policies():
    payload = {"provider_settings": {"computer_use_runtime": "local"}}
    original = deepcopy(payload)

    errors, saved = validate_config(payload, CONFIG_METADATA_2, is_core=True)

    assert errors == []
    assert saved == original


@pytest.mark.parametrize("role", ["member", "admin"])
@pytest.mark.parametrize("status", ["detected", "missing", "unsupported"])
@pytest.mark.parametrize(
    ("scope", "execution", "network", "denied_on"),
    [
        ("none", False, False, ()),
        ("workspace", False, False, ("unsupported",)),
        ("host", False, False, ()),
        ("workspace", True, False, ("missing", "unsupported")),
        ("workspace", True, True, ("missing", "unsupported")),
        ("host", True, False, ("missing", "unsupported")),
        ("host", True, True, ()),
    ],
)
def test_local_permission_platform_matrix(
    role, status, scope, execution, network, denied_on
):
    permissions = {r: {"filesystem_scope": "none"} for r in ("member", "admin")}
    permissions[role] = {
        "filesystem_scope": scope,
        "allow_execution": execution,
        "allow_network": network,
    }
    errors, _ = validate_config(
        {
            "provider_settings": {
                "computer_use_runtime": "local",
                "computer_use_local_permissions": permissions,
            }
        },
        CONFIG_METADATA_2,
        is_core=True,
        runtime={
            "os": "windows" if status == "unsupported" else "linux",
            "sandbox": {"status": status, "backend": "bubblewrap"},
        },
    )

    assert bool(errors) == (status in denied_on)
    if errors:
        assert len(errors) == 1
        assert errors[0].startswith(f"Local permission {role}:")


@pytest.mark.parametrize(
    ("old_mode", "new_mode", "role", "change", "rejected"),
    [
        ("local", "local", "member", {}, False),
        ("local", "local", "admin", {"filesystem_scope": "host"}, False),
        ("local", "local", "member", {"allow_execution": True}, True),
        ("local", "local", "member", None, True),
        ("none", "local", "member", {}, True),
        ("local", "none", "member", {}, False),
        ("local", "sandbox", "member", {}, False),
        ("local", "local", "member", {"filesystem_scope": "none"}, False),
    ],
)
def test_windows_legacy_permissions(old_mode, new_mode, role, change, rejected):
    old = {
        "provider_settings": {
            "computer_use_runtime": old_mode,
            "computer_use_local_permissions": {
                r: {
                    "filesystem_scope": "workspace",
                    "allow_execution": False,
                    "allow_network": True,
                }
                for r in ("member", "admin")
            },
        }
    }
    payload = deepcopy(old)
    settings = payload["provider_settings"]
    settings.update(computer_use_runtime=new_mode, default_provider_id="new-provider")
    permissions = settings["computer_use_local_permissions"]
    if change is None:
        del permissions[role]
    else:
        permissions[role].update(change)

    errors, normalized = validate_config(
        payload,
        CONFIG_METADATA_2,
        is_core=True,
        current_config=old,
        runtime={"os": "windows", "sandbox": {"status": "unsupported"}},
    )

    assert bool(errors) == rejected
    if not rejected:
        saved = normalized["provider_settings"]["computer_use_local_permissions"]
        assert all(not policy["allow_network"] for policy in saved.values())


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
    def test_logs_local_permission_change(self, mock_logger) -> None:
        """Role permission changes are included in the computer audit log."""
        old = {
            "provider_settings": {
                "computer_use_local_permissions": {
                    "member": {
                        "allow_execution": False,
                        "allow_network": False,
                        "filesystem_scope": "workspace",
                    }
                }
            }
        }
        new = {
            "provider_settings": {
                "computer_use_local_permissions": {
                    "member": {
                        "allow_execution": True,
                        "allow_network": False,
                        "filesystem_scope": "workspace",
                    }
                }
            }
        }

        _log_computer_config_changes(old, new)

        assert any(
            call.args[1:3] == ("member", "allow_execution")
            for call in mock_logger.info.call_args_list
        )

    @patch("astrbot.dashboard.services.config_service.logger")
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
        assert found, (
            f"Expected booter change in log calls: {mock_logger.info.call_args_list}"
        )

    @patch("astrbot.dashboard.services.config_service.logger")
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

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_masks_empty_token_as_empty_label(self, mock_logger) -> None:
        """Empty token values show as '(empty)' not '***'."""
        old = {
            "provider_settings": {"sandbox": {"shipyard_neo_access_token": "old-key"}}
        }
        new = {"provider_settings": {"sandbox": {"shipyard_neo_access_token": ""}}}

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
                    "booter": "shipyard_neo",
                    "shipyard_neo_endpoint": "http://127.0.0.1:8114",
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
                "sandbox": {"shipyard_neo_endpoint": "http://127.0.0.1:8114"}
            }
        }

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_called()
        call_args_str = str(mock_logger.info.call_args_list)
        assert "shipyard_neo_endpoint" in call_args_str

    @patch("astrbot.dashboard.services.config_service.logger")
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
