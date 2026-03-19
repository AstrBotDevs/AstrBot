from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from astrbot_sdk.protocol.descriptors import ParamSpec
from astrbot_sdk.runtime._command_matching import (
    build_command_args,
    build_regex_args,
    match_command_name,
    split_command_remainder,
)


def test_match_command_name_trims_input_consistently() -> None:
    assert match_command_name("  ping  ", "ping") == ""
    assert match_command_name("  ping   hello world  ", "ping") == "hello world"
    assert match_command_name("pingpong", "ping") is None


def test_build_command_args_supports_quotes_and_greedy_tail() -> None:
    param_specs = [
        ParamSpec(name="name", type="str"),
        ParamSpec(name="message", type="greedy_str"),
    ]

    args = build_command_args(param_specs, '"alpha beta" "hello world" tail')

    assert args == {"name": "alpha beta", "message": "hello world tail"}


def test_split_command_remainder_falls_back_on_invalid_quotes() -> None:
    assert split_command_remainder('"unterminated quote test') == [
        '"unterminated',
        "quote",
        "test",
    ]


def test_build_regex_args_preserves_named_and_positional_mapping() -> None:
    param_specs = [
        ParamSpec(name="first", type="str"),
        ParamSpec(name="second", type="str"),
        ParamSpec(name="third", type="str"),
    ]
    match = re.search(r"(?P<second>\w+)-(\w+)-(\w+)", "named-positional-tail")

    assert match is not None
    assert build_regex_args(param_specs, match) == {
        "second": "named",
        "first": "named",
        "third": "positional",
    }
