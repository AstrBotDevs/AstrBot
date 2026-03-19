"""
Configuration CLI for AstrBot.

This module provides:
- secure hashing utilities for the dashboard password (argon2)
- legacy compatibility helpers (md5 / sha256 hex digests)
- validators for commonly configurable items
- click CLI group with `set`, `get`, and `password` subcommands

Notes:
- The secure hasher uses `argon2.PasswordHasher`.
- Legacy checks are provided to detect pre-v3 default hashes.
"""

from __future__ import annotations

import hashlib
import json
import zoneinfo
from collections.abc import Callable
from typing import Any

import click
from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions

from astrbot.cli.utils import check_astrbot_root
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.utils.astrbot_path import astrbot_paths

# Instantiate a module-level argon2 hasher.
# Parameters use argon2 defaults provided by the library which are secure for typical use.
_PASSWORD_HASHER = PasswordHasher()

# Plaintext default dashboard password used on first-deploy / demo environments.
# This mirrors the default username "astrbot" from DEFAULT_CONFIG.
# NOTE: this is a documented default for new deployments; production installs should change it.
DEFAULT_DASHBOARD_PASSWORD = "astrbot"

# Legacy default password digests (hex) for compatibility checks in other modules.
DEFAULT_DASHBOARD_PASSWORD_MD5 = hashlib.md5(
    DEFAULT_DASHBOARD_PASSWORD.encode("utf-8")
).hexdigest()
DEFAULT_DASHBOARD_PASSWORD_SHA256 = hashlib.sha256(
    DEFAULT_DASHBOARD_PASSWORD.encode("utf-8")
).hexdigest()

# A secure argon2 hash of the default password (useful when initializing new configs).
# We compute it once at import-time. Argon2 produces a different encoded string per call,
# but that's acceptable for generating a starting hash for fresh configs.
try:
    DEFAULT_DASHBOARD_PASSWORD_HASH = _PASSWORD_HASHER.hash(DEFAULT_DASHBOARD_PASSWORD)
except Exception:
    # If argon2 is unavailable for some reason, fall back to sha256 hex as a last resort.
    # This branch intentionally crashes loudly later if argon2 is truly required.
    DEFAULT_DASHBOARD_PASSWORD_HASH = hashlib.sha256(
        DEFAULT_DASHBOARD_PASSWORD.encode("utf-8")
    ).hexdigest()


# --- Password hashing & validation utilities ---


def hash_dashboard_password_secure(value: str) -> str:
    """
    Hash the dashboard password using Argon2 (secure).

    Returns the encoded Argon2 hash string.
    """
    try:
        return _PASSWORD_HASHER.hash(value)
    except argon2_exceptions.HashingError as e:
        # Convert argon2-specific error into a ClickException to surface to CLI users.
        raise click.ClickException(f"Failed to hash password securely: {e!s}")


def verify_dashboard_password(value: str, stored_hash: str) -> bool:
    """
    Verify a plaintext password `value` against a stored hash.

    Supports:
    - Argon2 encoded hashes (preferred)
    - Legacy SHA-256 and MD5 hexadecimal digests for backward compatibility.
    """
    if not stored_hash:
        return False

    # Argon2 encoded hashes start with $argon2
    if stored_hash.startswith("$argon2"):
        try:
            return _PASSWORD_HASHER.verify(stored_hash, value)
        except argon2_exceptions.VerifyMismatchError:
            return False
        except Exception as e:
            # Fail loudly on unexpected errors
            raise click.ClickException(f"Password verification failure: {e!s}")

    # Legacy hex digests: support both sha256 (64 hex chars) and md5 (32 hex chars)
    if len(stored_hash) == 64 and all(
        ch in "0123456789abcdef" for ch in stored_hash.lower()
    ):
        return hashlib.sha256(value.encode("utf-8")).hexdigest() == stored_hash.lower()
    if len(stored_hash) == 32 and all(
        ch in "0123456789abcdef" for ch in stored_hash.lower()
    ):
        return hashlib.md5(value.encode("utf-8")).hexdigest() == stored_hash.lower()

    # Unknown format
    return False


def is_dashboard_password_hash(value: str) -> bool:
    """
    Heuristic: return True if `value` looks like a supported dashboard password hash.
    """
    if not isinstance(value, str) or not value:
        return False
    if value.startswith("$argon2"):
        return True
    value_l = value.lower()
    if len(value_l) == 64 and all(ch in "0123456789abcdef" for ch in value_l):
        return True
    if len(value_l) == 32 and all(ch in "0123456789abcdef" for ch in value_l):
        return True
    return False


# --- Validators for CLI configuration items ---


def _validate_log_level(value: str) -> str:
    value_up = value.upper()
    allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if value_up not in allowed:
        raise click.ClickException(
            "Log level must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL"
        )
    return value_up


def _validate_dashboard_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise click.ClickException("Port must be a number")
    if port < 1 or port > 65535:
        raise click.ClickException("Port must be in range 1-65535")
    return port


def _validate_dashboard_username(value: str) -> str:
    if value is None or value.strip() == "":
        raise click.ClickException("Username cannot be empty")
    return value.strip()


def _validate_dashboard_password(value: str) -> str:
    if value is None or value == "":
        raise click.ClickException("Password cannot be empty")
    # Return a secure stored representation (argon2 encoded)
    return hash_dashboard_password_secure(value)


def _validate_timezone(value: str) -> str:
    try:
        zoneinfo.ZoneInfo(value)
    except Exception:
        raise click.ClickException(
            f"Invalid timezone: {value}. Please use a valid IANA timezone name"
        )
    return value


def _validate_callback_api_base(value: str) -> str:
    if not (value.startswith("http://") or value.startswith("https://")):
        raise click.ClickException(
            "Callback API base must start with http:// or https://"
        )
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
    if not check_astrbot_root(root):
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
        # If caller provided plaintext by mistake, allow passing through validator,
        # but prefer that callers pass a pre-hashed password when applicable.
        if is_dashboard_password_hash(password_hash) and not password_hash.startswith(
            "$argon2"
        ):
            # It's a legacy hex digest; store as-is for compatibility.
            _set_nested_item(config, "dashboard.password", password_hash)
        elif password_hash.startswith("$argon2"):
            _set_nested_item(config, "dashboard.password", password_hash)
        else:
            # Treat value as plaintext and hash it securely
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


@conf.command(name="password")
@click.option("-u", "--username", type=str, help="Update dashboard username as well")
@click.option(
    "-p",
    "--password",
    type=str,
    help="Set dashboard password directly without interactive prompt",
)
def set_dashboard_password(username: str | None, password: str | None) -> None:
    """
    Interactively set dashboard password (with confirmation) or set directly with -p.
    """
    config = _load_config()

    if password is not None:
        # If the provided value already looks like a supported hash, accept it.
        if is_dashboard_password_hash(password):
            password_hash = password
        else:
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
