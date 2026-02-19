"""插件管理命令组 - astr plugin"""

import click

from ..connection import send_message
from ..output import output_response


@click.group(help="插件管理 (子命令: ls/on/off/help)")
def plugin() -> None:
    """插件管理命令组"""


@plugin.command(name="ls", help="列出已安装插件")
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def plugin_ls(use_json: bool) -> None:
    """列出已安装插件"""
    response = send_message("/plugin ls")
    output_response(response, use_json)


@plugin.command(name="on", help="启用插件")
@click.argument("name")
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def plugin_on(name: str, use_json: bool) -> None:
    """启用插件"""
    response = send_message(f"/plugin on {name}")
    output_response(response, use_json)


@plugin.command(name="off", help="禁用插件")
@click.argument("name")
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def plugin_off(name: str, use_json: bool) -> None:
    """禁用插件"""
    response = send_message(f"/plugin off {name}")
    output_response(response, use_json)


@plugin.command(name="help", help="获取插件帮助")
@click.argument("name", default="", required=False)
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def plugin_help(name: str, use_json: bool) -> None:
    """获取插件帮助"""
    cmd = "/plugin help" if not name else f"/plugin help {name}"
    response = send_message(cmd)
    output_response(response, use_json)
