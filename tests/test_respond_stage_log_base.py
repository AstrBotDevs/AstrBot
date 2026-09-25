"""Segmented-reply log base must stay usable.

`platform_settings.segmented_reply.log_base` is a dashboard float field
(`astrbot/core/config/default.py:4551-4556`) whose advertised range is
"1.0-10.0" in every locale, and the previous value `2.6` is only the default.
`math.log(words, 1)` divides by `log(1)`, so the range's own lower bound raises
`ZeroDivisionError` inside `RespondStage._calc_comp_interval`, which
`process()` calls at `stage.py:277` - before the per-segment `try`. The reply
is then dropped without a single segment being sent.
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.respond import stage as respond_stage
from astrbot.core.pipeline.respond.stage import RespondStage

# The shipped default, astrbot/core/config/default.py:116.
DOCUMENTED_DEFAULT_LOG_BASE = 2.6


def _ctx(**segmented_reply: Any) -> SimpleNamespace:
    settings: dict[str, Any] = {
        "enable": True,
        "only_llm_result": False,
        "interval_method": "log",
        "interval": "1.5,3.5",
        "log_base": DOCUMENTED_DEFAULT_LOG_BASE,
    }
    settings.update(segmented_reply)
    return SimpleNamespace(
        astrbot_config={
            "platform_settings": {
                "reply_with_mention": False,
                "reply_with_quote": False,
                "segmented_reply": settings,
            },
            "provider_settings": {},
        },
    )


async def _stage(**segmented_reply: Any) -> RespondStage:
    stage = RespondStage()
    await stage.initialize(cast(Any, _ctx(**segmented_reply)))
    return stage


@pytest.mark.asyncio
@pytest.mark.parametrize("log_base", [1, 1.0, 0, 0.0, -2.0, float("nan")])
async def test_an_unusable_log_base_falls_back_to_the_default(
    log_base: float,
) -> None:
    """A base math.log rejects must not survive configuration parsing."""
    stage = await _stage(log_base=log_base)
    assert stage.log_base == DOCUMENTED_DEFAULT_LOG_BASE


@pytest.mark.asyncio
@pytest.mark.parametrize("log_base", [2.6, 1.5, 10.0])
async def test_a_usable_log_base_is_kept(log_base: float) -> None:
    stage = await _stage(log_base=log_base)
    assert stage.log_base == log_base


@pytest.mark.asyncio
@pytest.mark.parametrize("log_base", ["", None, "abc", "2,6"])
async def test_an_unparsable_log_base_keeps_the_default(
    log_base: Any,
) -> None:
    """A cleared or hand-mangled field must not break pipeline setup."""
    stage = await _stage(log_base=log_base)
    assert stage.log_base == DOCUMENTED_DEFAULT_LOG_BASE


@pytest.mark.asyncio
async def test_the_interval_calculation_survives_the_advertised_lower_bound() -> None:
    stage = await _stage(log_base=1.0)
    delay = await stage._calc_comp_interval(Comp.Plain(text="hello there"))
    assert delay >= 0


@pytest.mark.asyncio
async def test_segmented_reply_is_still_delivered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The boundary base used to lose the whole message chain."""
    stage = await _stage(log_base=1.0)
    sent: list[Any] = []

    async def _send(chain: Any) -> None:
        sent.append(chain)

    async def _no_sleep(_: float) -> None:
        return None

    async def _no_hook(_event: Any, _hook_type: Any) -> bool:
        return False

    monkeypatch.setattr(respond_stage.asyncio, "sleep", _no_sleep)
    # the star hook needs a registered plugin, which this test does not have
    monkeypatch.setattr(respond_stage, "call_event_hook", _no_hook)
    result = MessageEventResult(
        chain=[Comp.Plain(text="first part"), Comp.Plain(text="second part")],
    )
    event = SimpleNamespace(
        clear_result=lambda: None,
        get_result=lambda: result,
        get_platform_name=lambda: "aiocqhttp",
        get_platform_id=lambda: "aiocqhttp",
        get_sender_name=lambda: "tester",
        get_sender_id=lambda: "u-1",
        get_extra=lambda _key, default=None: default,
        set_extra=lambda _key, _value: None,
        _outline_chain=lambda chain: str(chain),
        send=_send,
    )

    await stage.process(cast(Any, event))

    assert len(sent) == 2
