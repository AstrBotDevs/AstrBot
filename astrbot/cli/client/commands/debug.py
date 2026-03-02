"""调试工具命令 - astr ping / astr status / astr test"""

import json
import os
import time

import click

from ..connection import (
    get_data_path,
    load_auth_token,
    load_connection_info,
    send_message,
)
from ..output import output_response


@click.command(help="测试与 AstrBot 的连通性和延迟")
@click.option("-c", "--count", default=1, type=int, help="测试次数（默认 1）")
def ping(count: int) -> None:
    """测试连通性和延迟

    \b
    示例:
      astr ping               单次测试
      astr ping -c 3          测试 3 次
    """
    for i in range(count):
        start = time.time()
        response = send_message("/help")
        elapsed = (time.time() - start) * 1000

        if response.get("status") == "success":
            click.echo(f"pong: {elapsed:.0f}ms")
        else:
            error = response.get("error", "Unknown error")
            click.echo(f"failed: {error}", err=True)
            raise SystemExit(1)


@click.command(help="查看 AstrBot 连接状态")
def status() -> None:
    """查看 AstrBot 连接状态

    检查连接文件、token、以及服务可达性
    """
    data_dir = get_data_path()

    # 检查连接文件
    connection_info = load_connection_info(data_dir)
    if connection_info is not None:
        conn_type = connection_info.get("type", "unknown")
        if conn_type == "unix":
            path = connection_info.get("path", "N/A")
            click.echo("连接类型: Unix Socket")
            click.echo(f"路径: {path}")
            click.echo(f"文件存在: {os.path.exists(path)}")
        elif conn_type == "tcp":
            host = connection_info.get("host", "N/A")
            port = connection_info.get("port", "N/A")
            click.echo("连接类型: TCP Socket")
            click.echo(f"地址: {host}:{port}")
        else:
            click.echo(f"连接类型: {conn_type} (未知)")
    else:
        click.echo("连接文件: 未找到 (.cli_connection)")

    # 检查 token
    token = load_auth_token()
    if token:
        click.echo(f"Token: 已配置 ({token[:8]}...)")
    else:
        click.echo("Token: 未配置")

    # 测试连通性
    click.echo("---")
    start = time.time()
    response = send_message("/help")
    elapsed = (time.time() - start) * 1000

    if response.get("status") == "success":
        click.echo(f"服务状态: 在线 ({elapsed:.0f}ms)")
    else:
        error = response.get("error", "Unknown error")
        click.echo(f"服务状态: 离线 ({error})")


@click.group(help="测试工具 (子命令: echo/plugin)")
def test() -> None:
    """测试工具命令组"""


@test.command(name="echo", help="发送消息并验证回环")
@click.argument("message", nargs=-1, required=True)
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def test_echo(message: tuple[str, ...], use_json: bool) -> None:
    """发送消息验证回环

    \b
    示例:
      astr test echo Hello      发送 Hello 并查看响应
    """
    msg = " ".join(message)
    response = send_message(msg)

    if use_json:
        click.echo(json.dumps(response, ensure_ascii=False, indent=2))
    else:
        if response.get("status") == "success":
            click.echo(f"发送: {msg}")
            click.echo(f"响应: {response.get('response', '')}")
        else:
            error = response.get("error", "Unknown error")
            click.echo(f"发送: {msg}")
            click.echo(f"错误: {error}", err=True)
            raise SystemExit(1)


@test.command(name="plugin", help="测试插件命令（发送 /<cmd> <args>）")
@click.argument("name")
@click.argument("input_text", nargs=-1, required=True)
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def test_plugin(name: str, input_text: tuple[str, ...], use_json: bool) -> None:
    """测试插件命令

    name 是插件注册的命令名（非插件名），会拼接为 /<name> <input> 发送。

    \b
    示例:
      astr test plugin probe cpu       → 发送 /probe cpu
      astr test plugin help             → 发送 /help
    """
    msg = f"/{name} {' '.join(input_text)}"
    response = send_message(msg)
    output_response(response, use_json)
