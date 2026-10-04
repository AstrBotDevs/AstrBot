"""Regression tests for segmented reply bubble grouping (#10047).

With segmented reply enabled, every component used to be sent as its own
message, so an inline Face in the middle of a sentence split the text into
several bubbles. The stage now treats an inline Face as glue: it attaches to
the preceding text bubble and keeps the following Plain in the same bubble,
while adjacent Plain components from the segmentation-words feature (#3959)
keep their deliberate split.
"""

import math

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.pipeline.respond.stage import RespondStage


def test_inline_face_glues_the_whole_sentence_into_one_bubble():
    stage = RespondStage()
    chain = [
        Comp.Plain(text="好的"),
        Comp.Face(id=277),
        Comp.Plain(text="，我知道了！"),
    ]

    segments = stage._group_segment_chain(chain)

    assert segments == [chain]


def test_leading_face_joins_the_following_text_bubble():
    stage = RespondStage()
    face = Comp.Face(id=277)
    chain = [face, Comp.Plain(text="你好呀")]

    segments = stage._group_segment_chain(chain)

    assert segments == [[face, chain[1]]]


def test_adjacent_plain_components_keep_separate_bubbles():
    stage = RespondStage()
    first = Comp.Plain(text="第一段。")
    second = Comp.Plain(text="第二段。")

    segments = stage._group_segment_chain([first, second])

    assert segments == [[first], [second]]


def test_components_that_need_separate_sending_stay_alone():
    stage = RespondStage()
    record = Comp.Record(file="file:///tmp/a.wav")
    chain = [Comp.Plain(text="看这个"), record, Comp.Plain(text="好听吗")]

    segments = stage._group_segment_chain(chain)

    assert segments == [[chain[0]], [record], [chain[2]]]


def test_face_after_media_stays_its_own_bubble():
    stage = RespondStage()
    record = Comp.Record(file="file:///tmp/a.wav")
    face = Comp.Face(id=277)
    chain = [Comp.Plain(text="听"), record, face]

    segments = stage._group_segment_chain(chain)

    assert segments == [[chain[0]], [record], [face]]


def test_face_glue_does_not_absorb_media():
    stage = RespondStage()
    record = Comp.Record(file="file:///tmp/a.wav")
    chain = [Comp.Plain(text="好的"), Comp.Face(id=277), record]

    segments = stage._group_segment_chain(chain)

    assert segments == [[chain[0], chain[1]], [record]]


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
