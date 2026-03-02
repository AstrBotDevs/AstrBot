"""send 命令 - 发送消息给 AstrBot"""

import sys

import click

from ..connection import send_message
from ..output import fix_git_bash_path, output_response


@click.command(help="发送消息给 AstrBot")
@click.argument("message", nargs=-1)
@click.option("-s", "--socket", "socket_path", default=None, help="Unix socket 路径")
@click.option("-t", "--timeout", default=30.0, type=float, help="超时时间（秒）")
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON 响应")
def send(
    message: tuple[str, ...], socket_path: str | None, timeout: float, use_json: bool
) -> None:
    """发送消息给 AstrBot

    \b
    示例:
      astr send 你好
      astr send /help
      astr send plugin ls
      echo "你好" | astr send
    """
    if message:
        msg = " ".join(message)
        msg = fix_git_bash_path(msg)
    elif not sys.stdin.isatty():
        msg = sys.stdin.read().strip()
    else:
        click.echo("Error: 请提供消息内容", err=True)
        raise SystemExit(1)

    if not msg:
        click.echo("Error: 消息内容为空", err=True)
        raise SystemExit(1)

    do_send(msg, socket_path, timeout, use_json)


def do_send(msg: str, socket_path: str | None, timeout: float, use_json: bool) -> None:
    """执行消息发送并输出结果"""
    response = send_message(msg, socket_path, timeout)
    output_response(response, use_json)
