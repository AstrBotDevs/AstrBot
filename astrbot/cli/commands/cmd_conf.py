from astrbot.core.lang import t
import hashlib
import json
import zoneinfo
from collections.abc import Callable
from typing import Any

import click

from ..utils import check_astrbot_root, get_astrbot_root


def _validate_log_level(value: str) -> str:
    """验证日志级别"""
    value = value.upper()
    if value not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        raise click.ClickException(
            t("msg-635b8763"),
        )
    return value


def _validate_dashboard_port(value: str) -> int:
    """验证 Dashboard 端口"""
    try:
        port = int(value)
        if port < 1 or port > 65535:
            raise click.ClickException(t("msg-ebc250dc"))
        return port
    except ValueError:
        raise click.ClickException(t("msg-6ec400b6"))


def _validate_dashboard_username(value: str) -> str:
    """验证 Dashboard 用户名"""
    if not value:
        raise click.ClickException(t("msg-0b62b5ce"))
    return value


def _validate_dashboard_password(value: str) -> str:
    """验证 Dashboard 密码"""
    if not value:
        raise click.ClickException(t("msg-89b5d3d5"))
    return hashlib.md5(value.encode()).hexdigest()


def _validate_timezone(value: str) -> str:
    """验证时区"""
    try:
        zoneinfo.ZoneInfo(value)
    except Exception:
        raise click.ClickException(t("msg-92e7c8ad", value=value))
    return value


def _validate_callback_api_base(value: str) -> str:
    """验证回调接口基址"""
    if not value.startswith("http://") and not value.startswith("https://"):
        raise click.ClickException(t("msg-e470e37d"))
    return value


# 可通过CLI设置的配置项，配置键到验证器函数的映射
CONFIG_VALIDATORS: dict[str, Callable[[str], Any]] = {
    "timezone": _validate_timezone,
    "log_level": _validate_log_level,
    "dashboard.port": _validate_dashboard_port,
    "dashboard.username": _validate_dashboard_username,
    "dashboard.password": _validate_dashboard_password,
    "callback_api_base": _validate_callback_api_base,
}


def _load_config() -> dict[str, Any]:
    """加载或初始化配置文件"""
    root = get_astrbot_root()
    if not check_astrbot_root(root):
        raise click.ClickException(
            t("msg-6b615721", root=root),
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
        raise click.ClickException(t("msg-f74c517c", e=e))


def _save_config(config: dict[str, Any]) -> None:
    """保存配置文件"""
    config_path = get_astrbot_root() / "data" / "cmd_config.json"

    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


def _set_nested_item(obj: dict[str, Any], path: str, value: Any) -> None:
    """设置嵌套字典中的值"""
    parts = path.split(".")
    for part in parts[:-1]:
        if part not in obj:
            obj[part] = {}
        elif not isinstance(obj[part], dict):
            raise click.ClickException(
                t("msg-d7c58bcc", res='.'.join(parts[:parts.index(part) + 1])),
            )
        obj = obj[part]
    obj[parts[-1]] = value


def _get_nested_item(obj: dict[str, Any], path: str) -> Any:
    """获取嵌套字典中的值"""
    parts = path.split(".")
    for part in parts:
        obj = obj[part]
    return obj


@click.group(name="conf")
def conf() -> None:
    """配置管理命令

    支持的配置项:

    - timezone: 时区设置 (例如: Asia/Shanghai)

    - log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)

    - dashboard.port: Dashboard 端口

    - dashboard.username: Dashboard 用户名

    - dashboard.password: Dashboard 密码

    - callback_api_base: 回调接口基址
    """


@conf.command(name="set")
@click.argument("key")
@click.argument("value")
def set_config(key: str, value: str) -> None:
    """设置配置项的值"""
    if key not in CONFIG_VALIDATORS:
        raise click.ClickException(t("msg-e16816cc", key=key))

    config = _load_config()

    try:
        old_value = _get_nested_item(config, key)
        validated_value = CONFIG_VALIDATORS[key](value)
        _set_nested_item(config, key, validated_value)
        _save_config(config)

        click.echo(t("msg-e9cce750", key=key))
        if key == "dashboard.password":
            click.echo(t("msg-1ed565aa"))
            click.echo(t("msg-1bf9569a"))
        else:
            click.echo(t("msg-f2a20ab3", old_value=old_value))
            click.echo(t("msg-0c104905", validated_value=validated_value))

    except KeyError:
        raise click.ClickException(t("msg-ea9b4e2c", key=key))
    except Exception as e:
        raise click.UsageError(t("msg-4450e3b1", e=e))


@conf.command(name="get")
@click.argument("key", required=False)
def get_config(key: str | None = None) -> None:
    """获取配置项的值，不提供key则显示所有可配置项"""
    config = _load_config()

    if key:
        if key not in CONFIG_VALIDATORS:
            raise click.ClickException(t("msg-e16816cc", key=key))

        try:
            value = _get_nested_item(config, key)
            if key == "dashboard.password":
                value = "********"
            click.echo(t("msg-ba464bee", key=key, value=value))
        except KeyError:
            raise click.ClickException(t("msg-ea9b4e2c", key=key))
        except Exception as e:
            raise click.UsageError(t("msg-72aab576", e=e))
    else:
        click.echo(t("msg-c1693d1d"))
        for key in CONFIG_VALIDATORS:
            try:
                value = (
                    "********"
                    if key == "dashboard.password"
                    else _get_nested_item(config, key)
                )
                click.echo(t("msg-50be9b74", key=key, value=value))
            except (KeyError, TypeError):
                pass
