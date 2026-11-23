"""Command argument conversion uses explicit boolean semantics."""

import pytest

from astrbot.core.star.filter.command import CommandFilter, GreedyStr
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata


def toggle_filter(declaration):
    async def toggle(self, event, enabled: bool):
        return enabled

    if declaration is not bool:
        toggle.__defaults__ = (declaration,)
    metadata = StarHandlerMetadata(
        EventType.AdapterMessageEvent, "test_toggle", "toggle", __name__, toggle, []
    )
    return CommandFilter("toggle", handler_md=metadata)


@pytest.mark.parametrize(
    "declaration",
    [bool, True, False],
    ids=["annotation", "true-default", "false-default"],
)
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("false", False),
        ("yes", True),
        ("no", False),
        ("1", True),
        ("0", False),
        ("TRUE", True),
        ("NO", False),
    ],
)
def test_boolean_arguments_cover_annotations_and_defaults(
    declaration, raw: str, expected: bool
) -> None:
    command = toggle_filter(declaration)
    assert command.handler_params == {"enabled": declaration}
    assert command.validate_and_convert_params([raw], command.handler_params) == {
        "enabled": expected
    }


@pytest.mark.parametrize("declaration", [bool, True, False])
@pytest.mark.parametrize("raw", ["maybe", "2", ""])
def test_invalid_boolean_is_rejected(declaration, raw: str) -> None:
    command = toggle_filter(declaration)
    with pytest.raises(ValueError):
        command.validate_and_convert_params([raw], command.handler_params)


def test_omitted_boolean_uses_its_default() -> None:
    command = toggle_filter(False)
    assert command.validate_and_convert_params([], command.handler_params) == {
        "enabled": False
    }


def test_greedy_argument_keeps_the_remainder_and_numeric_arguments() -> None:
    assert CommandFilter("say").validate_and_convert_params(
        ["3", "hello", "whole", "world"], {"count": int, "text": GreedyStr}
    ) == {"count": 3, "text": "hello whole world"}


def test_greedy_argument_must_be_last() -> None:
    with pytest.raises(ValueError):
        CommandFilter("say").validate_and_convert_params(
            ["hello"], {"text": GreedyStr, "count": int}
        )
