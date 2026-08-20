from collections import deque
from pathlib import Path

from astrbot.api.message_components import (
    At,
    AtAll,
    Face,
    File,
    Forward,
    Image,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.builtin_stars.astrbot import group_chat_context as gcc


def test_describe_chain_covers_component_types():
    chain = [
        Plain(text="hello"),
        Image(file="https://example.com/a.png"),
        At(qq="1", name="bob"),
        Record(file="a.wav"),
        Video(file="a.mp4"),
        File(name="a.txt"),
        Forward(id="fwd"),
        AtAll(),
        Face(id=1),
        Reply(id="1"),
        object(),
    ]
    described = gcc._describe_chain(chain)
    assert "hello" in described
    assert "[Image]" in described
    assert "[Voice]" in described
    assert "[Video]" in described
    assert "[Forward]" in described
    assert gcc._describe_chain([]) == "[Unknown]"


def test_truncate_and_history_helpers(tmp_path: Path):
    assert gcc._truncate_reply_text("short") == "short"
    long_text = "x" * 250
    truncated = gcc._truncate_reply_text(long_text)
    assert truncated.endswith("...")
    assert len(truncated) == gcc._MAX_REPLY_TEXT_LENGTH + 3

    payload = tmp_path / "a.bin"
    payload.write_bytes(b"abc")
    digest = gcc._md5_file(payload)
    assert len(digest) == 32

    assert gcc._positive_int("3", 1) == 3
    assert gcc._positive_int("0", 7) == 7
    assert gcc._positive_int("nope", 7) == 7
    assert gcc._non_negative_float("1.5", 0.0) == 1.5
    assert gcc._non_negative_float(-1, 0.2) == 0.2
    assert gcc._non_negative_float(None, 0.2) == 0.2

    records = deque(["a", "b", "c", "d"])
    ids = deque(["1", "2", "3", "4"])
    gcc._trim_left(records, 2, ids)
    assert list(records) == ["c", "d"]
    assert list(ids) == ["3", "4"]

    block = gcc._format_group_history_block(["one", "two"])
    assert "one" in block
    assert "two" in block
