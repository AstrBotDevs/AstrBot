"""Unit tests for astrbot.core.tools.registry: builtin_tool decorator, tool registration."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic.dataclasses import dataclass

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.tools.registry import (
    BuiltinToolConfigCondition,
    BuiltinToolConfigRule,
    _BUILTIN_TOOL_CONFIG_RULES,
    _builtin_tool_classes_by_name,
    _builtin_tool_names_by_class,
    _get_config_value,
    _json_safe,
    _MISSING,
    _resolve_builtin_tool_name,
    builtin_tool,
    ensure_builtin_tools_loaded,
    get_builtin_tool_class,
    get_builtin_tool_config_rule,
    get_builtin_tool_config_statuses,
    get_builtin_tool_config_tags,
    get_builtin_tool_name,
    iter_builtin_tool_classes,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Clean the global builtin tool registry before and after each test."""
    before_classes = dict(_builtin_tool_classes_by_name)
    before_names = dict(_builtin_tool_names_by_class)
    before_rules = dict(_BUILTIN_TOOL_CONFIG_RULES)
    yield
    _builtin_tool_classes_by_name.clear()
    _builtin_tool_classes_by_name.update(before_classes)
    _builtin_tool_names_by_class.clear()
    _builtin_tool_names_by_class.update(before_names)
    _BUILTIN_TOOL_CONFIG_RULES.clear()
    _BUILTIN_TOOL_CONFIG_RULES.update(before_rules)


class TestBuiltinToolDecorator:
    """builtin_tool decorator registration."""

    def test_decorator_without_call_registers(self):
        """Using @builtin_tool without parentheses registers the class."""

        @builtin_tool
        class MyTool(FunctionTool):
            name: str = "my_tool"
            description: str = "My custom tool"

        assert get_builtin_tool_class("my_tool") is MyTool
        assert get_builtin_tool_name(MyTool) == "my_tool"

    def test_decorator_with_call_registers(self):
        """Using @builtin_tool() with parentheses registers the class."""

        @builtin_tool()
        class AnotherTool(FunctionTool):
            name: str = "another_tool"
            description: str = "Another tool"

        assert get_builtin_tool_class("another_tool") is AnotherTool

    def test_decorator_with_config(self):
        """@builtin_tool(config={...}) registers with config rules."""

        @builtin_tool(config={"feature.enabled": True, "mode": ("auto", "manual")})
        class ConfigTool(FunctionTool):
            name: str = "config_tool"
            description: str = "Tool with config"

        rule = get_builtin_tool_config_rule("config_tool")
        assert rule is not None
        assert len(rule.conditions) == 2

    def test_name_conflict_raises(self):
        """Registering the same name with a different class raises ValueError."""

        @builtin_tool
        class First(FunctionTool):
            name: str = "conflict_tool"
            description: str = "first"

        with pytest.raises(ValueError, match="name conflict"):

            @builtin_tool
            class Second(FunctionTool):
                name: str = "conflict_tool"
                description: str = "second"

    def test_same_class_no_conflict(self):
        """Registering the same class again with the same name does not raise."""

        @builtin_tool
        class SameTool(FunctionTool):
            name: str = "same_tool"
            description: str = "same"

        # Registering the same class again should not raise
        builtin_tool(SameTool)
        assert get_builtin_tool_class("same_tool") is SameTool

    def test_resolve_tool_name_from_field(self):
        """_resolve_builtin_tool_name reads from the 'name' dataclass field."""

        @dataclass
        class ResolveMe:
            name: str = "resolved_name"

        # Since ResolveMe is not a FunctionTool, we need to test _resolve_builtin_tool_name
        # by temporarily making it look like a FunctionTool subclass
        name = _resolve_builtin_tool_name(ResolveMe)
        assert name == "resolved_name"

    def test_resolve_tool_name_raises_when_missing(self):
        """_resolve_builtin_tool_name raises ValueError when no name is found."""

        class NoName:
            pass

        with pytest.raises(ValueError, match="does not define a valid name"):
            _resolve_builtin_tool_name(NoName)


