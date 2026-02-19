"""输出格式化模块 - 响应格式化与输出

从 __main__.py 提取的输出相关功能。
"""

import json
import re

import click


def format_response(response: dict) -> str:
    """格式化响应输出

    处理：
    1. 分段回复（每行一句）
    2. 图片占位符

    Args:
        response: 响应字典

    Returns:
        格式化后的字符串
    """
    if response.get("status") != "success":
        return ""

    text = response.get("response", "")
    images = response.get("images", [])
    image_count = len(images)

    lines = text.split("\n")

    if image_count > 0:
        if image_count == 1:
            lines.append("[图片]")
        else:
            lines.append(f"[{image_count}张图片]")

    return "\n".join(lines)


def fix_git_bash_path(message: str) -> str:
    """修复 Git Bash 路径转换问题

    Git Bash (MSYS2) 会把 /plugin ls 转换为 C:/Program Files/Git/plugin ls
    检测并还原原始命令

    Args:
        message: 被转换后的消息

    Returns:
        修复后的消息
    """
    pattern = r"[A-Z]:/(Program Files/Git|msys[0-9]+/[^/]+)/([^/]+)"
    match = re.match(pattern, message)

    if match:
        command = match.group(2)
        rest = message[match.end() :].lstrip()
        if rest:
            return f"/{command} {rest}"
        return f"/{command}"

    return message


def output_response(response: dict, use_json: bool) -> None:
    """统一输出响应

    Args:
        response: 响应字典
        use_json: 是否输出原始JSON
    """
    if use_json:
        click.echo(json.dumps(response, ensure_ascii=False, indent=2))
    else:
        if response.get("status") == "success":
            formatted = format_response(response)
            click.echo(formatted)
        else:
            error = response.get("error", "Unknown error")
            click.echo(f"Error: {error}", err=True)
            raise SystemExit(1)
