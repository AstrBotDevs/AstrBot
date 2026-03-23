# ruff: noqa: E402
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    HandlerDescriptor,
    MessageTrigger,
    MessageTypeFilterSpec,
    Permissions,
    PlatformFilterSpec,
)

from astrbot.core.sdk_bridge.event_converter import EventConverter

_TRIGGER_CONVERTER_SPEC = importlib.util.spec_from_file_location(
    "astrbot_sdk_bridge_trigger_converter_test",
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
    "astrbot_sdk_bridge_trigger_converter_test",
    _TRIGGER_CONVERTER_MODULE,
)
_TRIGGER_CONVERTER_SPEC.loader.exec_module(_TRIGGER_CONVERTER_MODULE)
TriggerConverter = _TRIGGER_CONVERTER_MODULE.TriggerConverter


class _FakeEvent:
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


@pytest.mark.unit
def test_trigger_converter_matches_command_and_respects_admin() -> None:
    descriptor = HandlerDescriptor(
        id="demo:demo.echo",
        trigger=CommandTrigger(command="ping"),
        priority=5,
        permissions=Permissions(require_admin=True),
    )

    assert (
        TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="ping hello", admin=False),
            load_order=0,
            declaration_order=0,
        )
        is None
    )

    match = TriggerConverter.match_handler(
        plugin_id="demo",
        descriptor=descriptor,
        event=_FakeEvent(text="ping hello", admin=True),
        load_order=0,
        declaration_order=0,
    )

    assert match is not None
    assert match.plugin_id == "demo"
    assert match.handler_id == "demo:demo.echo"


@pytest.mark.unit
def test_permissions_model_normalizes_required_role() -> None:
    assert Permissions(require_admin=True) == Permissions(required_role="admin")

    with pytest.raises(ValueError, match="conflicts"):
        Permissions(require_admin=True, required_role="member")


@pytest.mark.unit
def test_trigger_converter_respects_required_role_metadata() -> None:
    admin_descriptor = HandlerDescriptor(
        id="demo:demo.admin",
        trigger=CommandTrigger(command="panel"),
        permissions=Permissions(required_role="admin"),
    )
    member_descriptor = HandlerDescriptor(
        id="demo:demo.member",
        trigger=CommandTrigger(command="ping"),
        permissions=Permissions(required_role="member"),
    )

    assert (
        TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=admin_descriptor,
            event=_FakeEvent(text="panel", admin=False),
            load_order=0,
            declaration_order=0,
        )
        is None
    )
    assert (
        TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=admin_descriptor,
            event=_FakeEvent(text="panel", admin=True),
            load_order=0,
            declaration_order=0,
        )
        is not None
    )
    assert (
        TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=member_descriptor,
            event=_FakeEvent(text="ping", admin=False),
            load_order=0,
            declaration_order=0,
        )
        is not None
    )


@pytest.mark.unit
def test_trigger_converter_matches_command_aliases() -> None:
    descriptor = HandlerDescriptor(
        id="demo:demo.alias",
        trigger=CommandTrigger(command="ping", aliases=["pong", "echo"]),
    )

    match = TriggerConverter.match_handler(
        plugin_id="demo",
        descriptor=descriptor,
        event=_FakeEvent(text="pong hello world"),
        load_order=0,
        declaration_order=0,
    )

    assert match is not None
    assert match.handler_id == "demo:demo.alias"
    assert match.args == {}


@pytest.mark.unit
def test_trigger_converter_matches_message_keywords() -> None:
    descriptor = HandlerDescriptor(
        id="demo:demo.keyword",
        trigger=MessageTrigger(keywords=["bridge", "sdk"]),
    )

    match = TriggerConverter.match_handler(
        plugin_id="demo",
        descriptor=descriptor,
        event=_FakeEvent(text="this bridge test should match"),
        load_order=0,
        declaration_order=0,
    )

    assert match is not None
    assert match.handler_id == "demo:demo.keyword"
    assert match.args == {}


@pytest.mark.unit
def test_trigger_converter_applies_platform_and_message_type_filters() -> None:
    descriptor = HandlerDescriptor(
        id="demo:demo.filtered",
        trigger=MessageTrigger(keywords=["hello"]),
        filters=[
            PlatformFilterSpec(platforms=["discord"]),
            MessageTypeFilterSpec(message_types=["group"]),
        ],
    )

    assert (
        TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="hello there", platform="discord", message_type="group"),
            load_order=0,
            declaration_order=0,
        )
        is not None
    )
    assert (
        TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(
                text="hello there",
                platform="telegram",
                message_type="group",
            ),
            load_order=0,
            declaration_order=0,
        )
        is None
    )
    assert (
        TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(
                text="hello there",
                platform="discord",
                message_type="private",
            ),
            load_order=0,
            declaration_order=0,
        )
        is None
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (_FakeEvent(text="", message_type="channel", group_id="group-1"), "group"),
        (_FakeEvent(text="", message_type="channel", group_id="", sender_id="user-1"), "private"),
        (_FakeEvent(text="", message_type="channel", group_id="", sender_id=None), "other"),
    ],
)
def test_message_type_name_falls_back_to_event_shape(
    event: _FakeEvent,
    expected: str,
) -> None:
    assert TriggerConverter._message_type_name(event) == expected  # noqa: SLF001


@pytest.mark.unit
def test_split_command_remainder_falls_back_when_shlex_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_value_error(_remainder: str) -> list[str]:
        raise ValueError("bad quoting")

    monkeypatch.setattr(_TRIGGER_CONVERTER_MODULE.shlex, "split", _raise_value_error)

    assert TriggerConverter._split_command_remainder('hello "bridge test') == [  # noqa: SLF001
        "hello",
        '"bridge',
        "test",
    ]


@pytest.mark.unit
def test_extract_handler_result_defaults_when_result_is_missing() -> None:
    assert EventConverter.extract_handler_result(None) == {
        "sent_message": False,
        "stop": False,
        "call_llm": False,
    }


@pytest.mark.unit
def test_extract_handler_result_normalizes_truthy_flags() -> None:
    assert EventConverter.extract_handler_result(
        {"sent_message": 1, "stop": "yes", "call_llm": True}
    ) == {
        "sent_message": True,
        "stop": True,
        "call_llm": True,
    }
