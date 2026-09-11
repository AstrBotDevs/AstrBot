"""Regression tests for segmented reply bubble grouping (#10047).

With segmented reply enabled, every component used to be sent as its own
message, so an inline Face in the middle of a sentence split the text into
several bubbles. The stage now groups consecutive inline components
(Plain / Face) so a sentence stays in one bubble.
"""

import math

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.pipeline.respond.stage import RespondStage


def test_inline_face_stays_in_the_same_bubble_as_text():
    stage = RespondStage()
    chain = [
        Comp.Plain(text="好的"),
        Comp.Face(id=277),
        Comp.Plain(text="，我知道了！"),
    ]

    segments = stage._group_segment_chain(chain)

    assert len(segments) == 1
    assert segments[0] == chain


def test_components_that_need_separate_sending_stay_alone():
    stage = RespondStage()
    record = Comp.Record(file="file:///tmp/a.wav")
    chain = [Comp.Plain(text="看这个"), record, Comp.Plain(text="好听吗")]

    segments = stage._group_segment_chain(chain)

    assert segments == [[chain[0]], [record], [chain[2]]]


@pytest.mark.asyncio
async def test_log_interval_for_a_bubble_uses_total_plain_word_count():
    stage = RespondStage()
    stage.interval_method = "log"
    stage.log_base = 10.0

    # "hello" + "world" -> 2 words -> log10(3) ~= 0.477
    bubble = await stage._calc_comp_interval(
        [Comp.Plain(text="hello"), Comp.Face(id=277), Comp.Plain(text="world")],
    )
    lower, upper = math.log(3, 10), math.log(3, 10) + 0.5
    assert lower <= bubble <= upper

    # A bubble without text keeps the non-Plain interval.
    face_only = await stage._calc_comp_interval(Comp.Face(id=277))
    assert 1 <= face_only <= 1.75
