# ruff: noqa: E402
"""Extended unit tests for sdk_bridge modules.

This module covers additional test cases for:
- trigger_converter.py: regex triggers, filter specs, parameter handling
- event_payload.py: sanitization edge cases
- bridge_base.py: serialization helpers and message chain building
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    CompositeFilterSpec,
    HandlerDescriptor,
    LocalFilterRefSpec,
    MessageTrigger,
    MessageTypeFilterSpec,
    ParamSpec,
    Permissions,
    PlatformFilterSpec,
)

from astrbot.core.sdk_bridge.event_payload import (
    extract_sdk_handler_result,
    sanitize_sdk_extra_value,
    sanitize_sdk_extras,
)

# Load trigger_converter module directly
_TRIGGER_CONVERTER_SPEC = importlib.util.spec_from_file_location(
    "astrbot_sdk_bridge_trigger_converter_extended_test",
    str(
        Path(__file__).resolve().parents[3]
        / "astrbot"
        / "core"
        / "sdk_bridge"
        / "trigger_converter.py"
    ),
)
assert _TRIGGER_CONVERTER_SPEC is not None
assert _TRIGGER_CONVERTER_SPEC.loader is not None
_TRIGGER_CONVERTER_MODULE = importlib.util.module_from_spec(_TRIGGER_CONVERTER_SPEC)
sys.modules.setdefault(
    "astrbot_sdk_bridge_trigger_converter_extended_test",
    _TRIGGER_CONVERTER_MODULE,
)
_TRIGGER_CONVERTER_SPEC.loader.exec_module(_TRIGGER_CONVERTER_MODULE)
TriggerConverter = _TRIGGER_CONVERTER_MODULE.TriggerConverter
TriggerMatch = _TRIGGER_CONVERTER_MODULE.TriggerMatch


# Load bridge_base module directly
_BRIDGE_BASE_SPEC = importlib.util.spec_from_file_location(
    "astrbot_sdk_bridge_base_extended_test",
    str(
        Path(__file__).resolve().parents[3]
        / "astrbot"
        / "core"
        / "sdk_bridge"
        / "bridge_base.py"
    ),
)
assert _BRIDGE_BASE_SPEC is not None
assert _BRIDGE_BASE_SPEC.loader is not None
_BRIDGE_BASE_MODULE = importlib.util.module_from_spec(_BRIDGE_BASE_SPEC)
sys.modules.setdefault(
    "astrbot_sdk_bridge_base_extended_test",
    _BRIDGE_BASE_MODULE,
)
_BRIDGE_BASE_SPEC.loader.exec_module(_BRIDGE_BASE_MODULE)
_build_message_chain_from_payload = (
    _BRIDGE_BASE_MODULE._build_message_chain_from_payload
)
CapabilityBridgeBase = _BRIDGE_BASE_MODULE.CapabilityBridgeBase


class _FakeEvent:
    """Minimal fake event for trigger converter tests."""

    def __init__(
        self,
        *,
        text: str,
        platform: str = "test",
        message_type: str = "private",
        admin: bool = False,
        group_id: str | None = None,
        sender_id: str | None = "user-1",
    ) -> None:
        self._text = text
        self._platform = platform
        self._message_type = message_type
        self._admin = admin
        self._group_id = (
            "group-1" if group_id is None and message_type == "group" else group_id
        ) or ""
        self._sender_id = "" if sender_id is None else sender_id

    def get_message_type(self):
        return SimpleNamespace(value=self._message_type)

    def get_group_id(self) -> str:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_platform_name(self) -> str:
        return self._platform

    def get_message_str(self) -> str:
        return self._text

    def is_admin(self) -> bool:
        return self._admin


# ============================================================================
# TriggerConverter: Command Matching Tests
# ============================================================================


@pytest.mark.unit
class TestTriggerConverterCommandMatching:
    """Tests for TriggerConverter command matching behavior."""

    def test_match_command_name_exact_match(self) -> None:
        """Exact command match with no remainder."""
        result = TriggerConverter._match_command_name("ping", "ping")
        assert result == ""

    def test_match_command_name_with_remainder(self) -> None:
        """Command match with trailing arguments."""
        result = TriggerConverter._match_command_name("ping hello world", "ping")
        assert result == "hello world"

    def test_match_command_name_no_match_different_command(self) -> None:
        """No match when text starts with different command."""
        result = TriggerConverter._match_command_name("pong hello", "ping")
        assert result is None

    def test_match_command_name_no_match_partial_prefix(self) -> None:
        """No match when command is only partial prefix."""
        result = TriggerConverter._match_command_name("pinging", "ping")
        assert result is None

    def test_match_command_name_with_leading_spaces(self) -> None:
        """Command matching ignores leading spaces."""
        result = TriggerConverter._match_command_name("   ping hello", "ping")
        assert result == "hello"

    def test_match_command_name_empty_text(self) -> None:
        """Empty text never matches."""
        result = TriggerConverter._match_command_name("", "ping")
        assert result is None

    def test_match_command_name_accepts_leading_slash(self) -> None:
        """Leading slash is treated as transport syntax, not part of the command."""
        result = TriggerConverter._match_command_name("/ping hello world", "ping")
        assert result == "hello world"

    def test_match_command_name_accepts_space_after_slash(self) -> None:
        """Slash-prefixed commands may include spaces before the command body."""
        result = TriggerConverter._match_command_name("/ ping hello", "ping")
        assert result == "hello"


# ============================================================================
# TriggerConverter: Regex Trigger Tests
# ============================================================================


@pytest.mark.unit
class TestTriggerConverterRegexTriggers:
    """Tests for TriggerConverter regex trigger handling."""

    def test_regex_trigger_matches_pattern(self) -> None:
        """Regex trigger matches text pattern."""
        descriptor = HandlerDescriptor(
            id="demo:demo.regex",
            trigger=MessageTrigger(regex=r"hello (\w+)"),
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="hello world"),
            load_order=0,
            declaration_order=0,
        )

        assert match is not None
        assert match.handler_id == "demo:demo.regex"

    def test_regex_trigger_no_match(self) -> None:
        """Regex trigger returns None when pattern doesn't match."""
        descriptor = HandlerDescriptor(
            id="demo:demo.regex",
            trigger=MessageTrigger(regex=r"^hello$"),
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="hello world"),
            load_order=0,
            declaration_order=0,
        )

        assert match is None

    def test_regex_trigger_extracts_named_groups(self) -> None:
        """Regex trigger extracts named groups as args."""
        descriptor = HandlerDescriptor(
            id="demo:demo.regex",
            trigger=MessageTrigger(regex=r"(?P<name>\w+) is (?P<age>\d+)"),
            param_specs=[
                ParamSpec(name="name", type="str"),
                ParamSpec(name="age", type="int"),
            ],
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="Alice is 25"),
            load_order=0,
            declaration_order=0,
        )

        assert match is not None
        assert match.args.get("name") == "Alice"
        assert match.args.get("age") == "25"

    def test_regex_trigger_with_complex_pattern(self) -> None:
        """Complex regex pattern with multiple captures."""
        descriptor = HandlerDescriptor(
            id="demo:demo.complex",
            trigger=MessageTrigger(regex=r"buy (\d+) (.+) for \$(\d+)"),
            param_specs=[
                ParamSpec(name="quantity", type="int"),
                ParamSpec(name="item", type="str"),
                ParamSpec(name="price", type="int"),
            ],
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="buy 5 apples for $10"),
            load_order=0,
            declaration_order=0,
        )

        assert match is not None
        assert match.args.get("quantity") == "5"
        assert match.args.get("item") == "apples"
        assert match.args.get("price") == "10"


