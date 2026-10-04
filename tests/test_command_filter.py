from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter


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


def _group(name: str, alias: set | None = None, parent=None):
    return CommandGroupFilter(name, alias=alias, parent_group=parent)


def test_command_group_matches_name_followed_by_sub_command():
    group = _group("math")

    assert group.startswith("math add 1 2")
    assert group.startswith("math")


def test_command_group_does_not_claim_a_longer_prefixed_word():
    group = _group("math")

    # The whole point of #10371: "math" must not swallow "mathematics",
    # otherwise an admin-gated group intercepts another plugin's public
    # command (or plain chat like "天气真好啊") before it can run.
    assert not group.startswith("mathematics")
    assert not group.startswith("math123")


def test_command_group_boundary_covers_cjk_plain_chat():
    group = _group("天气")

    assert not group.startswith("天气真好啊")
    assert group.startswith("天气 设置 上海")


def test_command_group_boundary_matches_command_filter_whitespace():
    group = _group("math")

    # CommandFilter normalizes any whitespace run to a single space before
    # parsing, so the group gate has to accept the same characters or a
    # tab-separated call would pass the leaf but never reach it.
    assert group.startswith("math\tadd 1 2")
    assert group.startswith("math\u3000add")


def test_command_group_alias_and_nested_names_keep_the_boundary():
    group = _group("math", alias={"m"})
    assert group.startswith("m add 1 2")
    assert not group.startswith("mine")

    nested = _group("calc", parent=_group("admin"))
    assert nested.startswith("admin calc add")
    assert not nested.startswith("admin calculus")
