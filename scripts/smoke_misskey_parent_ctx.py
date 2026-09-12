"""Misskey 父帖上下文注入 smoke 测试（PR #7893 follow-up）。

覆盖场景：
1. normal reply（payload 已展开 reply 对象）→ parent_ctx 在 message_str 尾部，body 在头部
2. 自帖跳过（reply.user.id == bot_self_id）
3. replyId-only → 通过 mock api.get_note 拉取
4. reply + renote 已展开 → 双注入
5. reply + renoteId（仅 ID）→ 通过 mock api.get_note 拉到引用帖，仍双注入（关键回归）
6. 关闭开关（include_reply_context=False）
7. API 失败：mock get_note 抛 RuntimeError → 优雅吞掉返回空
8. 完全独立帖（无 reply / replyId / renote / renoteId）→ 早返回路径
9. wake_prefix / 命令前缀兼容：body 是 "/help" 时 message_str 仍以 "/help" 开头
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from astrbot.core.platform.sources.misskey.misskey_adapter import (  # noqa: E402
    MisskeyPlatformAdapter,
)


class FakeAPI:
    def __init__(
        self,
        notes: dict[str, dict[str, Any]] | None = None,
        raise_for: set[str] | None = None,
    ) -> None:
        self.notes = notes or {}
        self.raise_for = raise_for or set()
        self.calls: list[str] = []

    async def get_note(self, note_id: str) -> dict[str, Any] | None:
        self.calls.append(note_id)
        if note_id in self.raise_for:
            raise RuntimeError(f"mock api error for {note_id}")
        return self.notes.get(note_id)


def make_adapter(
    *,
    include: bool = True,
    depth: int = 1,
    api: FakeAPI | None = None,
    bot_self_id: str = "bot_user",
    bot_username: str = "bot",
    max_text_length: int = 500,
) -> MisskeyPlatformAdapter:
    """绕开 __init__，直接构造一个最小可用对象用于测试 convert_message。"""
    adapter = MisskeyPlatformAdapter.__new__(MisskeyPlatformAdapter)
    adapter.include_reply_context = include
    adapter.reply_context_max_depth = depth
    adapter.reply_context_max_text_length = max_text_length
    adapter.api = api
    adapter.bot_self_id = bot_self_id
    adapter._bot_username = bot_username
    adapter._user_cache = {}
    # 让 _process_poll_data 可被调用而不抛
    adapter._process_poll_data = lambda *a, **kw: None  # type: ignore[method-assign]
    return adapter


def user(uid: str, name: str = "Bob", username: str = "bob") -> dict[str, Any]:
    return {"id": uid, "username": username, "name": name}


def note(
    nid: str,
    *,
    text: str = "",
    user_id: str = "u_other",
    username: str = "bob",
    name: str = "Bob",
    files: list | None = None,
    reply: dict | None = None,
    renote: dict | None = None,
    reply_id: str | None = None,
    renote_id: str | None = None,
) -> dict[str, Any]:
    n: dict[str, Any] = {
        "id": nid,
        "text": text,
        "user": user(user_id, name=name, username=username),
        "files": files or [],
    }
    if reply is not None:
        n["reply"] = reply
    if renote is not None:
        n["renote"] = renote
    if reply_id is not None:
        n["replyId"] = reply_id
    if renote_id is not None:
        n["renoteId"] = renote_id
    return n


# convert_message 内部依赖 extract_sender_info / create_base_message / cache_user_info /
# process_at_mention / process_files。直接构造 raw_data 跑过去。

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, hint: str = "") -> None:
    results.append((name, ok, hint))
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {name}" + (f"  ::  {hint}" if hint and not ok else ""))


async def case_normal_reply() -> None:
    parent = note("n0", text="原帖正文 hello", user_id="u_alice", username="alice", name="Alice")
    raw = note("n1", text="@bot 这帖在说啥", user_id="u_b", username="bobby", reply=parent)

    adapter = make_adapter()
    msg = await adapter.convert_message(raw)

    body_first = msg.message_str.startswith("@bot 这帖在说啥") or msg.message_str.startswith("这帖在说啥")
    has_separator = "\n---\n" in msg.message_str
    has_parent_block = "[被回复的原帖]" in msg.message_str
    has_parent_text = "原帖正文 hello" in msg.message_str
    parent_after_body = msg.message_str.find("[被回复的原帖]") > 0  # 不是 0

    check(
        "case1 normal reply: body 在头部 + parent 在尾部",
        body_first and has_separator and has_parent_block and has_parent_text and parent_after_body,
        f"got message_str={msg.message_str!r}",
    )


async def case_self_authored_parent() -> None:
    parent = note("n0", text="bot 自己的帖", user_id="bot_user", username="bot", name="Bot")
    raw = note("n1", text="hi", reply=parent)

    adapter = make_adapter(bot_self_id="bot_user")
    msg = await adapter.convert_message(raw)

    check(
        "case2 自帖跳过：parent_ctx 不应注入",
        "[被回复的原帖]" not in msg.message_str and "\n---\n" not in msg.message_str,
        f"got message_str={msg.message_str!r}",
    )


async def case_reply_id_only_fetch() -> None:
    fetched_parent = note(
        "n0", text="原帖通过 API 拉到", user_id="u_a", username="alice", name="Alice"
    )
    api = FakeAPI(notes={"n0": fetched_parent})

    raw = note("n1", text="hi", reply_id="n0")
    adapter = make_adapter(api=api)
    msg = await adapter.convert_message(raw)

    check(
        "case3 replyId-only：通过 API 注入",
        "原帖通过 API 拉到" in msg.message_str and "[被回复的原帖]" in msg.message_str
        and api.calls == ["n0"],
        f"calls={api.calls} got={msg.message_str!r}",
    )


async def case_reply_with_quote_expanded() -> None:
    parent = note("n0", text="被回复帖", user_id="u_a", username="alice")
    quoted = note("nq", text="被引用帖", user_id="u_q", username="quotee")
    raw = note("n1", text="reply with quote", reply=parent, renote=quoted)

    adapter = make_adapter()
    msg = await adapter.convert_message(raw)

    check(
        "case4 reply+renote 都展开：双注入",
        "被回复帖" in msg.message_str
        and "被引用帖" in msg.message_str
        and "[被回复的原帖]" in msg.message_str
        and "[被引用/转发的原帖]" in msg.message_str,
        f"got={msg.message_str!r}",
    )


async def case_reply_with_quote_id_only() -> None:
    """关键回归：reply 已展开但 renote 仅给 renoteId，应通过 API 拉到引用帖。"""
    parent = note("n0", text="被回复帖", user_id="u_a", username="alice")
    fetched_quote = note("nq", text="API 拉到的被引用帖", user_id="u_q", username="quotee")
    api = FakeAPI(notes={"nq": fetched_quote})

    raw = note("n1", text="hi", reply=parent, renote_id="nq")
    adapter = make_adapter(api=api)
    msg = await adapter.convert_message(raw)

    check(
        "case5 reply+renoteId（关键回归）：API fallback 拉到引用帖",
        "被回复帖" in msg.message_str
        and "API 拉到的被引用帖" in msg.message_str
        and "[被引用/转发的原帖]" in msg.message_str
        and api.calls == ["nq"],
        f"calls={api.calls} got={msg.message_str!r}",
    )


async def case_disabled() -> None:
    parent = note("n0", text="原帖", user_id="u_a", username="alice")
    raw = note("n1", text="hi", reply=parent)

    adapter = make_adapter(include=False)
    msg = await adapter.convert_message(raw)

    check(
        "case6 关闭开关：parent_ctx 完全不注入",
        "[被回复的原帖]" not in msg.message_str and "\n---\n" not in msg.message_str,
        f"got={msg.message_str!r}",
    )


async def case_api_failure() -> None:
    api = FakeAPI(raise_for={"n_bad"})
    raw = note("n1", text="hi", reply_id="n_bad")
    adapter = make_adapter(api=api)
    msg = await adapter.convert_message(raw)

    check(
        "case7 API 失败：优雅吞掉，无 parent_ctx 但 body 完整",
        "hi" in msg.message_str and "[被回复的原帖]" not in msg.message_str,
        f"got={msg.message_str!r}",
    )


async def case_standalone_no_parent() -> None:
    """完全独立帖：无 reply / replyId / renote / renoteId，应走早返回路径。"""
    api = FakeAPI()
    raw = note("n1", text="just a standalone note")
    adapter = make_adapter(api=api)
    msg = await adapter.convert_message(raw)

    check(
        "case8 独立帖早返回：API 不被调用 + parent_ctx 空",
        api.calls == []
        and "[被回复的原帖]" not in msg.message_str
        and "\n---\n" not in msg.message_str,
        f"calls={api.calls} got={msg.message_str!r}",
    )


async def case_command_compat() -> None:
    """关键回归：body 以命令开头时（"/help"），尾部追加 parent_ctx 不影响命令前缀匹配。"""
    parent = note("n0", text="原帖", user_id="u_a", username="alice")
    raw = note("n1", text="/help", reply=parent)
    adapter = make_adapter()
    msg = await adapter.convert_message(raw)

    starts_with_cmd = msg.message_str.startswith("/help")
    has_parent_after = "[被回复的原帖]" in msg.message_str

    check(
        "case9 命令兼容：message_str 以 /help 开头 + parent 在尾部",
        starts_with_cmd and has_parent_after,
        f"got={msg.message_str!r}",
    )


async def case_get_note_cancelled_propagates() -> None:
    """get_note 必须把 asyncio.CancelledError 原样向上抛，否则 shutdown 会卡住。"""
    from astrbot.core.platform.sources.misskey.misskey_api import MisskeyAPI

    api = MisskeyAPI.__new__(MisskeyAPI)

    async def fake_make_request(*a: Any, **kw: Any) -> None:
        raise asyncio.CancelledError()

    api._make_request = fake_make_request  # type: ignore[method-assign]

    raised: Exception | None = None
    try:
        await api.get_note("any-id")
    except asyncio.CancelledError as e:
        raised = e
    except Exception as e:  # noqa: BLE001
        raised = e

    check(
        "case10 get_note: CancelledError 原样向上抛",
        isinstance(raised, asyncio.CancelledError),
        f"raised={type(raised).__name__ if raised else 'None'}",
    )


async def case_get_note_normal_exception_swallowed() -> None:
    """普通异常（403/404/网络错）应继续被吞掉返回 None，保持原行为。"""
    from astrbot.core.platform.sources.misskey.misskey_api import MisskeyAPI

    api = MisskeyAPI.__new__(MisskeyAPI)

    async def fake_make_request(*a: Any, **kw: Any) -> None:
        raise RuntimeError("HTTP 403 forbidden")

    api._make_request = fake_make_request  # type: ignore[method-assign]
    result = await api.get_note("any-id")

    check(
        "case11 get_note: 普通异常仍吞掉返回 None",
        result is None,
        f"result={result!r}",
    )


async def main() -> None:
    await case_normal_reply()
    await case_self_authored_parent()
    await case_reply_id_only_fetch()
    await case_reply_with_quote_expanded()
    await case_reply_with_quote_id_only()
    await case_disabled()
    await case_api_failure()
    await case_standalone_no_parent()
    await case_command_compat()
    await case_get_note_cancelled_propagates()
    await case_get_note_normal_exception_swallowed()

    failed = [n for n, ok, _ in results if not ok]
    print()
    print(f"== summary: {len(results) - len(failed)}/{len(results)} passed ==")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
