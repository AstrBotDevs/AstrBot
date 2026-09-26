"""Regression coverage for requests prepared before the session lock."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.agent.message import Message
from astrbot.core.astr_main_agent import (
    LLM_ERROR_MESSAGE_EXTRA_KEY,
    MainAgentBuildConfig,
    collect_initial_request,
)
from astrbot.core.db.po import Conversation
from astrbot.core.message.components import Plain
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.utils.session_lock import session_lock_manager


@pytest.fixture
def queued_history():
    """Provide detached DB snapshots and real request/history entry points."""
    umo = "test:GroupMessage:group"
    stored = Conversation(
        platform_id="test", user_id=umo, cid="original", history="[]"
    )

    async def read(umo, cid):
        assert cid == stored.cid
        return copy.deepcopy(stored)

    async def write(umo, cid, *, history, token_usage=None):
        assert cid == stored.cid
        stored.history = json.dumps(history)

    manager = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value=stored.cid),
        get_conversation=AsyncMock(side_effect=read),
        update_conversation=AsyncMock(side_effect=write),
    )
    context = MagicMock()
    context.conversation_manager = manager
    context.get_using_provider_async = AsyncMock(return_value=object())
    context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": False,
            "active_reply": {"enable": True},
        }
    }
    main = Main.__new__(Main)
    main.context = context
    main.group_chat_context = SimpleNamespace(
        need_active_reply=AsyncMock(return_value=True),
    )
    stage = InternalAgentSubStage()
    stage.conv_manager = manager

    def event(text):
        extras = {}
        result = MagicMock(spec=AstrMessageEvent)
        result.unified_msg_origin = umo
        result.session_id = "group"
        result.message_str = text
        result.message_obj = SimpleNamespace(message=[Plain(text=text)])
        result.get_extra.side_effect = lambda key, default=None: extras.get(key, default)
        result.set_extra.side_effect = extras.__setitem__
        result.request_llm.side_effect = lambda **kwargs: AstrMessageEvent.request_llm(
            result, **kwargs
        )
        return result

    return SimpleNamespace(
        umo=umo, stored=stored, manager=manager, context=context,
        main=main, stage=stage, event=event,
        config=MainAgentBuildConfig(tool_call_timeout=60),
    )


@pytest.mark.asyncio
async def test_queued_active_replies_keep_preceding_turns(queued_history):
    """Two early snapshots must not overwrite turns saved while they wait."""
    env = queued_history
    entered = asyncio.Event()
    inputs = []

    async def run(event):
        entered.set()
        async with session_lock_manager.acquire_lock(env.umo):
            req, _ = await collect_initial_request(event, env.context, env.config)
            inputs.append(copy.deepcopy(req.contexts))
            messages = [Message.model_validate(item) for item in req.contexts]
            messages.extend([
                Message(role="user", content=req.prompt),
                Message(role="assistant", content=f"reply {req.prompt}"),
            ])
            await env.stage._save_to_history(
                event, req,
                LLMResponse(role="assistant", completion_text=f"reply {req.prompt}"),
                messages, runner_stats=None,
            )

    events = [env.event("second"), env.event("third")]
    tasks = []
    try:
        async with session_lock_manager.acquire_lock(env.umo):
            for event in events:
                requests = [req async for req in env.main.on_message(event)]
                assert len(requests) == 1
                assert requests[0].conversation.history == "[]"
                event.set_extra("provider_request", requests[0])
                entered.clear()
                tasks.append(asyncio.create_task(run(event)))
                await asyncio.wait_for(entered.wait(), timeout=2)
            # Finish the preceding turn only after both requests are queued.
            await env.stage._save_to_history(
                env.event("first"),
                ProviderRequest(conversation=copy.deepcopy(env.stored)),
                LLMResponse(role="assistant", completion_text="reply first"),
                [Message(role="user", content="first"),
                 Message(role="assistant", content="reply first")],
                runner_stats=None,
            )
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert [item["content"] for item in inputs[0]] == ["first", "reply first"]
    assert [item["content"] for item in inputs[1]] == [
        "first", "reply first", "second", "reply second",
    ]
    assert [item["content"] for item in json.loads(env.stored.history)] == [
        "first", "reply first", "second", "reply second", "third", "reply third",
    ]


@pytest.mark.asyncio
async def test_refresh_keeps_bound_conversation_and_original_request(queued_history):
    """Refreshing must not redirect a queued turn to a newly selected chat."""
    env = queued_history
    event = env.event("queued")
    request = ProviderRequest(prompt="queued", conversation=copy.deepcopy(env.stored))
    event.set_extra("provider_request", request)
    env.stored.history = json.dumps([{"role": "assistant", "content": "latest"}])
    env.stored.persona_id = "updated-persona"
    env.manager.get_curr_conversation_id.return_value = "different-conversation"

    result, _ = await collect_initial_request(event, env.context, env.config)

    assert result.contexts == [{"role": "assistant", "content": "latest"}]
    assert result.conversation.cid == "original"
    assert result.conversation.persona_id == "updated-persona"
    assert request.conversation.history == "[]"
    assert request.contexts == []
    env.manager.get_conversation.assert_awaited_once_with(env.umo, "original")
    env.manager.get_curr_conversation_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_deleted_bound_conversation_does_not_use_stale_history(queued_history):
    """A deleted conversation must not be resurrected from its queued snapshot."""
    env = queued_history
    event = env.event("queued")
    event.set_extra("provider_request", ProviderRequest(conversation=env.stored))
    env.manager.get_conversation.side_effect = None
    env.manager.get_conversation.return_value = None

    result, _ = await collect_initial_request(event, env.context, env.config)

    assert result is None
    assert event.get_extra(LLM_ERROR_MESSAGE_EXTRA_KEY)
    env.manager.update_conversation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("direct", [False, True])
async def test_explicit_contexts_are_not_replaced(queued_history, direct):
    """Stateless plugin contexts and direct caller requests remain caller-owned."""
    env = queued_history
    event = env.event("custom")
    request = ProviderRequest(
        prompt="custom", contexts=[{"role": "user", "content": "custom context"}],
        conversation=copy.deepcopy(env.stored) if direct else None,
    )
    if not direct:
        event.set_extra("provider_request", request)

    result, _ = await collect_initial_request(
        event, env.context, env.config, req=request if direct else None,
    )

    assert result.contexts == request.contexts
    env.manager.get_conversation.assert_not_awaited()