# ============================================================================
# TriggerConverter: Composite Filter Tests
# ============================================================================


@pytest.mark.unit
class TestTriggerConverterCompositeFilters:
    """Tests for TriggerConverter composite filter handling."""

    def test_composite_filter_and_all_match(self) -> None:
        """AND composite filter passes when all children match."""
        descriptor = HandlerDescriptor(
            id="demo:demo.filtered",
            trigger=MessageTrigger(keywords=["hello"]),
            filters=[
                CompositeFilterSpec(
                    kind="and",
                    children=[
                        PlatformFilterSpec(platforms=["discord"]),
                        MessageTypeFilterSpec(message_types=["group"]),
                    ],
                )
            ],
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(
                text="hello there",
                platform="discord",
                message_type="group",
            ),
            load_order=0,
            declaration_order=0,
        )

        assert match is not None

    def test_composite_filter_and_one_fails(self) -> None:
        """AND composite filter fails when one child fails."""
        descriptor = HandlerDescriptor(
            id="demo:demo.filtered",
            trigger=MessageTrigger(keywords=["hello"]),
            filters=[
                CompositeFilterSpec(
                    kind="and",
                    children=[
                        PlatformFilterSpec(platforms=["discord"]),
                        MessageTypeFilterSpec(message_types=["private"]),
                    ],
                )
            ],
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(
                text="hello there",
                platform="discord",
                message_type="group",
            ),
            load_order=0,
            declaration_order=0,
        )

        assert match is None

    def test_composite_filter_or_one_matches(self) -> None:
        """OR composite filter passes when any child matches."""
        descriptor = HandlerDescriptor(
            id="demo:demo.filtered",
            trigger=MessageTrigger(keywords=["hello"]),
            filters=[
                CompositeFilterSpec(
                    kind="or",
                    children=[
                        PlatformFilterSpec(platforms=["discord"]),
                        PlatformFilterSpec(platforms=["telegram"]),
                    ],
                )
            ],
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="hello there", platform="telegram"),
            load_order=0,
            declaration_order=0,
        )

        assert match is not None

    def test_composite_filter_or_all_fail(self) -> None:
        """OR composite filter fails when all children fail."""
        descriptor = HandlerDescriptor(
            id="demo:demo.filtered",
            trigger=MessageTrigger(keywords=["hello"]),
            filters=[
                CompositeFilterSpec(
                    kind="or",
                    children=[
                        PlatformFilterSpec(platforms=["discord"]),
                        PlatformFilterSpec(platforms=["telegram"]),
                    ],
                )
            ],
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="hello there", platform="qq"),
            load_order=0,
            declaration_order=0,
        )

        assert match is None

    def test_local_filter_ref_is_fail_open(self) -> None:
        """LocalFilterRef always returns True (fail-open)."""
        descriptor = HandlerDescriptor(
            id="demo:demo.filtered",
            trigger=MessageTrigger(keywords=["hello"]),
            filters=[LocalFilterRefSpec(filter_id="custom_filter")],
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="hello there"),
            load_order=0,
            declaration_order=0,
        )

        assert match is not None


