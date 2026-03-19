import hashlib
import json
import zoneinfo
from collections.abc import Callable
from typing import Any

import click
from argon2 import PasswordHasher, exceptions as argon2_exceptions

from astrbot.core.utils.astrbot_path import astrbot_paths

from ..utils import check_astrbot_root

# Parameters for secure dashboard password hashing.
# Note: In a full implementation, salts should be unique per password.
DASHBOARD_PASSWORD_SALT = b"astrbot-dashboard"
DASHBOARD_PASSWORD_ITERATIONS = 200_000
PASSWORD_HASHER = PasswordHasher()


def hash_dashboard_password_secure(value: str) -> str:
    """Hash Dashboard password for storage.
        "sha256",

        DASHBOARD_PASSWORD_SALT,
        DASHBOARD_PASSWORD_ITERATIONS,
    )
    return dk.hex()


    """Return True if the value looks like a supported dashboard password hash.

    Supports:
    - Argon2 hashes (preferred, start with "$argon2")
    - Legacy SHA-256 and MD5 hexadecimal digests.
    """
    # Argon2 hashes contain algorithm marker like `$argon2id$...`
    if value.startswith("$argon2"):
        return True

    # Fallback to legacy hexadecimal digests
# Legacy default password hashes kept for backward compatibility.
DEFAULT_DASHBOARD_PASSWORD_MD5 = hashlib.md5(
    DEFAULT_DASHBOARD_PASSWORD.encode()
).hexdigest()
DEFAULT_DASHBOARD_PASSWORD_SHA256 = hashlib.sha256(
    DEFAULT_DASHBOARD_PASSWORD.encode()
).hexdigest()

# Secure default password hash for new configurations.
DEFAULT_DASHBOARD_PASSWORD_HASH = hash_dashboard_password_secure(
    DEFAULT_DASHBOARD_PASSWORD
)


def hash_dashboard_password(value: str) -> str:
    """Hash Dashboard password for storage (secure, PBKDF2-HMAC-SHA256)."""
    return hash_dashboard_password_secure(value)


def hash_dashboard_password_md5(value: str) -> str:
    """Hash Dashboard password with the legacy MD5 algorithm (compatibility only)."""
    return hashlib.md5(value.encode()).hexdigest()


def is_dashboard_password_hash(value: str, *, algorithm: str) -> bool:
    expected_len = 64 if algorithm == "sha256" else 32
    return len(value) == expected_len and all(ch in "0123456789abcdef" for ch in value)


def _validate_log_level(value: str) -> str:
    """Validate log level"""
    value = value.upper()
    if value not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        raise click.ClickException(
            "Log level must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL",
        )
    return value


def _validate_dashboard_port(value: str) -> int:
    """Validate Dashboard port"""
    try:
        port = int(value)
        if port < 1 or port > 65535:
            raise click.ClickException("Port must be in range 1-65535")
        return port
    except ValueError:
        raise click.ClickException("Port must be a number")


def _validate_dashboard_username(value: str) -> str:
    """Validate Dashboard username"""
    if not value:
        raise click.ClickException("Username cannot be empty")
    return value


def _validate_dashboard_password(value: str) -> str:
    """Validate Dashboard password"""
    if not value:
        raise click.ClickException("Password cannot be empty")
    return hash_dashboard_password(value)


def _validate_timezone(value: str) -> str:
    """Validate timezone"""
    try:
        zoneinfo.ZoneInfo(value)
    except Exception:
        raise click.ClickException(
            f"Invalid timezone: {value}. Please use a valid IANA timezone name"
        )
    return value


def _validate_callback_api_base(value: str) -> str:
    """Validate callback API base URL"""
    if not value.startswith("http://") and not value.startswith("https://"):
        raise click.ClickException(
            "Callback API base must start with http:// or https://"
        )
    return value


# Configuration items settable via CLI, mapping config keys to validator functions
CONFIG_VALIDATORS: dict[str, Callable[[str], Any]] = {
    "timezone": _validate_timezone,
    "log_level": _validate_log_level,
    "dashboard.port": _validate_dashboard_port,
    "dashboard.username": _validate_dashboard_username,
    "dashboard.password": _validate_dashboard_password,
    "callback_api_base": _validate_callback_api_base,
}


def _load_config() -> dict[str, Any]:
    """Load or initialize config file"""
    root = astrbot_paths.root
    if not check_astrbot_root(root):
        raise click.ClickException(
            f"{root} is not a valid AstrBot root directory. Use 'astrbot init' to initialize",
        )

    config_path = astrbot_paths.data / "cmd_config.json"
    if not config_path.exists():
        from astrbot.core.config.default import DEFAULT_CONFIG

        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )

    try:
        return json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Failed to parse config file: {e!s}")


def _save_config(config: dict[str, Any]) -> None:
    """Save config file"""
    config_path = astrbot_paths.data / "cmd_config.json"

    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


def ensure_config_file() -> dict[str, Any]:
    """Ensure config file exists and return parsed config."""
    return _load_config()


def _set_nested_item(obj: dict[str, Any], path: str, value: Any) -> None:
    """Set a value in a nested dictionary"""
    parts = path.split(".")
    for part in parts[:-1]:
        if part not in obj:
            obj[part] = {}
        elif not isinstance(obj[part], dict):
            raise click.ClickException(
                f"Config path conflict: {'.'.join(parts[: parts.index(part) + 1])} is not a dict",
            )
        obj = obj[part]
    obj[parts[-1]] = value


def _get_nested_item(obj: dict[str, Any], path: str) -> Any:
    """Get a value from a nested dictionary"""
    parts = path.split(".")
    for part in parts:
        obj = obj[part]
    return obj


def prompt_dashboard_password(prompt: str = "Dashboard password") -> str:
    """Prompt for dashboard password with confirmation."""
    password = click.prompt(
        prompt,
        hide_input=True,
        confirmation_prompt=True,
        type=str,
    )
    return _validate_dashboard_password(password)


def set_dashboard_credentials(
    config: dict[str, Any],
    *,
    username: str | None = None,
    password_hash: str | None = None,
) -> None:
    """Update dashboard credentials in config."""
    if username is not None:
        _set_nested_item(
            config,
            "dashboard.username",
            _validate_dashboard_username(username),
        )
    if password_hash is not None:
        _set_nested_item(config, "dashboard.password", password_hash)


@click.group(name="conf")
def conf() -> None:
    """Configuration management commands

    Supported config keys:

    - timezone: Timezone setting (e.g. Asia/Shanghai)

    - log_level: Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)

    - dashboard.port: Dashboard port

    - dashboard.username: Dashboard username

    - dashboard.password: Dashboard password

    - callback_api_base: Callback API base URL
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
        old_value = _get_nested_item(config, key)
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
    except Exception as e:
        raise click.UsageError(f"Failed to set config: {e!s}")


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
        except KeyError:
            raise click.ClickException(f"Unknown config key: {key}")
        except Exception as e:
            raise click.UsageError(f"Failed to get config: {e!s}")
    else:
        click.echo("Current config:")
        for key in CONFIG_VALIDATORS:
            try:
                value = (
                    "********"
                    if key == "dashboard.password"
                    else _get_nested_item(config, key)
                )
                click.echo(f"  {key}: {value}")
            except (KeyError, TypeError):
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
    """Interactively manage dashboard password."""
    config = _load_config()

    password_hash = (
        _validate_dashboard_password(password)
        if password is not None
        else prompt_dashboard_password()
    )
    set_dashboard_credentials(
        config,
        username=username.strip() if username is not None else None,
        password_hash=password_hash,
    )
    _save_config(config)

    if username is not None:
        click.echo(f"Dashboard username updated: {username.strip()}")
    click.echo("Dashboard password updated.")
