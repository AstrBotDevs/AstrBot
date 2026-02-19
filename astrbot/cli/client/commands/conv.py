"""会话管理命令组 - astr conv"""

import click

from ..connection import send_message
from ..output import output_response


@click.group(help="会话管理 (子命令: ls/new/switch/del/rename/reset/history)")
def conv() -> None:
    """会话管理命令组"""


@conv.command(name="ls", help="列出当前会话的所有对话")
@click.argument("page", default="", required=False)
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def conv_ls(page: str, use_json: bool) -> None:
    """列出对话"""
    cmd = "/ls" if not page else f"/ls {page}"
    response = send_message(cmd)
    output_response(response, use_json)


@conv.command(name="new", help="创建新对话")
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def conv_new(use_json: bool) -> None:
    """创建新对话"""
    response = send_message("/new")
    output_response(response, use_json)


@conv.command(name="switch", help="按序号切换对话")
@click.argument("index", type=int)
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def conv_switch(index: int, use_json: bool) -> None:
    """按序号切换对话"""
    response = send_message(f"/switch {index}")
    output_response(response, use_json)


@conv.command(name="del", help="删除当前对话")
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def conv_del(use_json: bool) -> None:
    """删除当前对话"""
    response = send_message("/del")
    output_response(response, use_json)


@conv.command(name="rename", help="重命名当前对话")
@click.argument("name")
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def conv_rename(name: str, use_json: bool) -> None:
    """重命名当前对话"""
    response = send_message(f"/rename {name}")
    output_response(response, use_json)


@conv.command(name="reset", help="重置当前 LLM 会话")
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def conv_reset(use_json: bool) -> None:
    """重置当前 LLM 会话"""
    response = send_message("/reset")
    output_response(response, use_json)


@conv.command(name="history", help="查看对话记录")
@click.argument("page", default="", required=False)
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
def conv_history(page: str, use_json: bool) -> None:
    """查看对话记录"""
    cmd = "/history" if not page else f"/history {page}"
    response = send_message(cmd)
    output_response(response, use_json)
