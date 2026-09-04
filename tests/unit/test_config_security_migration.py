"""Security migration tests for Dashboard authentication and exposure state."""

from __future__ import annotations

import json

from astrbot.core.utils.migra_helper import migrate_config_on_load


def _configure_paths(monkeypatch, tmp_path):
    data_path = tmp_path / "data"
    profiles_path = data_path / "config"
    profiles_path.mkdir(parents=True)
    monkeypatch.setattr(
        "astrbot.core.utils.migra_helper.get_astrbot_data_path",
        lambda: str(data_path),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.migra_helper.get_astrbot_config_path",
        lambda: str(profiles_path),
    )
    return data_path, profiles_path


def test_v4_default_migration_rotates_tokens_and_closes_remote_binding(
    tmp_path, monkeypatch
) -> None:
    data_path, _ = _configure_paths(monkeypatch, tmp_path)
    config_path = data_path / "cmd_config.json"
    config = {
        "config_version": 3,
        "dashboard": {
            "host": "0.0.0.0",
            "jwt_secret": "previous-shared-secret",
            "trust_proxy_headers": True,
        },
    }

    assert migrate_config_on_load(config, config_path)

    dashboard = config["dashboard"]
    assert config["config_version"] == 4
    assert len(dashboard["jwt_secret"]) == 64
    assert len(dashboard["plugin_asset_jwt_secret"]) == 64
    assert dashboard["jwt_secret"] != "previous-shared-secret"
    assert dashboard["jwt_secret"] != dashboard["plugin_asset_jwt_secret"]
    assert dashboard["host"] == "127.0.0.1"
    assert dashboard["access_mode"] == "local"
    assert dashboard["reverse_proxy"] == {
        "public_url": "",
        "trusted_proxy_cidrs": [],
    }
    assert dashboard["trust_proxy_headers"] is False


def test_v4_profile_migration_removes_global_authentication_state(
    tmp_path, monkeypatch
) -> None:
    data_path, profiles_path = _configure_paths(monkeypatch, tmp_path)
    (data_path / "cmd_config.json").write_text("{}", encoding="utf-8")
    profile_path = profiles_path / "abconf_profile.json"
    config = {
        "config_version": 3,
        "dashboard": {
            "jwt_secret": "session-secret",
            "plugin_asset_jwt_secret": "asset-secret",
            "password": "password-hash",
            "pbkdf2_password": "pbkdf2-hash",
            "totp": {
                "enable": True,
                "secret": "totp-secret",
                "recovery_code_hash": "recovery-hash",
            },
        },
    }
    profile_path.write_text(json.dumps(config), encoding="utf-8")

    assert migrate_config_on_load(config, profile_path)

    dashboard = config["dashboard"]
    assert config["config_version"] == 4
    assert dashboard["jwt_secret"] == ""
    assert dashboard["plugin_asset_jwt_secret"] == ""
    assert dashboard["password"] == ""
    assert dashboard["pbkdf2_password"] == ""
    assert dashboard["totp"] == {
        "enable": False,
        "secret": "",
        "recovery_code_hash": "",
    }
