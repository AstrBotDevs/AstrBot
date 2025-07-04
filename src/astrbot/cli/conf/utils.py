import json
import click
from typing import Any, Callable
from ..utils import (
    validate_timezone,
    validate_log_level,
    validate_dashboard_port,
    validate_dashboard_username,
    validate_dashboard_password,
    validate_callback_api_base,
)

# 可通过CLI设置的配置项，配置键到验证器函数的映射
CONFIG_VALIDATORS: dict[str, Callable[[str], Any]] = {
    "timezone": validate_timezone,
    "log_level": validate_log_level,
    "dashboard.port": validate_dashboard_port,
    "dashboard.username": validate_dashboard_username,
    "dashboard.password": validate_dashboard_password,
    "callback_api_base": validate_callback_api_base,
}

def load_config() -> dict[str, Any]:
    """加载或初始化配置文件"""
    from ..utils import get_astrbot_root, check_astrbot_root

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


def save_config(config: dict[str, Any]) -> None:
    """保存配置文件"""
    from ..utils import get_astrbot_root

    config_path = get_astrbot_root() / "data" / "cmd_config.json"

    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8-sig"
    )


def set_nested_item(obj: dict[str, Any], path: str, value: Any) -> None:
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


def get_nested_item(obj: dict[str, Any], path: str) -> Any:
    """获取嵌套字典中的值"""
    parts = path.split(".")
    for part in parts:
        obj = obj[part]
    return obj
