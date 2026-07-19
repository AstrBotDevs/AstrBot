from types import SimpleNamespace

import pytest

from data.plugins.astrbot_plugin_wakepro.core.model import (
    MemberState,
    StepName,
    StepResult,
    WakeContext,
)
from data.plugins.astrbot_plugin_wakepro.core.pipeline import Pipeline
from data.plugins.astrbot_plugin_wakepro.core.step.wake import WakeStep


@pytest.mark.asyncio
async def test_noop_mention_does_not_erase_active_followup_window() -> None:
    class NoopMention:
        name = StepName.MENTION

        async def handle(self, ctx: WakeContext) -> StepResult:
            return StepResult()

    class FollowupWake:
        name = StepName.WAKE

        async def handle(self, ctx: WakeContext) -> StepResult:
            return StepResult(
                wake=ctx.member.can_prolong if ctx.member else False,
                prolong=True,
            )

    enabled = SimpleNamespace(
        is_enabled_step=lambda name: True,
        in_whitelist=lambda name, *values: False,
        in_blacklist=lambda name, *values: False,
    )
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.plugin_config = SimpleNamespace(pipeline=enabled)
    pipeline._steps = [NoopMention(), FollowupWake()]
    pipeline._debounce_step = None
    event = SimpleNamespace(is_at_or_wake_command=False, stop_event=lambda: None)
    member = MemberState(uid="user", can_prolong=True, last_reply=100.0)
    ctx = WakeContext(
        event=event,
        chain=[],
        plain="继续说",
        cmd=None,
        is_admin=False,
        umo="qq:group:user",
        gid="group",
        uid="user",
        bid="bot",
        group=None,
        member=member,
        now=120.0,
    )

    await pipeline.run(ctx)

    assert event.is_at_or_wake_command is True
    assert member.can_prolong is True


@pytest.mark.asyncio
async def test_recent_bot_reply_wakes_same_user_without_mention() -> None:
    step = WakeStep.__new__(WakeStep)
    step.cfg = SimpleNamespace(
        prolong=60.0,
        similar=1.0,
        ask=1.0,
        bored=1.0,
        interest=1.0,
        prob=0.0,
    )
    member = MemberState(uid="user", can_prolong=True, last_reply=100.0)
    ctx = SimpleNamespace(
        debounce_follow_up=False,
        group=None,
        member=member,
        now=145.0,
        cmd=None,
        plain="好啊，继续",
    )

    result = await step.handle(ctx)

    assert result.wake is True
    assert result.prolong is True
    assert result.msg == "唤醒延长"
