"""
Configuration CLI for AstrBot.

This module provides:
- secure hashing utilities for the dashboard password (argon2)
- validators for commonly configurable items
- click CLI group with `set`, `get`, and `password` subcommands
"""

from __future__ import annotations

import binascii
import hashlib
import json
import zoneinfo
from collections.abc import Callable
from typing import Any

import argon2.exceptions as argon2_exceptions
import click
from argon2 import PasswordHasher

from astrbot.cli.i18n import t
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.utils.astrbot_path import astrbot_paths

_PASSWORD_HASHER = PasswordHasher()


PBKDF2_SALT = b"astrbot-dashboard"
PBKDF2_ITER = 200_000


# --- Password hashing & validation utilities ---


def hash_dashboard_password_secure(value: str) -> str:
    """
    Hash the dashboard password for storage.

    Stored format:
        $argon2id$... (if Argon2 available) or pbkdf2_sha256 fallback.
    """
    if _PASSWORD_HASHER is not None:
        try:
            return _PASSWORD_HASHER.hash(value)
        except Exception as e:
            raise click.ClickException(
                f"Failed to hash password securely (argon2): {e!s}"
            )

    dk = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), PBKDF2_SALT, PBKDF2_ITER)
    return f"pbkdf2_sha256${PBKDF2_ITER}${binascii.hexlify(PBKDF2_SALT).decode()}${dk.hex()}"


def verify_dashboard_password(value: str, stored_hash: str) -> bool:
    """
    Verify a plaintext password `value` against a stored hash.

    Supported format:
    - Argon2 encoded string: $argon2id$...
    - PBKDF2 encoded string: pbkdf2_sha256$...
    """
    if not stored_hash:
        return False

    if stored_hash.startswith("$argon2"):
        try:
            return _PASSWORD_HASHER.verify(stored_hash, value)
        except argon2_exceptions.VerifyMismatchError:
            return False
        except Exception as e:
            raise click.ClickException(f"Password verification failure (argon2): {e!s}")

    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iters_s, salt_hex, digest_hex = stored_hash.split("$", 3)
            iters = int(iters_s)
            salt = binascii.unhexlify(salt_hex)
            expected = digest_hex.lower()
            dk = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, iters)
            return dk.hex() == expected
        except Exception:
            return False

    return False


def is_dashboard_password_hash(value: str) -> bool:
    """
    Heuristic: return True if `value` looks like a supported dashboard password hash.
    """
    if not isinstance(value, str) or not value:
        return False
    return value.startswith("$argon2") or value.startswith("pbkdf2_sha256$")


def is_legacy_dashboard_password_hash(value: str) -> bool:
    """
    Return True when `value` looks like an old dashboard password hash format.
    """
    if not isinstance(value, str) or not value:
        return False
    value_l = value.lower()
    return len(value_l) in {32, 64} and all(ch in "0123456789abcdef" for ch in value_l)


# --- Validators for CLI configuration items ---


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
        raise click.ClickException(t("config_port_must_be_number"))
    if port < 1 or port > 65535:
        raise click.ClickException(t("config_port_range_invalid"))
    return port


def _validate_dashboard_username(value: str) -> str:
    if value is None or value.strip() == "":
        raise click.ClickException(t("config_username_empty"))
    return value.strip()


def _validate_dashboard_password(value: str) -> str:
    if value is None or value == "":
        raise click.ClickException(t("config_password_empty"))
    # Return the canonical stored representation.
    return hash_dashboard_password_secure(value)


def _validate_timezone(value: str) -> str:
    try:
        zoneinfo.ZoneInfo(value)
    except Exception:
        raise click.ClickException(t("config_timezone_invalid", value=value))
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
    """
    Load or initialize the CLI config file (data/cmd_config.json).
    Ensures the astrbot root is valid before proceeding.
    """
    root = astrbot_paths.root
    if not astrbot_paths.is_root:
        raise click.ClickException(
            f"{root} is not a valid AstrBot root directory. Use 'astrbot init' to initialize"
        )

    config_path = astrbot_paths.data / "cmd_config.json"
    if not config_path.exists():
        # Write DEFAULT_CONFIG to disk if file missing
        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )

    try:
        return json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Failed to parse config file: {e!s}")


def _save_config(config: dict[str, Any]) -> None:
    config_path = astrbot_paths.data / "cmd_config.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8-sig"
    )


def ensure_config_file() -> dict[str, Any]:
    return _load_config()


