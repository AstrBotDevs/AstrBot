import hashlib
import json
import zoneinfo
from collections.abc import Callable
from typing import Any

import click

from ..utils import check_astrbot_root, get_astrbot_root


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
    return hashlib.md5(value.encode()).hexdigest()


def _validate_timezone(value: str) -> str:
    """Validate timezone"""
    try:
        zoneinfo.ZoneInfo(value)
    except Exception:
        raise click.ClickException(f"Invalid timezone: {value}. Please use a valid IANA timezone name")
    return value


def _validate_callback_api_base(value: str) -> str:
    """Validate callback API base URL"""
    if not value.startswith("http://") and not value.startswith("https://"):
        raise click.ClickException("Callback API base must start with http:// or https://")
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
    root = get_astrbot_root()
    if not check_astrbot_root(root):
        raise click.ClickException(
            f"{root} is not a valid AstrBot root directory. Use 'astrbot init' to initialize",
        )

    config_path = root / "data" / "cmd_config.json"
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
    config_path = get_astrbot_root() / "data" / "cmd_config.json"

    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


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
