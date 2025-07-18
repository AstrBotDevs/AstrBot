import click
import json

@click.command()
@click.argument("key", required=False)
@click.option("--format", "-f",
              type=click.Choice(["simple", "json", "yaml"]),
              default="simple",
              help="输出格式")
@click.option("--show-type", "-t", is_flag=True, help="显示值的类型")
@click.option("--all", "-a", is_flag=True, help="显示所有配置项（包括未在验证器中的）")
def get(key: str = None, format: str = "simple", show_type: bool = False, all: bool = False):
    """获取配置项的值
    
    不提供key则显示所有可配置项，使用 --all 显示完整配置
    
    示例:
    \b
    astrbot conf get                    # 显示所有的已知配置项
    astrbot conf get --all              # 显示所有配置项
    astrbot conf get log_level          # 获取特定配置
    astrbot conf get --format json     # JSON格式输出
    """

    from .utils import load_config, get_nested_item
    config = load_config()

    if key:
        # 获取特定配置项
        try:
            value = get_nested_item(config, key)
            _display_single_value(key, value, format, show_type)
        except KeyError:
            # 尝试模糊匹配
            possible_keys = _find_similar_keys(config, key)
            if possible_keys:
                click.echo(click.style(f"未找到配置项: {key}", fg="red"))
                click.echo(click.style("可能您想要的是:", fg="yellow"))
                for possible_key in possible_keys[:5]:  # 最多显示5个建议
                    click.echo(f"  {click.style(possible_key, fg='cyan')}")
            else:
                raise click.ClickException(click.style(f"未找到配置项: {key}", fg="red"))
        except Exception as e:
            raise click.ClickException(click.style(f"获取配置失败: {str(e)}", fg="red"))
    else:
        # 显示配置列表
        if all:
            _display_all_config(config, format, show_type)
        else:
            _display_known_config(config, format, show_type)


def _display_single_value(key: str, value, format: str, show_type: bool):
    """显示单个配置值"""
    if key == "dashboard.password":
        display_value = "********"
    else:
        display_value = value

    if format == "json":
        output = {key: display_value}
        if show_type:
            output[f"{key}_type"] = type(value).__name__
        click.echo(json.dumps(output, ensure_ascii=False, indent=2))
    elif format == "yaml":
        click.echo(f"{key}: {_format_yaml_value(display_value)}")
        if show_type:
            click.echo(f"{key}_type: {type(value).__name__}")
    else:  # simple
        type_info = f" ({click.style(type(value).__name__, fg='cyan')})" if show_type else ""
        click.echo(f"{click.style(key, fg='cyan', bold=True)}: {click.style(str(display_value), fg='green')}{type_info}")


def _display_known_config(config: dict, format: str, show_type: bool):
    """显示已知配置项"""
    from .utils import CONFIG_VALIDATORS,get_nested_item

    if format == "json":
        output = {}
        for key in CONFIG_VALIDATORS.keys():
            try:
                value = get_nested_item(config, key)
                display_value = "********" if key == "dashboard.password" else value
                output[key] = display_value
                if show_type:
                    output[f"{key}_type"] = type(value).__name__
            except (KeyError, TypeError):
                output[key] = None
                if show_type:
                    output[f"{key}_type"] = "null"
        click.echo(json.dumps(output, ensure_ascii=False, indent=2))
    elif format == "yaml":
        click.echo("# 已知配置项")
        for key in CONFIG_VALIDATORS.keys():
            try:
                value = get_nested_item(config, key)
                display_value = "********" if key == "dashboard.password" else value
                click.echo(f"{key}: {_format_yaml_value(display_value)}")
                if show_type:
                    click.echo(f"{key}_type: {type(value).__name__}")
            except (KeyError, TypeError):
                click.echo(f"{key}: null  # 未设置")
    else:  # simple
        click.echo(click.style("已知配置项:", fg="cyan", bold=True))
        for key in CONFIG_VALIDATORS.keys():
            try:
                value = get_nested_item(config, key)
                display_value = "********" if key == "dashboard.password" else value
                type_info = f" ({click.style(type(value).__name__, fg='cyan')})" if show_type else ""
                click.echo(f"  {click.style(key, fg='yellow')}: {click.style(str(display_value), fg='green')}{type_info}")
            except (KeyError, TypeError):
                click.echo(f"  {click.style(key, fg='yellow')}: {click.style('未设置', fg='red')}")


def _display_all_config(config: dict, format: str, show_type: bool):
    """显示所有配置项"""
    if format == "json":
        output = _redact_passwords(config.copy())
        click.echo(json.dumps(output, ensure_ascii=False, indent=2))
    elif format == "yaml":
        _print_yaml_recursive(config, show_type)
    else:  # simple
        click.echo(click.style("完整配置:", fg="cyan", bold=True))
        _print_config_recursive(config, "", show_type)


def _print_config_recursive(obj: dict, prefix: str = "", show_type: bool = False, level: int = 0):
    """递归打印配置"""
    indent = "  " * level
    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key

        if key == "password" and "dashboard" in prefix:
            display_value = "********"
        elif isinstance(value, dict):
            click.echo(f"{indent}{click.style(key, fg='yellow', bold=True)}:")
            _print_config_recursive(value, full_key, show_type, level + 1)
            continue
        else:
            display_value = value

        type_info = f" ({click.style(type(value).__name__, fg='cyan')})" if show_type else ""
        click.echo(f"{indent}{click.style(key, fg='yellow')}: {click.style(str(display_value), fg='green')}{type_info}")


def _print_yaml_recursive(obj: dict, show_type: bool = False, level: int = 0):
    """递归打印YAML格式"""
    indent = "  " * level
    for key, value in obj.items():
        if key == "password" and level > 0:  # 简单的密码检测
            click.echo(f"{indent}{key}: ********")
        elif isinstance(value, dict):
            click.echo(f"{indent}{key}:")
            _print_yaml_recursive(value, show_type, level + 1)
        else:
            click.echo(f"{indent}{key}: {_format_yaml_value(value)}")
            if show_type:
                click.echo(f"{indent}{key}_type: {type(value).__name__}")


def _format_yaml_value(value) -> str:
    """格式化YAML值"""
    if isinstance(value, str):
        if "\n" in value or '"' in value or "'" in value:
            return f'"{value}"'
        return value
    elif isinstance(value, bool):
        return str(value).lower()
    elif value is None:
        return "null"
    else:
        return str(value)


def _redact_passwords(obj: dict) -> dict:
    """递归隐藏密码字段"""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == "password":
                result[key] = "********"
            elif isinstance(value, dict):
                result[key] = _redact_passwords(value)
            else:
                result[key] = value
        return result
    return obj


def _find_similar_keys(config: dict, target_key: str) -> list[str]:
    """查找相似的配置键"""
    all_keys = _get_all_keys(config)
    target_lower = target_key.lower()

    # 完全匹配
    exact_matches = [key for key in all_keys if key.lower() == target_lower]
    if exact_matches:
        return exact_matches

    # 包含匹配
    contains_matches = [key for key in all_keys if target_lower in key.lower() or key.lower() in target_lower]
    return sorted(contains_matches)


def _get_all_keys(obj: dict, prefix: str = "") -> list[str]:
    """获取所有配置键（包括嵌套）"""
    keys = []
    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        keys.append(full_key)
        if isinstance(value, dict):
            keys.extend(_get_all_keys(value, full_key))
    return keys