# ============================================================================
# TriggerConverter: Parameter Handling Tests
# ============================================================================


@pytest.mark.unit
class TestTriggerConverterParameterHandling:
    """Tests for TriggerConverter parameter handling."""

    def test_build_command_args_single_param(self) -> None:
        """Single parameter captures entire remainder."""
        handler = SimpleNamespace(param_specs=[ParamSpec(name="text", type="str")])
        result = TriggerConverter._build_command_args(handler, "hello world")
        assert result == {"text": "hello world"}

    def test_build_command_args_multiple_params(self) -> None:
        """Multiple parameters split by whitespace."""
        handler = SimpleNamespace(
            param_specs=[
                ParamSpec(name="first", type="str"),
                ParamSpec(name="second", type="str"),
            ]
        )
        result = TriggerConverter._build_command_args(handler, "hello world")
        assert result == {"first": "hello", "second": "world"}

    def test_build_command_args_greedy_str(self) -> None:
        """Greedy string parameter captures remaining args."""
        handler = SimpleNamespace(
            param_specs=[
                ParamSpec(name="command", type="str"),
                ParamSpec(name="args", type="greedy_str"),
            ]
        )
        result = TriggerConverter._build_command_args(handler, "echo hello world test")
        assert result == {"command": "echo", "args": "hello world test"}

    def test_build_command_args_more_parts_than_params(self) -> None:
        """Extra parts are ignored when more parts than params."""
        handler = SimpleNamespace(
            param_specs=[
                ParamSpec(name="first", type="str"),
                ParamSpec(name="second", type="str"),
            ]
        )
        result = TriggerConverter._build_command_args(handler, "a b c d")
        assert result == {"first": "a", "second": "b"}

    def test_build_command_args_fewer_parts_than_params(self) -> None:
        """Missing params are not included when fewer parts."""
        handler = SimpleNamespace(
            param_specs=[
                ParamSpec(name="first", type="str"),
                ParamSpec(name="second", type="str"),
                ParamSpec(name="third", type="str"),
            ]
        )
        result = TriggerConverter._build_command_args(handler, "a b")
        assert result == {"first": "a", "second": "b"}

    def test_build_command_args_no_param_specs(self) -> None:
        """No param specs returns empty dict."""
        handler = SimpleNamespace(param_specs=None)
        result = TriggerConverter._build_command_args(handler, "hello world")
        assert result == {}

    def test_build_descriptor_command_args_single_param(self) -> None:
        """Descriptor command args with single param captures remainder."""
        param_specs = [ParamSpec(name="text", type="str")]
        result = TriggerConverter._build_descriptor_command_args(
            param_specs, "hello world"
        )
        assert result == {"text": "hello world"}

    def test_build_descriptor_command_args_empty(self) -> None:
        """Empty param specs returns empty dict."""
        result = TriggerConverter._build_descriptor_command_args([], "hello")
        assert result == {}


