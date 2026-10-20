"""Tests for the cascade of command-group custom filters to sub-commands."""

from typing import Any

import pytest


class FakeEvent:
    """Minimal AstrMessageEvent stand-in for filter unit tests."""

    def __init__(self, message_str: str) -> None:
        self.message_str = message_str
        self.is_at_or_wake_command = True
        self._extras: dict[str, Any] = {}

    def get_message_str(self) -> str:
        return self.message_str

    def get_extra(self, key: str | None = None, default: Any = None) -> Any:
        if key is None:
            return default
        return self._extras.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value


def make_custom_filter(allowed: bool, calls: list[int] | None = None):
    """Build a CustomFilter that returns ``allowed`` and counts invocations."""
    from astrbot.core.star.filter.custom_filter import CustomFilter

    class _Filter(CustomFilter):
        def filter(self, event, cfg) -> bool:
            if calls is not None:
                calls.append(1)
            return allowed

    return _Filter()


def make_group(name: str, parent_group=None):
    from astrbot.core.star.filter.command_group import CommandGroupFilter

    return CommandGroupFilter(name, parent_group=parent_group)


def make_sub_command(name: str, group):
    from astrbot.core.star.filter.command import CommandFilter

    sub_command = CommandFilter(
        name,
        parent_command_names=group.get_complete_command_names(),
        parent_group=group,
    )
    # Normally filled by init_handler_md() while decorating the handler.
    sub_command.handler_params = {}
    return sub_command


def test_group_filter_blocks_sub_command():
    group = make_group("math")
    group.add_custom_filter(make_custom_filter(False))
    sub_command = make_sub_command("add", group)

    assert sub_command.filter(FakeEvent("math add"), {}) is False


def test_group_filter_allows_sub_command():
    group = make_group("math")
    group.add_custom_filter(make_custom_filter(True))
    sub_command = make_sub_command("add", group)

    assert sub_command.filter(FakeEvent("math add"), {}) is True


def test_nested_group_filter_blocks_sub_command():
    outer = make_group("math")
    outer.add_custom_filter(make_custom_filter(False))
    inner = make_group("calc", parent_group=outer)
    inner.add_custom_filter(make_custom_filter(True))
    sub_command = make_sub_command("add", inner)

    assert sub_command.filter(FakeEvent("math calc add"), {}) is False


def test_sub_command_filter_still_applies():
    group = make_group("math")
    group.add_custom_filter(make_custom_filter(True))
    sub_command = make_sub_command("add", group)
    sub_command.add_custom_filter(make_custom_filter(False))

    assert sub_command.filter(FakeEvent("math add"), {}) is False


def test_group_filter_is_evaluated_once_per_message():
    calls: list[int] = []
    group = make_group("math")
    group.add_custom_filter(make_custom_filter(True, calls))
    sub_command = make_sub_command("add", group)
    event = FakeEvent("math add")

    assert group.filter(event, {}) is True
    assert sub_command.filter(event, {}) is True
    assert len(calls) == 1


def test_group_filter_not_checked_for_unrelated_message():
    calls: list[int] = []
    group = make_group("math")
    group.add_custom_filter(make_custom_filter(False, calls))
    sub_command = make_sub_command("add", group)

    assert sub_command.filter(FakeEvent("other add"), {}) is False
    assert calls == []


def test_group_handler_skips_filters_for_unrelated_message():
    calls: list[int] = []
    group = make_group("math")
    group.add_custom_filter(make_custom_filter(True, calls))

    assert group.filter(FakeEvent("weather info"), {}) is False
    assert calls == []


def test_group_handler_shows_help_for_exact_group_name():
    group = make_group("math")
    group.add_custom_filter(make_custom_filter(True))

    with pytest.raises(ValueError, match="参数不足"):
        group.filter(FakeEvent("math"), {})


def test_group_handler_hides_help_when_filter_denies():
    group = make_group("math")
    group.add_custom_filter(make_custom_filter(False))

    assert group.filter(FakeEvent("math"), {}) is False


def test_register_command_attaches_parent_group():
    from astrbot.core.star.filter.command_group import CommandGroupFilter
    from astrbot.core.star.register.star_handler import (
        RegisteringCommandable,
        register_command,
    )
    from astrbot.core.star.star_handler import star_handlers_registry

    group = CommandGroupFilter("_scope_test_math")

    async def handler(event):
        pass

    md = None
    try:
        register_command(RegisteringCommandable(group), "_scope_test_add")(handler)
        md = star_handlers_registry.get_handler_by_full_name(
            f"{handler.__module__}_{handler.__name__}"
        )
        assert md is not None
        assert md.event_filters[0].parent_group is group
    finally:
        if md is not None:
            star_handlers_registry.remove(md)
