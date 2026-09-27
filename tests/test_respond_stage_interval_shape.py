"""A one-item segmented-reply ``interval`` must not drop the whole reply.

``platform_settings.segmented_reply.interval`` is a free-text string in the
dashboard (``astrbot/core/config/default.py`` declares it as
``{"type": "string"}`` and hints ``格式：最小值,最大值（如：1.5,3.5）``), so the
parse in ``RespondStage.initialize`` accepted whatever ``float()`` accepts and
stored the whole list.  ``_calc_comp_interval`` then reads ``self.interval[1]``:
measured on master, ``interval="3"`` gives ``stage.interval == [3.0]`` and the
next ``_calc_comp_interval(Plain(text=...))`` raises
``IndexError: list index out of range``.  The delay is computed *before* the
``try`` that wraps the send, so the exception escapes ``process()``, reaches
``EventDispatcher._on_task_done`` as ``Pipeline task failed.``, and no segment
is sent at all -- unlike an unparseable value such as ``"abc"``, which the
existing ``except`` already degrades to the documented default pair.

A non-finite bound fails one step later and even less visibly:
``random.uniform(nan, 3.5)`` returns ``nan``, and ``asyncio.sleep(nan)`` never
resumes on the supported Python 3.12 (measured: still pending after a 6 s
deadline while ``sleep(0.2)`` and ``sleep(3.5)`` both finish), so the pipeline
task hangs before the first send instead of raising.
"""

import math

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.pipeline.respond.stage import RespondStage

EXPECTED_INTERVAL = [1.5, 3.5]


class _Context:
    def __init__(self, interval: str) -> None:
        self.astrbot_config = {
            "platform_settings": {
                "reply_with_mention": {"enable": False, "key": ""},
                "reply_with_quote": {"enable": False, "key": ""},
                "segmented_reply": {
                    "enable": True,
                    "only_llm_result": True,
                    "interval_method": "random",
                    "interval": interval,
                    "log_base": 2.6,
                    "words_count_threshold": 150,
                },
            }
        }


async def _stage(interval: str) -> RespondStage:
    stage = RespondStage()
    await stage.initialize(_Context(interval))
    return stage


async def _delay(stage: RespondStage) -> float:
    return await stage._calc_comp_interval(Plain(text="hello world"))


@pytest.mark.asyncio
async def test_single_value_interval_keeps_the_default_pair():
    stage = await _stage("3")

    assert stage.interval == EXPECTED_INTERVAL
    delay = await _delay(stage)
    assert math.isfinite(delay) and delay >= 0


@pytest.mark.asyncio
async def test_extra_values_are_not_silently_truncated():
    stage = await _stage("3,4,5")

    assert stage.interval == EXPECTED_INTERVAL


@pytest.mark.asyncio
async def test_non_finite_bounds_keep_the_default_pair():
    for interval in ("nan,3.5", "inf,3.5", "0,inf"):
        stage = await _stage(interval)

        assert stage.interval == EXPECTED_INTERVAL
        delay = await _delay(stage)
        assert math.isfinite(delay) and delay >= 0


@pytest.mark.asyncio
async def test_valid_pair_is_honoured():
    stage = await _stage("5,7")

    assert stage.interval == [5.0, 7.0]
    delay = await _delay(stage)
    assert 5.0 <= delay <= 7.0


@pytest.mark.asyncio
async def test_unparseable_text_still_falls_back():
    stage = await _stage("abc")

    assert stage.interval == EXPECTED_INTERVAL