# ============================================================================
# TriggerConverter: Legacy Parameter Handling Tests
# ============================================================================


@pytest.mark.unit
class TestTriggerConverterLegacyParameterHandling:
    """Tests for TriggerConverter legacy parameter handling."""

    def test_legacy_arg_parameter_names_basic(self) -> None:
        """Legacy arg extraction from simple function."""

        def handler(name: str, value: int) -> None:
            pass

        names = TriggerConverter._legacy_arg_parameter_names(handler)
        assert names == ["name", "value"]

    def test_legacy_arg_parameter_names_skips_event(self) -> None:
        """Legacy arg extraction skips event parameter."""

        def handler(event: Any, name: str) -> None:
            pass

        names = TriggerConverter._legacy_arg_parameter_names(handler)
        assert names == ["name"]

    def test_legacy_arg_parameter_names_skips_ctx(self) -> None:
        """Legacy arg extraction skips ctx parameter."""

        def handler(ctx: Any, name: str) -> None:
            pass

        names = TriggerConverter._legacy_arg_parameter_names(handler)
        assert names == ["name"]

    def test_legacy_arg_parameter_names_skips_context(self) -> None:
        """Legacy arg extraction skips context parameter."""

        def handler(context: Any, name: str) -> None:
            pass

        names = TriggerConverter._legacy_arg_parameter_names(handler)
        assert names == ["name"]

    def test_is_injected_parameter_by_name(self) -> None:
        """Injected parameter detection by name."""
        assert TriggerConverter._is_injected_parameter("event", None) is True
        assert TriggerConverter._is_injected_parameter("ctx", None) is True
        assert TriggerConverter._is_injected_parameter("context", None) is True
        assert TriggerConverter._is_injected_parameter("name", None) is False

    def test_unwrap_optional_with_optional(self) -> None:
        """Unwrap Optional type annotation."""
        result = TriggerConverter._unwrap_optional(Optional[str])  # noqa: UP045
        assert result is str

    def test_unwrap_optional_with_non_optional(self) -> None:
        """Non-optional types pass through unchanged."""
        result = TriggerConverter._unwrap_optional(str)
        assert result is str

    def test_unwrap_optional_with_none(self) -> None:
        """None annotation returns None."""
        result = TriggerConverter._unwrap_optional(None)
        assert result is None


# ============================================================================
# TriggerConverter: Sort Key Tests
# ============================================================================


@pytest.mark.unit
class TestTriggerConverterSortKey:
    """Tests for TriggerConverter sort_key method."""

    def test_sort_key_higher_priority_first(self) -> None:
        """Higher priority sorts first (negative in tuple)."""
        high = TriggerMatch(
            plugin_id="a",
            handler_id="a:high",
            args={},
            priority=10,
            load_order=0,
            declaration_order=0,
        )
        low = TriggerMatch(
            plugin_id="a",
            handler_id="a:low",
            args={},
            priority=5,
            load_order=0,
            declaration_order=0,
        )

        assert TriggerConverter.sort_key(high) < TriggerConverter.sort_key(low)

    def test_sort_key_lower_load_order_first(self) -> None:
        """Lower load order sorts first when priority equal."""
        first = TriggerMatch(
            plugin_id="a",
            handler_id="a:first",
            args={},
            priority=5,
            load_order=0,
            declaration_order=0,
        )
        second = TriggerMatch(
            plugin_id="b",
            handler_id="b:second",
            args={},
            priority=5,
            load_order=1,
            declaration_order=0,
        )

        assert TriggerConverter.sort_key(first) < TriggerConverter.sort_key(second)

    def test_sort_key_lower_declaration_order_first(self) -> None:
        """Lower declaration order sorts first when priority and load order equal."""
        first = TriggerMatch(
            plugin_id="a",
            handler_id="a:first",
            args={},
            priority=5,
            load_order=0,
            declaration_order=0,
        )
        second = TriggerMatch(
            plugin_id="a",
            handler_id="a:second",
            args={},
            priority=5,
            load_order=0,
            declaration_order=1,
        )

        assert TriggerConverter.sort_key(first) < TriggerConverter.sort_key(second)


