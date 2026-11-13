"""首次对话的空唤醒（仅 @ / 仅唤醒前缀）必须带上 conversation。

回归 #10375 第 5 条：首次对话时 ``handle_empty_mention`` 把 ``conversation=None``
交给 ``request_llm``，使得下游 ``_ensure_persona_and_skills`` 在
``if not req.conversation: return`` 处提前返回，人格段落不会被注入；同一前置条件
还让该轮不写入会话历史（``internal.py`` 的 ``_save_to_history``）。

覆盖两条触发判据（``is_empty_mention`` 与 ``is_wake_prefix_only``），并在最后
把 ``request_llm`` 的入参重新组装成 ``ProviderRequest`` 走一遍真实的
``_ensure_persona_and_skills``，断言人格段落**确实**被注入 —— 只断言
``conversation`` 非空会漏掉「传了但下游仍然没注入」这种回归。

注意：``handle_empty_mention`` 末尾用 ``@session_waiter(60)`` 等待用户下一条消息，
真实环境下最长阻塞 60 秒。测试里压成 0（``timeout <= 0`` 时立即 ``stop()``），
只验证 ``request_llm`` 的入参；等待期间的行为不在本文件范围内。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.builtin_stars.astrbot.main as empty_mention_module
from astrbot.api.message_components import At, Plain
from astrbot.api.provider import ProviderRequest
from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.astr_main_agent import _ensure_persona_and_skills
from astrbot.core.utils.session_waiter import session_waiter as _session_waiter

UMO = "aiocqhttp:FriendMessage:10001"
SELF_ID = "10001"

PERSONA_PROMPT = "You are a helpful assistant for tests."
PERSONA = {"prompt": PERSONA_PROMPT, "skills": [], "tools": []}


@pytest.fixture(autouse=True)
def _instant_waiter(monkeypatch):
    """把「等待用户下一条消息」的 60 秒超时压成 0，避免测试空等。"""
    monkeypatch.setattr(
        empty_mention_module,
        "session_waiter",
        lambda _timeout: _session_waiter(0),
    )


class _FakeConversationManager:
    """只实现 handle_empty_mention 用到的那三个方法。"""

    def __init__(self, existing_cid: str | None = None, readable: bool = True):
        self._existing_cid = existing_cid
        self._readable = readable
        self.new_conversation_calls = 0
        self.conversation = SimpleNamespace(id="cid-new", persona_id=None)

    async def get_curr_conversation_id(self, umo):
        return self._existing_cid

    async def new_conversation(self, umo, platform_id=None):
        self.new_conversation_calls += 1
        self._existing_cid = "cid-new"
        return "cid-new"

    async def get_conversation(self, umo, conversation_id, create_if_not_exists=False):
        if not self._readable:
            return None
        if conversation_id == self._existing_cid:
            return self.conversation
        return None


class _FakeEvent:
    def __init__(self, messages):
        self.message_obj = SimpleNamespace(message=list(messages), self_id=SELF_ID)
        self.unified_msg_origin = UMO
        self.session_id = "session-10001"
        self.message_str = ""
        self.llm_requests: list[dict] = []
        self.extra: dict = {}
        self.stopped = False

    def get_messages(self):
        return self.message_obj.message

    def get_self_id(self):
        return self.message_obj.self_id

    def get_platform_id(self):
        return "aiocqhttp"

    def get_platform_name(self):
        return "aiocqhttp"

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)

    def set_extra(self, key, value):
        self.extra[key] = value

    def request_llm(self, **kwargs):
        self.llm_requests.append(kwargs)
        return "llm_request"

    def plain_result(self, text):
        return f"plain_result:{text}"

    def stop_event(self):
        self.stopped = True


def _make_star(cm):
    context = SimpleNamespace(
        conversation_manager=cm,
        astrbot_config_mgr=SimpleNamespace(),
        get_config=lambda umo=None: {
            "platform_settings": {
                "empty_mention_waiting": True,
                "empty_mention_waiting_need_reply": True,
            },
            "wake_prefix": ["/"],
        },
    )
    return Main(context)


def _make_persona_context(persona=PERSONA):
    """仿 tests/unit/test_astr_main_agent.py 的 mock_context。"""
    ctx = MagicMock()
    ctx.get_config.return_value = {}
    ctx.persona_manager.resolve_selected_persona = AsyncMock(
        return_value=("persona-id", persona, None, False)
    )
    ctx.subagent_orchestrator = None
    return ctx


async def _run(star, event):
    return [item async for item in star.handle_empty_mention(event)]


def _rebuild_request(event) -> ProviderRequest:
    """把 request_llm 的入参重新组装成 ProviderRequest，供下游链式断言使用。"""
    kwargs = event.llm_requests[0]
    return ProviderRequest(
        prompt=kwargs["prompt"],
        session_id=kwargs["session_id"],
        contexts=list(kwargs["contexts"]),
        system_prompt=kwargs["system_prompt"],
        conversation=kwargs["conversation"],
    )


@pytest.mark.parametrize(
    ("trigger", "messages"),
    [
        ("is_empty_mention（只有一个 @）", [At(qq=SELF_ID)]),
        ("is_wake_prefix_only（仅有唤醒词）", [Plain(text="/")]),
    ],
)
@pytest.mark.asyncio
async def test_first_conversation_passes_conversation(trigger, messages):
    """会话尚无 conversation id 时，也必须把新建的 conversation 传下去。"""
    cm = _FakeConversationManager(existing_cid=None)
    star = _make_star(cm)
    event = _FakeEvent(messages)

    assert await _run(star, event) == ["llm_request"], trigger

    assert cm.new_conversation_calls == 1
    assert len(event.llm_requests) == 1
    request = event.llm_requests[0]
    assert request["session_id"] == "cid-new"
    assert request["conversation"] is cm.conversation, (
        "首次对话必须传入 conversation，否则人格段落不会被注入、该轮也不会写入历史"
    )


@pytest.mark.asyncio
async def test_first_conversation_persona_actually_injected():
    """链式断言：首次对话的人格段落必须真的进入 system_prompt。

    只断言 ``conversation`` 非空属于契约层；这里把它喂给真实的
    ``_ensure_persona_and_skills``，确认没有在 ``if not req.conversation`` 处早退。
    """
    cm = _FakeConversationManager(existing_cid=None)
    star = _make_star(cm)
    event = _FakeEvent([At(qq=SELF_ID)])

    await _run(star, event)

    req = _rebuild_request(event)
    assert req.conversation is not None, "前置条件：首次对话也要带上 conversation"

    await _ensure_persona_and_skills(req, {}, _make_persona_context(), event)

    assert "# Persona Instructions" in req.system_prompt
    assert PERSONA_PROMPT in req.system_prompt


@pytest.mark.asyncio
async def test_existing_conversation_is_unchanged():
    """已有对话的路径不受影响，且不会新建对话。"""
    cm = _FakeConversationManager(existing_cid="cid-old")
    star = _make_star(cm)
    event = _FakeEvent([At(qq=SELF_ID)])

    await _run(star, event)

    assert cm.new_conversation_calls == 0
    assert event.llm_requests[0]["conversation"] is cm.conversation
    assert event.llm_requests[0]["session_id"] == "cid-old"


@pytest.mark.asyncio
async def test_unreadable_conversation_degrades_gracefully():
    """取不到 conversation 时不应抛错，退回「无对话」的旧行为。"""
    cm = _FakeConversationManager(existing_cid="cid-x", readable=False)
    star = _make_star(cm)
    event = _FakeEvent([At(qq=SELF_ID)])

    assert await _run(star, event) == ["llm_request"]
    assert event.llm_requests[0]["conversation"] is None
