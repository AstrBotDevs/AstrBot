from typing import Any
import click
import json
import re

@click.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--type", "-t",
              type=click.Choice(["str", "int", "float", "bool", "json"]),
              default="auto",
              help="指定值的类型 (auto/str/int/float/bool/json)")
def set_config(key: str, value: str, type: str):
    """设置配置项的值
    
    支持多种值类型和灵活的键路径：
    
    示例:
    \b
    astrbot conf set log_level INFO\n
    \b
    astrbot conf set dashboard.port 8080 --type int\n
    \b
    astrbot conf set timezone Asia/Shanghai --type str\n
    \b
    astrbot conf set custom.data '{"key": "value"}' --type json\n
    """
    from .utils import load_config, save_config, get_nested_item, set_nested_item, CONFIG_VALIDATORS

    # 避免与内置type函数冲突
    value_type = type

    # 解析和转换值
    parsed_value = _parse_value(value, value_type)

    config = load_config()    # 检查是否为已知配置项
    if key in CONFIG_VALIDATORS.keys():
        # 使用验证器验证已知配置项
        try:
            validated_value = CONFIG_VALIDATORS[key](value)
            parsed_value = validated_value
        except Exception as e:
            raise click.ClickException(
                click.style(f"配置验证失败: {str(e)}", fg="red")
            )
    else:
        # 处理未知配置项 - 检查键是否存在
        try:
            get_nested_item(config, key)
        except KeyError:
            supported_keys = ", ".join(CONFIG_VALIDATORS.keys())
            raise click.ClickException(
                click.style(f"未知的配置项: {key}", fg="red") + "\n" +
                click.style(f"已知配置项: {supported_keys}", fg="cyan")
            )

    try:
        # 获取旧值（如果存在）
        try:
            old_value = get_nested_item(config, key)
            is_new_key = False
        except KeyError:
            old_value = None
            is_new_key = True

        # 设置新值
        set_nested_item(config, key, parsed_value)
        save_config(config)
          # 显示结果
        if is_new_key:
            click.echo(click.style(f"✓ 新配置项已创建: {key}", fg="green", bold=True))
        else:
            click.echo(click.style(f"✓ 配置已更新: {key}", fg="green", bold=True))

        if key == "dashboard.password":
            if not is_new_key:
                click.echo(click.style("  原值: ********", fg="yellow"))
            click.echo(click.style("  新值: ********", fg="green"))
        else:
            if not is_new_key:
                click.echo(click.style(f"  原值: {_format_display_value(old_value)}", fg="yellow"))
            click.echo(click.style(f"  新值: {_format_display_value(parsed_value)}", fg="green"))
            # 使用__class__.__name__避免type函数名冲突
            click.echo(click.style(f"  类型: {parsed_value.__class__.__name__}", fg="cyan"))

    except Exception as e:
        raise click.ClickException(click.style(f"设置配置失败: {str(e)}", fg="red"))


def _parse_value(value: str, value_type: str) -> Any:
    """解析和转换值到指定类型"""
    if value_type == "auto":
        # 自动检测类型
        return _auto_parse_value(value)
    elif value_type == "str":
        return value
    elif value_type == "int":
        try:
            return int(value)
        except ValueError:
            raise click.ClickException(click.style(f"无法将 '{value}' 转换为整数", fg="red"))
    elif value_type == "float":
        try:
            return float(value)
        except ValueError:
            raise click.ClickException(click.style(f"无法将 '{value}' 转换为浮点数", fg="red"))
    elif value_type == "bool":
        return _parse_bool(value)
    elif value_type == "json":
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            raise click.ClickException(click.style(f"无效的JSON格式: {str(e)}", fg="red"))
    else:
        return value


def _auto_parse_value(value: str) -> Any:
    """自动检测并解析值的类型"""
    # 尝试布尔值
    if value.lower() in ("true", "false", "yes", "no", "on", "off", "1", "0"):
        return _parse_bool(value)

    # 尝试整数
    if re.match(r"^-?\d+$", value):
        return int(value)

    # 尝试浮点数
    if re.match(r"^-?\d*\.\d+$", value):
        return float(value)

    # 尝试JSON（数组或对象）
    if value.startswith(("[", "{")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

    # 默认为字符串
    return value


def _parse_bool(value: str) -> bool:
    """解析布尔值"""
    true_values = ("true", "yes", "on", "1", "enable", "enabled")
    false_values = ("false", "no", "off", "0", "disable", "disabled")

    value_lower = value.lower()
    if value_lower in true_values:
        return True
    elif value_lower in false_values:
        return False
    else:
        raise click.ClickException(
            click.style(f"无法将 '{value}' 转换为布尔值", fg="red") + "\n" +
            click.style(f"支持的true值: {', '.join(true_values)}", fg="cyan") + "\n" +
            click.style(f"支持的false值: {', '.join(false_values)}", fg="cyan")
        )


def _format_display_value(value: Any) -> str:
    """格式化显示值"""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    elif isinstance(value, str) and len(value) > 50:
        return value[:47] + "..."
    else:
        return str(value)