# ============================================================================
# TriggerConverter: Edge Cases
# ============================================================================


@pytest.mark.unit
class TestTriggerConverterEdgeCases:
    """Tests for TriggerConverter edge cases."""

    def test_empty_command_trigger(self) -> None:
        """Empty command name doesn't match."""
        descriptor = HandlerDescriptor(
            id="demo:demo.empty",
            trigger=CommandTrigger(command=""),
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="hello"),
            load_order=0,
            declaration_order=0,
        )

        assert match is None

    def test_empty_aliases_ignored(self) -> None:
        """Empty alias strings are ignored."""
        descriptor = HandlerDescriptor(
            id="demo:demo.alias",
            trigger=CommandTrigger(command="ping", aliases=["", "pong"]),
        )

        # Should match via "pong" alias
        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="pong hello"),
            load_order=0,
            declaration_order=0,
        )

        assert match is not None

    def test_message_trigger_no_keywords_or_regex(self) -> None:
        """Message trigger without keywords or regex matches any message."""
        descriptor = HandlerDescriptor(
            id="demo:demo.any",
            trigger=MessageTrigger(),  # No keywords or regex
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="anything"),
            load_order=0,
            declaration_order=0,
        )

        assert match is not None

    def test_message_trigger_without_keywords_matches_any_text(self) -> None:
        """MessageTrigger without keywords/regex matches any non-empty text."""
        descriptor = HandlerDescriptor(
            id="demo:demo.any",
            trigger=MessageTrigger(),  # Empty trigger matches everything
        )

        match = TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="anything at all"),
            load_order=0,
            declaration_order=0,
        )

        assert match is not None
        assert match.args == {}


# ============================================================================
# CapabilityBridgeBase: Serialization Helper Tests
# ============================================================================


