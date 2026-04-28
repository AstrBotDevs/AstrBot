"""Configuration CLI for AstrBot."""

from __future__ import annotations

import hashlib
import json
import zoneinfo
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click
from filelock import FileLock, Timeout

from astrbot.cli.i18n import t
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_root,
)


# --- Validators ---


def _validate_log_level(value: str) -> str:
    value_up = value.upper()
    allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if value_up not in allowed:
        raise click.ClickException(t("config_log_level_invalid"))
    return value_up


def _validate_dashboard_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise click.ClickException(t("config_port_must_be_number")) from None
    if port < 1 or port > 65535:
        raise click.ClickException(t("config_port_range_invalid"))
    return port


def _validate_dashboard_username(value: str) -> str:
    if not value or not value.strip():
        raise click.ClickException(t("config_username_empty"))
    return value.strip()


def _validate_dashboard_password(value: str) -> str:
    if not value:
        raise click.ClickException(t("config_password_empty"))
    return hashlib.md5(value.encode()).hexdigest()


def _validate_timezone(value: str) -> str:
    try:
        zoneinfo.ZoneInfo(value)
    except Exception as e:
        raise click.ClickException(t("config_timezone_invalid", value=value)) from e
    return value


def _validate_callback_api_base(value: str) -> str:
    if not (value.startswith("http://") or value.startswith("https://")):
        raise click.ClickException(t("config_callback_invalid"))
    return value


CONFIG_VALIDATORS: dict[str, Callable[[str], Any]] = {
    "timezone": _validate_timezone,
    "log_level": _validate_log_level,
    "dashboard.port": _validate_dashboard_port,
    "dashboard.username": _validate_dashboard_username,
    "dashboard.password": _validate_dashboard_password,
    "callback_api_base": _validate_callback_api_base,
}


# --- Config file helpers ---


def _load_config() -> dict[str, Any]:
    root = Path(get_astrbot_root())
    if not (Path(get_astrbot_root()) / ".astrbot").exists():
        raise click.ClickException(
            f"{root} is not a valid AstrBot root directory. Use 'astrbot init' to initialize",
        )

    config_path = Path(get_astrbot_data_path()) / "cmd_config.json"
    if not config_path.exists():
        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )

    try:
        return json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Failed to parse config file: {e!s}") from e


def _save_config(config: dict[str, Any]) -> None:
    config_path = Path(get_astrbot_data_path()) / "cmd_config.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


def _set_nested_item(obj: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = obj
    for part in parts[:-1]:
        if part not in cur:
            cur[part] = {}
        elif not isinstance(cur[part], dict):
            raise click.ClickException(
                f"Config path conflict: {'.'.join(parts[: parts.index(part) + 1])} is not a dict",
            )
        cur = cur[part]
    cur[parts[-1]] = value


def _get_nested_item(obj: dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    cur = obj
    for part in parts:
        cur = cur[part]
    return cur


# --- CLI commands ---


@click.group(name="conf")
def conf() -> None:
    """Configuration management commands.

    Supported config keys:
    - timezone
    - log_level
    - dashboard.port
    - dashboard.username
    - dashboard.password
    - callback_api_base
    """


@conf.command(name="set")
@click.argument("key")
@click.argument("value")
def set_config(key: str, value: str) -> None:
    """Set the value of a config item"""
    if key not in CONFIG_VALIDATORS:
        raise click.ClickException(f"Unsupported config key: {key}")

    config = _load_config()
    try:
        try:
            old_value = _get_nested_item(config, key)
        except Exception:
            old_value = "<not set>"

        validated_value = CONFIG_VALIDATORS[key](value)
        _set_nested_item(config, key, validated_value)
        _save_config(config)

        click.echo(f"Config updated: {key}")
        click.echo(f"  Old value: {old_value}")
        click.echo(f"  New value: {validated_value}")
    except KeyError as e:
        raise click.ClickException(f"Unknown config key: {key}") from e
    except click.ClickException:
        raise
    except Exception as e:
        raise click.UsageError(f"Failed to set config: {e!s}") from e


@conf.command(name="get")
@click.argument("key", required=False)
def get_config(key: str | None = None) -> None:
    """Get the value of a config item. If no key is provided, show all configurable items"""
    config = _load_config()
    if key:
        if key not in CONFIG_VALIDATORS:
            raise click.ClickException(f"Unsupported config key: {key}")
        try:
            value = _get_nested_item(config, key)
            if key == "dashboard.password":
                value = "********"
            click.echo(f"{key}: {value}")
        except KeyError as e:
            raise click.ClickException(f"Unknown config key: {key}") from e
        except Exception as e:
            raise click.UsageError(f"Failed to get config: {e!s}") from e
    else:
        click.echo("Current config:")
        for k in CONFIG_VALIDATORS:
            try:
                v = (
                    "********"
                    if k == "dashboard.password"
                    else _get_nested_item(config, k)
                )
                click.echo(f"  {k}: {v}")
            except (KeyError, TypeError):
                pass


def _check_astrbot_not_running() -> None:
    """Refuse to proceed if astrbot is currently running (lock file held)."""
    lock_file = Path(get_astrbot_root()) / "astrbot.lock"
    if not lock_file.exists():
        return
    lock = FileLock(lock_file, timeout=1)
    try:
        lock.acquire()
    except Timeout:
        raise click.ClickException(
            "AstrBot is currently running. "
            "Please stop it first before changing the password via CLI.",
        ) from None
    else:
        lock.release()


@conf.command(name="admin")
@click.option("-u", "--username", type=str, help="Update admin username as well")
@click.option(
    "-p",
    "--password",
    type=str,
    help="Set admin password directly without interactive prompt",
)
def set_dashboard_password(username: str | None, password: str | None) -> None:
    """Interactively set dashboard password (with confirmation) or set directly with -p."""
    _check_astrbot_not_running()
    config = _load_config()

    if password is not None:
        password_hash = _validate_dashboard_password(password)
    else:
        click.echo()
        click.echo("Set dashboard password (leave empty to skip):")
        password = click.prompt(
            "Password", hide_input=True, confirmation_prompt=True, default=""
        )
        if not password:
            click.echo("Password not changed.")
            return
        password_hash = _validate_dashboard_password(password)

    _set_nested_item(config, "dashboard.password", password_hash)
    if username is not None:
        _set_nested_item(
            config,
            "dashboard.username",
            _validate_dashboard_username(username),
        )
    _save_config(config)

    if username is not None:
        click.echo(f"Dashboard username updated: {username.strip()}")
    click.echo("Dashboard password updated.")
