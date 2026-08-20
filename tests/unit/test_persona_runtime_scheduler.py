import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.db.po import PersonaSessionState
from astrbot.core.persona_runtime import PersonaRuntimeManager, ProactiveScheduler
from astrbot.core.persona_runtime.injector import PersonaRuntimeInjector


def _state(**overrides) -> PersonaSessionState:
    now = datetime.now(UTC)
    values = {
        "persona_id": "persona-a",
        "umo": "webchat:FriendMessage:u1",
        "agent_state": "running",
        "talk_frequency_adjust": 1.0,
        "consecutive_idle_count": 0,
        "cooldown_until": None,
        "last_interaction_at": now,
        "extra_state": {"proactive_enabled": True},
    }
    values.update(overrides)
    return PersonaSessionState(**values)


def test_proactive_scheduler_respects_cooldown_and_unread_threshold():
    scheduler = ProactiveScheduler()
    now = datetime.now(UTC)
    cooling = _state(cooldown_until=now + timedelta(minutes=5))
    assert scheduler.evaluate(cooling, now=now).reason == "cooldown"

    ready = _state(cooldown_until=None)
    assert scheduler.evaluate(ready, unread_count=3, now=now).should_enqueue is True
    assert scheduler.evaluate(ready, unread_count=1, now=now).should_enqueue is False


def test_injector_adds_transient_runtime_context():
    req = ProviderRequest(prompt="hi")
    PersonaRuntimeInjector().inject(req, _state())
    assert req.extra_user_content_parts
    assert req.extra_user_content_parts[0].is_temp is True
    assert "persona_runtime_context" in req.extra_user_content_parts[0].text


@pytest.mark.asyncio
async def test_process_turn_reraises_cancelled_error(temp_db):
    manager = PersonaRuntimeManager(temp_db)
    await temp_db.initialize()

    async def boom(**_kwargs):
        raise asyncio.CancelledError

    manager.jargon_learner.learn = boom  # type: ignore[method-assign]
    event = SimpleNamespace(
        unified_msg_origin="webchat:FriendMessage:cancel",
        message_str="hello `term` `term`",
        message_obj=SimpleNamespace(sender=SimpleNamespace(user_id="u1")),
    )

    with pytest.raises(asyncio.CancelledError):
        await manager.process_turn(
            event=event,
            persona_id="persona-a",
            conversation_id="cid-1",
            assistant_text="ack",
        )