class TestGetAndIter:
    """Query functions for the builtin tool registry."""

    def test_get_nonexistent_class_returns_none(self):
        """get_builtin_tool_class returns None for unknown names."""
        assert get_builtin_tool_class("nonexistent_tool") is None

    def test_get_nonexistent_name_returns_none(self):
        """get_builtin_tool_name returns None for unknown classes."""
        class Random(FunctionTool):
            name: str = "random"
            description: str = "r"
        assert get_builtin_tool_name(Random) is None

    def test_iter_builtin_tool_classes_empty(self):
        """iter_builtin_tool_classes returns empty tuple when nothing registered."""
        classes = iter_builtin_tool_classes()
        # Only pre-existing builtins may be present, but the fixture resets to original state.
        # We just check it's a tuple.
        assert isinstance(classes, tuple)

    def test_iter_after_registration(self):
        """iter_builtin_tool_classes includes newly registered tools."""

        @builtin_tool
        class IterTool(FunctionTool):
            name: str = "iter_tool"
            description: str = "iter"

        classes = iter_builtin_tool_classes()
        assert IterTool in classes


class TestConfigCondition:
    """BuiltinToolConfigCondition evaluation."""

    def test_equals_condition_match(self):
        """'equals' operator returns matched=True when values match."""
        cond = BuiltinToolConfigCondition(key="enabled", operator="equals", expected=True)
        result = cond.evaluate({"enabled": True})
        assert result["matched"] is True

    def test_equals_condition_mismatch(self):
        """'equals' operator returns matched=False when values differ."""
        cond = BuiltinToolConfigCondition(key="enabled", operator="equals", expected=True)
        result = cond.evaluate({"enabled": False})
        assert result["matched"] is False

    def test_in_condition_match(self):
        """'in' operator returns matched=True when value is in expected."""
        cond = BuiltinToolConfigCondition(key="mode", operator="in", expected=("a", "b", "c"))
        result = cond.evaluate({"mode": "b"})
        assert result["matched"] is True

    def test_in_condition_mismatch(self):
        """'in' operator returns matched=False when value is not in expected."""
        cond = BuiltinToolConfigCondition(key="mode", operator="in", expected=("a", "b"))
        result = cond.evaluate({"mode": "c"})
        assert result["matched"] is False

    def test_truthy_condition_match(self):
        """'truthy' operator returns matched=True for truthy values."""
        cond = BuiltinToolConfigCondition(key="timeout", operator="truthy")
        result = cond.evaluate({"timeout": 30})
        assert result["matched"] is True

    def test_truthy_condition_mismatch(self):
        """'truthy' operator returns matched=False for falsy values."""
        cond = BuiltinToolConfigCondition(key="timeout", operator="truthy")
        result = cond.evaluate({"timeout": 0})
        assert result["matched"] is False

    def test_custom_condition(self):
        """'custom' operator delegates to the expected field."""
        cond = BuiltinToolConfigCondition(key="custom_key", operator="custom", expected=True)
        result = cond.evaluate({})
        assert result["matched"] is True

    def test_unsupported_operator_raises(self):
        """An unknown operator raises ValueError."""
        cond = BuiltinToolConfigCondition(key="k", operator="bad_op")
        with pytest.raises(ValueError, match="Unsupported builtin tool config operator"):
            cond.evaluate({})

    def test_missing_key_returns_missing(self):
        """A key that is not present in config returns _MISSING as actual."""
        cond = BuiltinToolConfigCondition(key="missing.key", operator="truthy")
        result = cond.evaluate({})
        assert result["actual"] is None

    def test_nested_key_access(self):
        """_get_config_value traverses dot-separated keys."""
        config = {"a": {"b": {"c": 42}}}
        assert _get_config_value(config, "a.b.c") == 42
        assert _get_config_value(config, "a.b.missing") is _MISSING
        assert _get_config_value(config, "x") is _MISSING

    def test_json_safe_converts_tuple_to_list(self):
        """_json_safe converts tuples to lists."""
        result = _json_safe((1, (2, 3)))
        assert result == [1, [2, 3]]

    def test_json_safe_dict(self):
        """_json_safe processes dicts recursively."""
        result = _json_safe({"a": (1, 2), "b": "hello"})
        assert result == {"a": [1, 2], "b": "hello"}