@pytest.mark.unit
class TestCapabilityBridgeBaseSerialization:
    """Tests for CapabilityBridgeBase serialization helpers."""

    def test_to_iso_datetime_with_datetime(self) -> None:
        """DateTime objects are converted to ISO format."""
        dt = datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = CapabilityBridgeBase._to_iso_datetime(dt)
        assert result == "2024-06-15T10:30:00+00:00"

    def test_to_iso_datetime_with_timestamp(self) -> None:
        """Unix timestamps are converted to ISO format."""
        result = CapabilityBridgeBase._to_iso_datetime(1718443800)
        assert isinstance(result, str)
        assert "T" in result  # ISO format contains T separator

    def test_to_iso_datetime_with_none(self) -> None:
        """None returns None."""
        result = CapabilityBridgeBase._to_iso_datetime(None)
        assert result is None

    def test_to_iso_datetime_with_invalid(self) -> None:
        """Invalid values return None."""
        result = CapabilityBridgeBase._to_iso_datetime("invalid")
        assert result is None

    def test_to_iso_datetime_with_negative_timestamp(self) -> None:
        """Negative timestamps return None."""
        result = CapabilityBridgeBase._to_iso_datetime(-1)
        assert result is None

    def test_optional_int_with_int(self) -> None:
        """Integer values pass through."""
        result = CapabilityBridgeBase._optional_int(42)
        assert result == 42

    def test_optional_int_with_string(self) -> None:
        """String integers are converted."""
        result = CapabilityBridgeBase._optional_int("123")
        assert result == 123

    def test_optional_int_with_none(self) -> None:
        """None returns None."""
        result = CapabilityBridgeBase._optional_int(None)
        assert result is None

    def test_optional_int_with_invalid_string(self) -> None:
        """Invalid strings return None."""
        result = CapabilityBridgeBase._optional_int("not a number")
        assert result is None

    def test_normalize_history_items_with_list(self) -> None:
        """List of dicts passes through as list of dicts."""
        items = [{"role": "user", "content": "hello"}]
        result = CapabilityBridgeBase._normalize_history_items(items)
        assert result == items

    def test_normalize_history_items_with_json_string(self) -> None:
        """JSON string is parsed to list of dicts."""
        result = CapabilityBridgeBase._normalize_history_items(
            '[{"role": "user", "content": "hello"}]'
        )
        assert result == [{"role": "user", "content": "hello"}]

    def test_normalize_history_items_with_invalid_json(self) -> None:
        """Invalid JSON returns empty list."""
        result = CapabilityBridgeBase._normalize_history_items("not json")
        assert result == []

    def test_normalize_history_items_with_non_list_json(self) -> None:
        """Non-list JSON returns empty list."""
        result = CapabilityBridgeBase._normalize_history_items('{"key": "value"}')
        assert result == []

    def test_normalize_persona_dialogs_with_list(self) -> None:
        """List of strings passes through."""
        result = CapabilityBridgeBase._normalize_persona_dialogs(["Hello", "World"])
        assert result == ["Hello", "World"]

    def test_normalize_persona_dialogs_with_json_string(self) -> None:
        """JSON string is parsed to list of strings."""
        result = CapabilityBridgeBase._normalize_persona_dialogs('["Hello", "World"]')
        assert result == ["Hello", "World"]

    def test_normalize_session_scoped_config_with_nested(self) -> None:
        """Session config extracts nested session_id key."""
        config = {"session-1": {"key": "value"}}
        result = CapabilityBridgeBase._normalize_session_scoped_config(
            config, "session-1"
        )
        assert result == {"key": "value"}

    def test_normalize_session_scoped_config_without_nested(self) -> None:
        """Config without session_id key returns entire config."""
        config = {"key": "value"}
        result = CapabilityBridgeBase._normalize_session_scoped_config(
            config, "session-1"
        )
        assert result == {"key": "value"}

    def test_normalize_session_scoped_config_with_non_dict(self) -> None:
        """Non-dict input returns empty dict."""
        result = CapabilityBridgeBase._normalize_session_scoped_config(
            "not a dict", "session-1"
        )
        assert result == {}


# ============================================================================
# _build_message_chain_from_payload Tests
# ============================================================================


@pytest.mark.unit
class TestBuildMessageChainFromPayload:
    """Tests for _build_message_chain_from_payload function."""

    def test_text_component(self) -> None:
        """Text/plain component creates Plain message."""
        chain = _build_message_chain_from_payload(
            [{"type": "text", "data": {"text": "hello"}}]
        )
        assert chain.get_plain_text() == "hello"

    def test_plain_component(self) -> None:
        """Plain type alias creates Plain message."""
        chain = _build_message_chain_from_payload(
            [{"type": "plain", "data": {"text": "world"}}]
        )
        assert chain.get_plain_text() == "world"

    def test_image_component_with_url(self) -> None:
        """Image with URL creates Image from URL."""
        chain = _build_message_chain_from_payload(
            [{"type": "image", "data": {"url": "https://example.com/img.png"}}]
        )
        assert len(chain.chain) == 1
        # Image component should be present

    def test_image_component_with_file(self) -> None:
        """Image with file path creates Image from filesystem."""
        chain = _build_message_chain_from_payload(
            [{"type": "image", "data": {"file": "/path/to/image.png"}}]
        )
        assert len(chain.chain) == 1

    def test_image_component_with_file_uri(self) -> None:
        """Image with file:/// URI creates Image from filesystem."""
        chain = _build_message_chain_from_payload(
            [{"type": "image", "data": {"file": "file:///path/to/image.png"}}]
        )
        assert len(chain.chain) == 1

    def test_unknown_component_fallback(self) -> None:
        """Unknown component type falls back to JSON string."""
        chain = _build_message_chain_from_payload(
            [{"type": "unknown", "data": {"foo": "bar"}}]
        )
        assert "unknown" in chain.get_plain_text()

    def test_non_dict_item_skipped(self) -> None:
        """Non-dict items are skipped in message chain."""
        chain = _build_message_chain_from_payload(["plain text"])
        # Non-dict items are skipped, not converted
        assert len(chain.chain) == 0

    def test_empty_list(self) -> None:
        """Empty list creates empty chain."""
        chain = _build_message_chain_from_payload([])
        assert len(chain.chain) == 0

    def test_multiple_components(self) -> None:
        """Multiple components are combined."""
        chain = _build_message_chain_from_payload(
            [
                {"type": "text", "data": {"text": "hello "}},
                {"type": "text", "data": {"text": "world"}},
            ]
        )
        assert chain.get_plain_text() == "hello  world"


