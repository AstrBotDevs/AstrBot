"""Tests for _log_computer_config_changes()."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

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
@pytest.mark.parametrize("status", ["detected", "missing", "unavailable", "unsupported"])
@pytest.mark.parametrize(
    ("scope", "execution", "network", "denied_on"),
    [
        ("none", False, False, ()),
        ("workspace", False, False, ("unsupported",)),
        ("host", False, False, ()),
        ("workspace", True, False, ("missing", "unavailable", "unsupported")),
        ("workspace", True, True, ("missing", "unavailable", "unsupported")),
        ("host", True, False, ("missing", "unavailable", "unsupported")),
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
        ("local", "local", "member", None, False),
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
