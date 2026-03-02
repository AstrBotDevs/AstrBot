"""跨会话浏览命令组 - astr session"""

import json
import sys

import click

from ..connection import (
    get_session_history,
    list_session_conversations,
    list_sessions,
)


@click.group(help="跨会话浏览 — 查看任意平台的会话和聊天记录 (ls/convs/history)")
def session() -> None:
    """跨会话浏览命令组"""


@session.command(name="ls", help="列出所有会话（跨平台：QQ/TG/微信/CLI…）")
@click.option("--page", "-p", type=int, default=1, help="页码 (默认 1)")
@click.option("--size", "-s", type=int, default=20, help="每页数量 (默认 20)")
@click.option("--platform", "-P", type=str, default=None, help="按平台过滤")
@click.option("--search", "-q", type=str, default=None, help="搜索关键词")
@click.option("-j", "--json-output", "use_json", is_flag=True, help="输出原始 JSON")
def session_ls(
    page: int, size: int, platform: str | None, search: str | None, use_json: bool
) -> None:
    """列出所有会话"""
    resp = list_sessions(
        page=page,
        page_size=size,
        platform=platform,
        search_query=search,
    )

    if resp.get("status") != "success":
        click.echo(f"[ERROR] {resp.get('error', 'Unknown error')}", err=True)
        sys.exit(1)

    if use_json:
        click.echo(json.dumps(resp, ensure_ascii=False, indent=2))
        return

    sessions = resp.get("sessions", [])
    if not sessions:
        click.echo("没有找到会话。")
        return

    click.echo(f"{'#':<4} {'会话 ID':<45} {'当前对话标题':<20} {'人设'}")
    click.echo("-" * 90)
    for i, s in enumerate(sessions, start=(page - 1) * size + 1):
        sid = s.get("session_id", "?")
        title = s.get("title") or "(无标题)"
        persona = s.get("persona_name") or "-"
        # 截断过长的字段
        if len(sid) > 43:
            sid = sid[:40] + "..."
        if len(title) > 18:
            title = title[:15] + "..."
        click.echo(f"{i:<4} {sid:<45} {title:<20} {persona}")

    total = resp.get("total", 0)
    total_pages = resp.get("total_pages", 0)
    click.echo(f"\n共 {total} 个会话，第 {page}/{total_pages} 页")


@session.command(name="convs", help="查看指定会话下的对话列表")
@click.argument("session_id")
@click.option("--page", "-p", type=int, default=1, help="页码 (默认 1)")
@click.option("--size", "-s", type=int, default=20, help="每页数量 (默认 20)")
@click.option("-j", "--json-output", "use_json", is_flag=True, help="输出原始 JSON")
def session_convs(session_id: str, page: int, size: int, use_json: bool) -> None:
    """查看指定会话的对话列表"""
    resp = list_session_conversations(
        session_id=session_id,
        page=page,
        page_size=size,
    )

    if resp.get("status") != "success":
        click.echo(f"[ERROR] {resp.get('error', 'Unknown error')}", err=True)
        sys.exit(1)

    if use_json:
        click.echo(json.dumps(resp, ensure_ascii=False, indent=2))
        return

    convs = resp.get("conversations", [])
    if not convs:
        click.echo(f"会话 {session_id} 没有对话。")
        return

    click.echo(f"会话: {session_id}")
    click.echo(f"当前对话: {resp.get('current_cid', '无')}")
    click.echo("")
    click.echo(f"{'#':<4} {'对话 ID':<38} {'标题':<20} {'Token':<8} {'当前'}")
    click.echo("-" * 80)
    for i, c in enumerate(convs, start=(page - 1) * size + 1):
        cid = c.get("cid", "?")
        title = c.get("title") or "(无标题)"
        token = c.get("token_usage", 0)
        is_curr = "*" if c.get("is_current") else ""
        if len(title) > 18:
            title = title[:15] + "..."
        click.echo(f"{i:<4} {cid:<38} {title:<20} {token:<8} {is_curr}")

    total = resp.get("total", 0)
    total_pages = resp.get("total_pages", 0)
    click.echo(f"\n共 {total} 个对话，第 {page}/{total_pages} 页")


@session.command(name="history", help="查看聊天记录（用户/AI 交替显示）")
@click.argument("session_id")
@click.option(
    "-c", "--conversation-id", type=str, default=None, help="对话 ID (默认当前对话)"
)
@click.option("--page", "-p", type=int, default=1, help="页码 (默认 1)")
@click.option("--size", "-s", type=int, default=10, help="每页数量 (默认 10)")
@click.option("-j", "--json-output", "use_json", is_flag=True, help="输出原始 JSON")
def session_history(
    session_id: str,
    conversation_id: str | None,
    page: int,
    size: int,
    use_json: bool,
) -> None:
    """查看指定会话的聊天记录"""
    resp = get_session_history(
        session_id=session_id,
        conversation_id=conversation_id,
        page=page,
        page_size=size,
    )

    if resp.get("status") != "success":
        click.echo(f"[ERROR] {resp.get('error', 'Unknown error')}", err=True)
        sys.exit(1)

    if use_json:
        click.echo(json.dumps(resp, ensure_ascii=False, indent=2))
        return

    _render_history(resp, session_id, page)


def _render_history(resp: dict, session_id: str, page: int) -> None:
    """简洁地渲染聊天记录：用户/AI 交替显示。"""
    history = resp.get("history", [])
    total_pages = resp.get("total_pages", 0)
    cid = resp.get("conversation_id")

    click.echo(f"会话: {session_id}")
    click.echo(f"对话: {cid or '(无)'}  页码: {page}/{total_pages}")
    click.echo("-" * 60)

    if not history:
        click.echo("(无聊天记录)")
        return

    for msg in history:
        # 新格式：msg 是 {"role": "user"|"assistant", "text": "..."}
        if isinstance(msg, dict):
            role = msg.get("role", "?")
            text = msg.get("text", "")
            label = "You" if role == "user" else "AI"
            click.echo(f"{label}: {text}")
        else:
            # 兼容旧格式（纯字符串）
            click.echo(msg)
        click.echo()