# ============================================================================
# TriggerMatch Dataclass Tests
# ============================================================================


@pytest.mark.unit
class TestTriggerMatchDataclass:
    """Tests for TriggerMatch dataclass."""

    def test_trigger_match_attributes(self) -> None:
        """TriggerMatch has all expected attributes."""
        match = TriggerMatch(
            plugin_id="demo",
            handler_id="demo:handler",
            args={"key": "value"},
            priority=5,
            load_order=0,
            declaration_order=1,
        )

        assert match.plugin_id == "demo"
        assert match.handler_id == "demo:handler"
        assert match.args == {"key": "value"}
        assert match.priority == 5
        assert match.load_order == 0
        assert match.declaration_order == 1

    def test_trigger_match_slots(self) -> None:
        """TriggerMatch uses slots for memory efficiency."""
        match = TriggerMatch(
            plugin_id="demo",
            handler_id="demo:handler",
            args={},
            priority=0,
            load_order=0,
            declaration_order=0,
        )

        # Slots prevent adding new attributes
        with pytest.raises(AttributeError):
            match.new_attribute = "value"  # type: ignore


# ============================================================================
# Additional Permissions Tests
# ============================================================================


@pytest.mark.unit
class TestPermissionsModel:
    """Additional tests for Permissions model."""

    def test_permissions_default_values(self) -> None:
        """Permissions has sensible defaults."""
        perms = Permissions()
        assert perms.required_role is None
        assert perms.require_admin is False

    def test_permissions_member_role(self) -> None:
        """Member role doesn't require admin."""
        perms = Permissions(required_role="member")
        assert perms.required_role == "member"

    def test_permissions_admin_role_equivalent(self) -> None:
        """Admin role is equivalent to require_admin=True."""
        admin_perms = Permissions(required_role="admin")
        legacy_perms = Permissions(require_admin=True)

        # Both should behave the same in permission checks
        assert admin_perms.required_role == "admin" or admin_perms.require_admin
        assert legacy_perms.require_admin


# ============================================================================
# SDK Event Payload: Sanitization Tests
# ============================================================================


