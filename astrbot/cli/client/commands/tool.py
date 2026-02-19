"""函数工具管理命令组 - astr tool"""

import json
import sys

import click

from ..connection import call_tool, list_tools


@click.group(help="函数工具管理 (子命令: ls/info/call)")
def tool() -> None:
    """函数工具管理命令组"""


@tool.command(name="ls", help="列出所有注册的函数工具")
@click.option(
    "--origin", "-o", type=str, default="", help="按来源过滤: plugin/mcp/builtin"
)
@click.option("-j", "--json-output", "use_json", is_flag=True, help="输出原始 JSON")
def tool_ls(origin: str, use_json: bool) -> None:
    """列出所有注册的函数工具"""
    resp = list_tools()

    if resp.get("status") != "success":
        click.echo(f"[ERROR] {resp.get('error', 'Unknown error')}", err=True)
        sys.exit(1)

    tools = resp.get("tools", [])
    if not tools:
        raw = resp.get("response", "")
        if raw:
            try:
                tools = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass

    if origin:
        tools = [
            t
            for t in tools
            if t.get("origin") == origin or t.get("origin_name") == origin
        ]

    if use_json:
        click.echo(json.dumps(tools, ensure_ascii=False, indent=2))
        return

    if not tools:
        click.echo("没有注册的函数工具。")
        return

    click.echo(f"{'名称':<25} {'来源':<10} {'来源名':<18} {'状态':<6} {'描述'}")
    click.echo("-" * 90)
    for t in tools:
        name = t.get("name", "?")
        ori = t.get("origin", "?")
        ori_name = t.get("origin_name", "?")
        active = "启用" if t.get("active", True) else "停用"
        desc = (t.get("description") or "")[:40]
        click.echo(f"{name:<25} {ori:<10} {ori_name:<18} {active:<6} {desc}")

    click.echo(f"\n共 {len(tools)} 个工具")


@tool.command(name="info", help="查看工具详细信息")
@click.argument("name")
def tool_info(name: str) -> None:
    """查看工具详细信息"""
    resp = list_tools()

    if resp.get("status") != "success":
        click.echo(f"[ERROR] {resp.get('error', 'Unknown error')}", err=True)
        sys.exit(1)

    tools = resp.get("tools", [])
    if not tools:
        raw = resp.get("response", "")
        if raw:
            try:
                tools = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass

    matched = [t for t in tools if t.get("name") == name]
    if not matched:
        click.echo(f"未找到工具: {name}")
        sys.exit(1)

    t = matched[0]
    click.echo(f"名称:     {t.get('name')}")
    click.echo(f"描述:     {t.get('description', '无')}")
    click.echo(f"来源:     {t.get('origin', '?')} ({t.get('origin_name', '?')})")
    click.echo(f"状态:     {'启用' if t.get('active', True) else '停用'}")

    params = t.get("parameters")
    if params:
        click.echo("参数:")
        props = params.get("properties", {})
        required = params.get("required", [])
        for pname, pinfo in props.items():
            req_mark = "*" if pname in required else " "
            ptype = pinfo.get("type", "any")
            pdesc = pinfo.get("description", "")
            click.echo(f"  {req_mark} {pname} ({ptype}): {pdesc}")


@tool.command(name="call", help="调用指定的函数工具")
@click.argument("name")
@click.argument("args_json", required=False, default="{}")
@click.option("-t", "--timeout", type=float, default=60.0, help="超时时间（秒）")
def tool_call(name: str, args_json: str, timeout: float) -> None:
    """调用指定的函数工具

    ARGS_JSON: JSON 格式的参数，例如 '{"key": "value"}'
    """
    try:
        tool_args = json.loads(args_json)
    except json.JSONDecodeError as e:
        click.echo(f"[ERROR] 参数 JSON 格式错误: {e}", err=True)
        sys.exit(1)

    if not isinstance(tool_args, dict):
        click.echo("[ERROR] 参数必须是 JSON 对象", err=True)
        sys.exit(1)

    resp = call_tool(name, tool_args, timeout=timeout)

    if resp.get("status") != "success":
        click.echo(f"[ERROR] {resp.get('error', 'Unknown error')}", err=True)
        sys.exit(1)

    click.echo(resp.get("response", "(无返回值)"))
