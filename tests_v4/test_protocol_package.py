"""Tests for protocol package exports."""

from __future__ import annotations

import astrbot_sdk.protocol as protocol_module

from astrbot_sdk.protocol import (
    CapabilityDescriptor,
    CommandTrigger,
    ErrorPayload,
    EventMessage,
    HandlerDescriptor,
    InitializeMessage,
    MessageTrigger,
    PeerInfo,
    ProtocolMessage,
    ResultMessage,
    ScheduleTrigger,
    parse_message,
)
from astrbot_sdk.protocol.descriptors import BUILTIN_CAPABILITY_SCHEMAS
from astrbot_sdk.protocol.legacy_adapter import (
    LegacyAdapter,
    LegacyRequest,
    parse_legacy_message,
)


class TestProtocolPackageExports:
    """Ensure protocol package exposes the intended public surface."""

    def test_core_exports_are_importable(self):
        """Core protocol models and parsers should be importable from package root."""
        handler = HandlerDescriptor(
            id="demo.handler",
            trigger=CommandTrigger(command="hello"),
        )
        message = InitializeMessage(
            id="msg-1",
            protocol_version="1.0",
            peer=PeerInfo(name="plugin", role="plugin"),
            handlers=[handler],
        )
        parsed: ProtocolMessage = parse_message(message)

        assert isinstance(parsed, InitializeMessage)
        assert isinstance(ErrorPayload(code="x", message="y"), ErrorPayload)
        assert isinstance(
            CapabilityDescriptor(
                name="llm.chat",
                description="chat",
                input_schema=BUILTIN_CAPABILITY_SCHEMAS["llm.chat"]["input"],
                output_schema=BUILTIN_CAPABILITY_SCHEMAS["llm.chat"]["output"],
            ),
            CapabilityDescriptor,
        )
        assert isinstance(MessageTrigger(keywords=["hello"]), MessageTrigger)
        assert isinstance(ScheduleTrigger(interval_seconds=60), ScheduleTrigger)
        assert isinstance(EventMessage(id="evt-1", phase="started"), EventMessage)
        assert isinstance(ResultMessage(id="res-1", success=True), ResultMessage)

    def test_protocol_root_does_not_reexport_legacy_helpers(self):
        """protocol root should stay focused on native v4 models."""
        assert not hasattr(protocol_module, "LegacyAdapter")
        assert not hasattr(protocol_module, "LegacyRequest")
        assert not hasattr(protocol_module, "parse_legacy_message")

    def test_legacy_exports_are_available_from_submodule(self):
        """Legacy adapter helpers remain available from the explicit submodule."""
        legacy = parse_legacy_message({"jsonrpc": "2.0", "method": "handshake"})

        assert isinstance(legacy, LegacyRequest)
        assert isinstance(LegacyAdapter(), LegacyAdapter)
