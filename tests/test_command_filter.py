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

    assert command_filter.handler_params == {"machine": str, "retries": int}
    assert command_filter.handler_param_defaults == {"retries": 1}
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


async def optional_str_handler(self, event, text: str = None) -> None:
    pass


async def optional_union_handler(self, event, text: str | None = None) -> None:
    pass


async def required_bool_handler(self, event, flag: bool) -> None:
    pass


async def defaulted_str_handler(self, event, text: str = "fallback") -> None:
    pass


async def untyped_handler(self, event, arg) -> None:
    pass


@pytest.mark.parametrize(
    "handler",
    [optional_str_handler, optional_union_handler],
)
def test_command_filter_keeps_digit_string_for_annotated_str(handler):
    """A digit string must stay str when the parameter is annotated as str."""
    command_filter = CommandFilter("echo", handler_md=SimpleNamespace(handler=handler))

    result = command_filter.validate_and_convert_params(
        ["123"],
        command_filter.handler_params,
    )

    assert result == {"text": "123"}
    assert isinstance(result["text"], str)


def test_command_filter_parses_annotation_only_bool():
    """Annotation-only bool must parse true/false instead of bool() truthiness."""
    command_filter = CommandFilter(
        "flag",
        handler_md=SimpleNamespace(handler=required_bool_handler),
    )

    assert command_filter.validate_and_convert_params(
        ["false"],
        command_filter.handler_params,
    ) == {"flag": False}


def test_command_filter_uses_default_when_param_missing():
    command_filter = CommandFilter(
        "echo",
        handler_md=SimpleNamespace(handler=defaulted_str_handler),
    )

    assert command_filter.validate_and_convert_params(
        [],
        command_filter.handler_params,
    ) == {"text": "fallback"}


def test_command_filter_keeps_untyped_digit_heuristic():
    """Untyped parameters keep the legacy digit-to-int heuristic."""
    command_filter = CommandFilter(
        "t",
        handler_md=SimpleNamespace(handler=untyped_handler),
    )

    assert command_filter.validate_and_convert_params(
        ["123"],
        command_filter.handler_params,
    ) == {"arg": 123}