def _set_nested_item(obj: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = obj
    for part in parts[:-1]:
        if part not in cur:
            cur[part] = {}
        elif not isinstance(cur[part], dict):
            raise click.ClickException(
                f"Config path conflict: {'.'.join(parts[: parts.index(part) + 1])} is not a dict"
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


def prompt_dashboard_password(prompt: str = "Dashboard password") -> str:
    password = click.prompt(prompt, hide_input=True, confirmation_prompt=True, type=str)
    return _validate_dashboard_password(password)


def set_dashboard_credentials(
    config: dict[str, Any],
    *,
    username: str | None = None,
    password_hash: str | None = None,
) -> None:
    if username is not None:
        _set_nested_item(
            config, "dashboard.username", _validate_dashboard_username(username)
        )
    if password_hash is not None:
        if isinstance(password_hash, str) and is_dashboard_password_hash(password_hash):
            _set_nested_item(config, "dashboard.password", password_hash)
        else:
            if is_legacy_dashboard_password_hash(password_hash):
                raise click.ClickException(
                    "Storing legacy dashboard password hashes is no longer supported. "
                    "Please provide the plaintext password (it will be hashed securely), "
                    "or provide an Argon2-encoded hash string."
                )
            _set_nested_item(
                config,
                "dashboard.password",
                _validate_dashboard_password(password_hash),
            )


@click.group(name="conf")
def conf() -> None:
    """
    Configuration management commands.

    Supported config keys:
    - timezone
    - log_level
    - dashboard.port
    - dashboard.username
    - dashboard.password
    - callback_api_base
    """
    pass


@conf.command(name="set")
@click.argument("key")
@click.argument("value")
def set_config(key: str, value: str) -> None:
    if key not in CONFIG_VALIDATORS:
        raise click.ClickException(f"Unsupported config key: {key}")

    config = _load_config()
    try:
        # Attempt to get old value (may raise KeyError)
        try:
            old_value = _get_nested_item(config, key)
        except Exception:
            old_value = "<not set>"

        validated_value = CONFIG_VALIDATORS[key](value)
        _set_nested_item(config, key, validated_value)
        _save_config(config)

        click.echo(f"Config updated: {key}")
        if key == "dashboard.password":
            click.echo("  Old value: ********")
            click.echo("  New value: ********")
        else:
            click.echo(f"  Old value: {old_value}")
            click.echo(f"  New value: {validated_value}")
    except KeyError:
        raise click.ClickException(f"Unknown config key: {key}")
    except click.ClickException:
        raise
    except Exception as e:
        raise click.UsageError(f"Failed to set config: {e!s}")


@conf.command(name="get")
@click.argument("key", required=False)
def get_config(key: str | None = None) -> None:
    config = _load_config()
    if key:
        if key not in CONFIG_VALIDATORS:
            raise click.ClickException(f"Unsupported config key: {key}")
        try:
            value = _get_nested_item(config, key)
            if key == "dashboard.password":
                value = "********"
            click.echo(f"{key}: {value}")
        except KeyError:
            raise click.ClickException(f"Unknown config key: {key}")
        except Exception as e:
            raise click.UsageError(f"Failed to get config: {e!s}")
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
                # Missing or non-dict paths are simply skipped in listing
                pass


@conf.command(name="admin")
@click.option("-u", "--username", type=str, help="Update admain username as well")
@click.option(
    "-p",
    "--password",
    type=str,
    help="Set admain password directly without interactive prompt",
)
def set_dashboard_password(username: str | None, password: str | None) -> None:
    """
    Interactively set dashboard password (with confirmation) or set directly with -p.

    Acceptable inputs:
    - Plaintext password (recommended): it will be hashed securely before storage.
    - Argon2 encoded hash (advanced): stored as-is.
    """
    config = _load_config()

    if password is not None:
        if isinstance(password, str) and is_dashboard_password_hash(password):
            password_hash = password
        else:
            if is_legacy_dashboard_password_hash(password):
                raise click.ClickException(
                    "Providing legacy dashboard password hashes is no longer supported. "
                    "Please supply the plaintext password (it will be hashed securely), "
                    "or provide an Argon2-encoded hash string."
                )
            password_hash = _validate_dashboard_password(password)
    else:
        password_hash = prompt_dashboard_password()

    set_dashboard_credentials(
        config,
        username=username.strip() if username is not None else None,
        password_hash=password_hash,
    )
    _save_config(config)

    if username is not None:
        click.echo(f"Dashboard username updated: {username.strip()}")
    click.echo("Dashboard password updated.")