@pytest.mark.unit
class TestEventPayloadSanitization:
    """Tests for SDK event payload sanitization helpers."""

    def test_sanitize_extra_value_primitives(self) -> None:
        """Primitive types pass through unchanged."""
        assert sanitize_sdk_extra_value(None) is None
        assert sanitize_sdk_extra_value("string") == "string"
        assert sanitize_sdk_extra_value(42) == 42
        assert sanitize_sdk_extra_value(3.14) == 3.14
        assert sanitize_sdk_extra_value(True) is True

    def test_sanitize_extra_value_list(self) -> None:
        """Lists are sanitized recursively."""
        result = sanitize_sdk_extra_value([1, "a", None])
        assert result == [1, "a", None]

    def test_sanitize_extra_value_list_drops_non_serializable(self) -> None:
        """Non-serializable list items are dropped."""
        # Functions are not JSON serializable
        result = sanitize_sdk_extra_value([1, lambda x: x, 2])
        assert result == [1, 2]

    def test_sanitize_extra_value_tuple(self) -> None:
        """Tuples are sanitized as lists."""
        result = sanitize_sdk_extra_value((1, 2, 3))
        assert result == [1, 2, 3]

    def test_sanitize_extra_value_dict(self) -> None:
        """Dicts are sanitized recursively."""
        result = sanitize_sdk_extra_value({"a": 1, "b": "text"})
        assert result == {"a": 1, "b": "text"}

    def test_sanitize_extra_value_dict_drops_non_serializable(self) -> None:
        """Non-serializable dict values are dropped."""
        result = sanitize_sdk_extra_value({"a": 1, "b": lambda: None})
        assert result == {"a": 1}

    def test_sanitize_extra_value_nested_structures(self) -> None:
        """Nested structures are sanitized recursively."""
        result = sanitize_sdk_extra_value(
            {
                "list": [1, {"nested": "value"}],
                "dict": {"inner": [2, 3]},
            }
        )
        assert result == {
            "list": [1, {"nested": "value"}],
            "dict": {"inner": [2, 3]},
        }

    def test_sanitize_extra_value_supports_datetime_bytes_and_uuid(self) -> None:
        """Common host-side values are normalized explicitly."""
        result = sanitize_sdk_extra_value(
            {
                "created_at": datetime(2026, 3, 28, 12, 0, 0),
                "blob": b"hello",
                "id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
            }
        )
        assert result == {
            "created_at": "2026-03-28T12:00:00",
            "blob": "hello",
            "id": "12345678-1234-5678-1234-567812345678",
        }

    def test_sanitize_extra_value_json_serializable_object(self) -> None:
        """JSON serializable objects pass through."""

        # Dataclasses with __dict__ are JSON serializable if their contents are
        class SimpleObj:
            def __init__(self) -> None:
                self.value = 42

        result = sanitize_sdk_extra_value(SimpleObj())
        assert result == {"value": 42}

    def test_sanitize_extras_empty_dict(self) -> None:
        """Empty dict returns empty dict."""
        result = sanitize_sdk_extras({})
        assert result == {}

    def test_sanitize_extras_all_dropped(self) -> None:
        """Dict with all non-serializable values returns empty dict."""
        result = sanitize_sdk_extras(
            {
                "a": lambda: None,
                "b": object(),
            }
        )
        assert result == {}

    def test_sanitize_extras_mixed_values(self) -> None:
        """Dict with mixed values keeps only serializable ones."""
        result = sanitize_sdk_extras(
            {
                "valid": "string",
                "also_valid": {"nested": 123},
                "invalid": lambda: None,
            }
        )
        assert result == {"valid": "string", "also_valid": {"nested": 123}}


# ============================================================================
# SDK Event Payload: extract_handler_result Tests
# ============================================================================


@pytest.mark.unit
class TestEventPayloadExtractHandlerResult:
    """Tests for extract_sdk_handler_result helper."""

    def test_extract_handler_result_none(self) -> None:
        """None input returns default values."""
        result = extract_sdk_handler_result(None)
        assert result == {
            "sent_message": False,
            "stop": False,
            "call_llm": False,
        }

    def test_extract_handler_result_empty_dict(self) -> None:
        """Empty dict returns default values."""
        result = extract_sdk_handler_result({})
        assert result == {
            "sent_message": False,
            "stop": False,
            "call_llm": False,
        }

    def test_extract_handler_result_all_false(self) -> None:
        """Explicitly false values are preserved."""
        result = extract_sdk_handler_result(
            {
                "sent_message": False,
                "stop": False,
                "call_llm": False,
            }
        )
        assert result == {
            "sent_message": False,
            "stop": False,
            "call_llm": False,
        }

    def test_extract_handler_result_all_true(self) -> None:
        """True values are preserved."""
        result = extract_sdk_handler_result(
            {
                "sent_message": True,
                "stop": True,
                "call_llm": True,
            }
        )
        assert result == {
            "sent_message": True,
            "stop": True,
            "call_llm": True,
        }

    def test_extract_handler_result_truthy_values(self) -> None:
        """Truthy values are converted to boolean True."""
        result = extract_sdk_handler_result(
            {
                "sent_message": 1,
                "stop": "yes",
                "call_llm": [1],
            }
        )
        assert result == {
            "sent_message": True,
            "stop": True,
            "call_llm": True,
        }

    def test_extract_handler_result_falsy_values(self) -> None:
        """Falsy values are converted to boolean False."""
        result = extract_sdk_handler_result(
            {
                "sent_message": 0,
                "stop": "",
                "call_llm": [],
            }
        )
        assert result == {
            "sent_message": False,
            "stop": False,
            "call_llm": False,
        }

    def test_extract_handler_result_extra_keys_ignored(self) -> None:
        """Extra keys in input are ignored."""
        result = extract_sdk_handler_result(
            {
                "sent_message": True,
                "extra_key": "value",
                "another_key": 123,
            }
        )
        assert result == {
            "sent_message": True,
            "stop": False,
            "call_llm": False,
        }
        assert "extra_key" not in result