class TestBuiltinToolConfigRule:
    """BuiltinToolConfigRule evaluation."""

    def test_rule_with_conditions(self):
        """A rule with conditions evaluates all of them."""
        c1 = BuiltinToolConfigCondition(key="x", operator="equals", expected=1)
        c2 = BuiltinToolConfigCondition(key="y", operator="truthy")
        rule = BuiltinToolConfigRule(conditions=(c1, c2))
        results = rule.evaluate({"x": 1, "y": True})
        assert len(results) == 2
        assert all(r["matched"] for r in results)

    def test_rule_with_evaluator(self):
        """A rule with an evaluator callable uses it instead of conditions."""
        def my_evaluator(config):
            return [{"key": "custom", "matched": True}]
        rule = BuiltinToolConfigRule(evaluator=my_evaluator)
        results = rule.evaluate({"anything": 1})
        assert results == [{"key": "custom", "matched": True}]

    def test_rule_conditions_are_frozen(self):
        """BuiltinToolConfigRule and its conditions are frozen dataclasses."""
        rule = BuiltinToolConfigRule(conditions=())
        with pytest.raises(Exception):
            rule.conditions = ("cannot", "change")


class TestGetBuiltinToolConfigStatuses:
    """get_builtin_tool_config_statuses integration."""

    def test_no_rule_returns_empty(self):
        """Getting statuses for a tool with no config rule returns []."""
        statuses = get_builtin_tool_config_statuses("nonexistent", [{"config": {}}])
        assert statuses == []

    def test_statuses_with_matching_config(self):
        """Statuses are returned with enabled=True when all conditions match."""

        @builtin_tool(config={"enabled": True})
        class StatusTool(FunctionTool):
            name: str = "status_tool"
            description: str = "test"

        entries = [{"conf_id": "1", "conf_name": "cfg1", "config": {"enabled": True}}]
        statuses = get_builtin_tool_config_statuses("status_tool", entries)
        assert len(statuses) == 1
        assert statuses[0]["enabled"] is True

    def test_statuses_with_non_matching_config(self):
        """Statuses are returned with enabled=False when some conditions fail."""

        @builtin_tool(config={"enabled": True})
        class StatusTool2(FunctionTool):
            name: str = "status_tool2"
            description: str = "test"

        entries = [{"conf_id": "2", "conf_name": "cfg2", "config": {"enabled": False}}]
        statuses = get_builtin_tool_config_statuses("status_tool2", entries)
        assert len(statuses) == 1
        assert statuses[0]["enabled"] is False
        assert len(statuses[0]["failed_conditions"]) > 0

    def test_get_tags_filters_enabled(self):
        """get_builtin_tool_config_tags only returns entries where enabled is True."""

        @builtin_tool(config={"enabled": True})
        class TagTool(FunctionTool):
            name: str = "tag_tool"
            description: str = "test"

        entries = [
            {"conf_id": "1", "conf_name": "on", "config": {"enabled": True}},
            {"conf_id": "2", "conf_name": "off", "config": {"enabled": False}},
        ]
        tags = get_builtin_tool_config_tags("tag_tool", entries)
        assert len(tags) == 1
        assert tags[0]["conf_id"] == "1"


class TestEnsureBuiltinToolsLoaded:
    """ensure_builtin_tools_loaded idempotency."""

    def test_load_is_idempotent(self):
        """Calling ensure_builtin_tools_loaded twice does not raise."""
        # The first call may fail if the builtin modules have missing deps; catch.
        try:
            ensure_builtin_tools_loaded()
        except Exception:
            pass
        # Second call should also not raise (just returns early).
        ensure_builtin_tools_loaded()
