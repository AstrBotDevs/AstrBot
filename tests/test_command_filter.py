from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrbot.core.star.filter.command import CommandFilter


async def postponed_annotations_handler(
    self,
    event,
    machine: str,
    retries: int = 1,
) -> None:
    pass


def test_command_filter_resolves_postponed_annotations():
    command_filter = CommandFilter(
        "probe",
        handler_md=SimpleNamespace(handler=postponed_annotations_handler),
    )

    assert command_filter.handler_params == {"machine": str, "retries": 1}
    assert command_filter.validate_and_convert_params(
        ["server-1", "2"],
        command_filter.handler_params,
    ) == {"machine": "server-1", "retries": 2}


def test_command_filter_rejects_missing_postponed_required_param():
    command_filter = CommandFilter(
        "probe",
        handler_md=SimpleNamespace(handler=postponed_annotations_handler),
    )

    with pytest.raises(ValueError, match="必要参数缺失"):
        command_filter.validate_and_convert_params([], command_filter.handler_params)


async def single_arg_handler(self, event, arg: str) -> None:
    pass


def _make_event(message_str: str) -> SimpleNamespace:
    event = SimpleNamespace(
        is_at_or_wake_command=True,
        extras={},
        get_message_str=lambda: message_str,
        set_extra=lambda key, value: event.extras.__setitem__(key, value),
    )
    return event


def test_command_alias_does_not_consume_argument_matching_alias():
    """An argument equal to (or starting with) the command's own alias must be
    passed through to the handler instead of being stripped as a command name."""
    command_filter = CommandFilter(
        "hello",
        alias={"h"},
        handler_md=SimpleNamespace(handler=single_arg_handler),
    )
    event = _make_event("hello h")

    assert command_filter.filter(event, {}) is True
    assert event.extras["parsed_params"] == {"arg": "h"}


def test_command_alias_does_not_consume_first_argument_of_many():
    """The alias must not shift arguments when more than one is provided."""
    command_filter = CommandFilter(
        "hello",
        alias={"h"},
        handler_md=SimpleNamespace(handler=single_arg_handler),
    )
    event = _make_event("hello h extra")

    assert command_filter.filter(event, {}) is True
    assert event.extras["parsed_params"] == {"arg": "h"}


def test_invoking_via_alias_still_passes_arguments():
    """Invoking the command through its alias must keep passing arguments."""
    command_filter = CommandFilter(
        "hello",
        alias={"h"},
        handler_md=SimpleNamespace(handler=single_arg_handler),
    )
    event = _make_event("h hello")

    assert command_filter.filter(event, {}) is True
    assert event.extras["parsed_params"] == {"arg": "hello"}


def test_longest_command_name_wins_over_prefixing_shorter_name():
    """A longer alias containing spaces must win over the shorter main name."""
    command_filter = CommandFilter(
        "hello",
        alias={"hello world"},
        handler_md=SimpleNamespace(handler=single_arg_handler),
    )
    event = _make_event("hello world x")

    assert command_filter.filter(event, {}) is True
    assert event.extras["parsed_params"] == {"arg": "x"}
