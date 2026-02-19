"""交互式 REPL 模式 - astr interactive"""

import click

from ..connection import send_message
from ..output import format_response


@click.command(help="进入交互式 REPL 模式")
def interactive() -> None:
    """进入交互式 REPL 模式

    \b
    特性:
      - 直接输入消息发送给 AstrBot
      - 支持 CLI 子命令（如 conv ls, plugin ls）
      - /quit 或 Ctrl+C 退出
      - 支持命令历史（readline）

    \b
    示例:
      astr interactive          进入交互模式
      astr -i                   同上（快捷方式）
    """
    # 子命令映射：REPL 中输入的前缀 -> 对应的内部命令格式
    _REPL_COMMAND_MAP = {
        "conv ls": "/ls",
        "conv new": "/new",
        "conv switch": "/switch",
        "conv del": "/del",
        "conv rename": "/rename",
        "conv reset": "/reset",
        "conv history": "/history",
        "plugin ls": "/plugin ls",
        "plugin on": "/plugin on",
        "plugin off": "/plugin off",
        "plugin help": "/plugin help",
        "provider": "/provider",
        "model": "/model",
        "key": "/key",
        "help": "/help",
        "sid": "/sid",
        "t2i": "/t2i",
        "tts": "/tts",
    }

    # 尝试启用 readline 支持命令历史
    try:
        import readline  # noqa: F401
    except ImportError:
        pass

    click.echo("AstrBot 交互模式 (输入 /quit 或 Ctrl+C 退出)")
    click.echo("---")

    while True:
        try:
            line = input("astr> ").strip()
        except (EOFError, KeyboardInterrupt):
            click.echo("\n再见!")
            break

        if not line:
            continue

        if line in ("/quit", "/exit", "quit", "exit"):
            click.echo("再见!")
            break

        # 尝试匹配 REPL 子命令
        msg = _resolve_repl_command(line, _REPL_COMMAND_MAP)

        response = send_message(msg)
        if response.get("status") == "success":
            formatted = format_response(response)
            if formatted:
                click.echo(formatted)
        else:
            error = response.get("error", "Unknown error")
            click.echo(f"Error: {error}", err=True)


def _resolve_repl_command(line: str, command_map: dict[str, str]) -> str:
    """将 REPL 输入解析为内部命令

    先尝试匹配最长前缀的子命令映射，未匹配则原样发送。

    Args:
        line: 用户输入
        command_map: 子命令映射表

    Returns:
        要发送的消息
    """
    # 按键长度降序匹配，确保 "conv ls" 优先于 "conv"
    for prefix in sorted(command_map, key=len, reverse=True):
        if line == prefix:
            return command_map[prefix]
        if line.startswith(prefix + " "):
            rest = line[len(prefix) :].strip()
            return f"{command_map[prefix]} {rest}"

    return line
