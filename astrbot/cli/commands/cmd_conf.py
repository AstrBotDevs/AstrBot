import json
import click
import hashlib
import zoneinfo
from typing import Any, Callable
from ..utils import get_astrbot_root, check_astrbot_root


def _validate_log_level(value: str) -> str:
    """验证日志级别"""
    value = value.upper()
    if value not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        raise click.ClickException(
            "日志级别必须是 DEBUG/INFO/WARNING/ERROR/CRITICAL 之一"
        )
    return value


def _validate_dashboard_port(value: str) -> int:
    """验证 Dashboard 端口"""
    try:
        port = int(value)
        if port < 1 or port > 65535:
            raise click.ClickException("端口必须在 1-65535 范围内")
        return port
    except ValueError:
        raise click.ClickException("端口必须是数字")


def _validate_dashboard_username(value: str) -> str:
    """验证 Dashboard 用户名"""
    if not value:
        raise click.ClickException("用户名不能为空")
    return value


def _validate_dashboard_password(value: str) -> str:
    """验证 Dashboard 密码"""
    if not value:
        raise click.ClickException("密码不能为空")
    return hashlib.md5(value.encode()).hexdigest()


def _validate_timezone(value: str) -> str:
    """验证时区"""
    try:
        zoneinfo.ZoneInfo(value)
    except Exception:
        raise click.ClickException(f"无效的时区: {value}，请使用有效的IANA时区名称")
    return value


def _validate_callback_api_base(value: str) -> str:
    """验证回调接口基址"""
    if not value.startswith("http://") and not value.startswith("https://"):
        raise click.ClickException("回调接口基址必须以 http:// 或 https:// 开头")
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
            f"{root}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init"
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
        raise click.ClickException(f"配置文件解析失败: {str(e)}")


def _save_config(config: dict[str, Any]) -> None:
    """保存配置文件"""
    config_path = get_astrbot_root() / "data" / "cmd_config.json"

    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8-sig"
    )


def _set_nested_item(obj: dict[str, Any], path: str, value: Any) -> None:
    """设置嵌套字典中的值"""
    parts = path.split(".")
    for part in parts[:-1]:
        if part not in obj:
            obj[part] = {}
        elif not isinstance(obj[part], dict):
            raise click.ClickException(
                f"配置路径冲突: {'.'.join(parts[: parts.index(part) + 1])} 不是字典"
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
def conf():
    """配置管理命令

    支持的配置项:

    - timezone: 时区设置 (例如: Asia/Shanghai)

    - log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)

    - dashboard.port: Dashboard 端口

    - dashboard.username: Dashboard 用户名

    - dashboard.password: Dashboard 密码

    - callback_api_base: 回调接口基址

    可用子命令:

    - set: 设置配置项值

    - get: 获取配置项值

    - login-info: 显示 Web 管理面板登录信息
    """
    pass


@conf.command(name="set")
@click.argument("key")
@click.argument("value")
def set_config(key: str, value: str):
    """设置配置项的值"""
    if key not in CONFIG_VALIDATORS.keys():
        raise click.ClickException(f"不支持的配置项: {key}")

    config = _load_config()

    try:
        old_value = _get_nested_item(config, key)
        validated_value = CONFIG_VALIDATORS[key](value)
        _set_nested_item(config, key, validated_value)
        _save_config(config)

        click.echo(f"配置已更新: {key}")
        if key == "dashboard.password":
            click.echo("  原值: ********")
            click.echo("  新值: ********")
        else:
            click.echo(f"  原值: {old_value}")
            click.echo(f"  新值: {validated_value}")

    except KeyError:
        raise click.ClickException(f"未知的配置项: {key}")
    except Exception as e:
        raise click.UsageError(f"设置配置失败: {str(e)}")


@conf.command(name="get")
@click.argument("key", required=False)
def get_config(key: str = None):
    """获取配置项的值，不提供key则显示所有可配置项"""
    config = _load_config()

    if key:
        if key not in CONFIG_VALIDATORS.keys():
            raise click.ClickException(f"不支持的配置项: {key}")

        try:
            value = _get_nested_item(config, key)
            if key == "dashboard.password":
                value = "********"
            click.echo(f"{key}: {value}")
        except KeyError:
            raise click.ClickException(f"未知的配置项: {key}")
        except Exception as e:
            raise click.UsageError(f"获取配置失败: {str(e)}")
    else:
        click.echo("当前配置:")
        for key in CONFIG_VALIDATORS.keys():
            try:
                value = (
                    "********"
                    if key == "dashboard.password"
                    else _get_nested_item(config, key)
                )
                click.echo(f"  {key}: {value}")
            except (KeyError, TypeError):
                pass


@conf.command(name="login-info")
def get_login_info():
    """显示 Web 管理面板的登录信息

    在 Docker 环境中使用示例:
    docker exec -e ASTRBOT_ROOT=/AstrBot astrbot-container astrbot conf login-info
    """
    config = _load_config()

    try:
        username = _get_nested_item(config, "dashboard.username")
        # 注意：我们不显示实际的MD5哈希密码，而是提示用户如何重置
        click.echo("🔐 Web 管理面板登录信息:")
        click.echo(f"  用户名: {username}")
        click.echo("  密码: [已加密存储]")
        click.echo()
        click.echo("💡 如需重置密码，请使用以下命令:")
        click.echo("  astrbot conf set dashboard.password <新密码>")
        click.echo()
        click.echo("🌐 访问地址:")

        # 尝试获取端口信息
        try:
            port = _get_nested_item(config, "dashboard.port")
            click.echo(f"  http://localhost:{port}")
            click.echo(f"  http://your-server-ip:{port}")
        except (KeyError, TypeError):
            click.echo("  http://localhost:6185 (默认端口)")
            click.echo("  http://your-server-ip:6185 (默认端口)")

        click.echo()
        click.echo("📋 Docker 环境使用说明:")
        click.echo("  如果在 Docker 中运行，请使用以下命令格式:")
        click.echo("  docker exec -e ASTRBOT_ROOT=/AstrBot <容器名> astrbot conf login-info")

    except KeyError:
        click.echo("❌ 无法找到登录配置，请先运行 'astrbot init' 初始化")
    except Exception as e:
        raise click.UsageError(f"获取登录信息失败: {str(e)}")
