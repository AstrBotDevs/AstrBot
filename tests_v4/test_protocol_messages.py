"""
Tests for protocol/messages.py - Protocol message models.
"""

from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from astrbot_sdk.protocol.descriptors import (
    BUILTIN_CAPABILITY_SCHEMAS,
    CapabilityDescriptor,
    CommandTrigger,
    HandlerDescriptor,
)
from astrbot_sdk.protocol.messages import (
    CancelMessage,
    ErrorPayload,
    EventMessage,
    InitializeMessage,
    InitializeOutput,
    InvokeMessage,
    PeerInfo,
    ResultMessage,
    parse_message,
)


class TestErrorPayload:
    """Tests for ErrorPayload model."""

    def test_required_code_and_message(self):
        """ErrorPayload requires code and message."""
        error = ErrorPayload(code="test_error", message="Test error occurred")
        assert error.code == "test_error"
        assert error.message == "Test error occurred"
        assert error.hint == ""
        assert error.retryable is False

    def test_with_all_fields(self):
        """ErrorPayload should accept all fields."""
        error = ErrorPayload(
            code="server_error",
            message="Internal server error",
            hint="Try again later",
            retryable=True,
        )
        assert error.code == "server_error"
        assert error.message == "Internal server error"
        assert error.hint == "Try again later"
        assert error.retryable is True

    def test_model_dump(self):
        """ErrorPayload should serialize correctly."""
        error = ErrorPayload(
            code="not_found",
            message="Resource not found",
            hint="Check the ID",
        )
        data = error.model_dump()
        assert data == {
            "code": "not_found",
            "message": "Resource not found",
            "hint": "Check the ID",
            "retryable": False,
        }

    def test_extra_fields_forbidden(self):
        """ErrorPayload should forbid extra fields."""
        with pytest.raises(ValidationError):
            ErrorPayload(code="test", message="test", extra="field")


class TestPeerInfo:
    """Tests for PeerInfo model."""

    def test_required_name_and_role(self):
        """PeerInfo requires name and role."""
        peer = PeerInfo(name="test-plugin", role="plugin")
        assert peer.name == "test-plugin"
        assert peer.role == "plugin"
        assert peer.version is None

    def test_with_version(self):
        """PeerInfo should accept version."""
        peer = PeerInfo(name="my-plugin", role="plugin", version="1.0.0")
        assert peer.version == "1.0.0"

    def test_role_must_be_valid(self):
        """PeerInfo role must be 'plugin' or 'core'."""
        peer1 = PeerInfo(name="p1", role="plugin")
        assert peer1.role == "plugin"

        peer2 = PeerInfo(name="p2", role="core")
        assert peer2.role == "core"

        with pytest.raises(ValidationError):
            PeerInfo(name="p3", role="invalid")

    def test_model_dump(self):
        """PeerInfo should serialize correctly."""
        peer = PeerInfo(name="test", role="plugin", version="2.0.0")
        data = peer.model_dump()
        assert data == {"name": "test", "role": "plugin", "version": "2.0.0"}

    def test_extra_fields_forbidden(self):
        """PeerInfo should forbid extra fields."""
        with pytest.raises(ValidationError):
            PeerInfo(name="test", role="plugin", extra="field")


class TestInitializeMessage:
    """Tests for InitializeMessage model."""

    def test_required_fields(self):
        """InitializeMessage requires id, protocol_version, and peer."""
        peer = PeerInfo(name="test", role="plugin")
        msg = InitializeMessage(
            id="msg_001",
            protocol_version="1.0",
            peer=peer,
        )
        assert msg.type == "initialize"
        assert msg.id == "msg_001"
        assert msg.protocol_version == "1.0"
        assert msg.peer == peer
        assert msg.handlers == []
        assert msg.metadata == {}

    def test_with_handlers(self):
        """InitializeMessage should accept handlers."""
        peer = PeerInfo(name="test", role="plugin")
        handler = HandlerDescriptor(
            id="test.handler",
            trigger=CommandTrigger(command="hello"),
        )
        msg = InitializeMessage(
            id="msg_002",
            protocol_version="1.0",
            peer=peer,
            handlers=[handler],
        )
        assert len(msg.handlers) == 1
        assert msg.handlers[0].id == "test.handler"

    def test_with_metadata(self):
        """InitializeMessage should accept metadata."""
        peer = PeerInfo(name="test", role="plugin")
        msg = InitializeMessage(
            id="msg_003",
            protocol_version="1.0",
            peer=peer,
            metadata={"author": "test", "version": "1.0.0"},
        )
        assert msg.metadata["author"] == "test"
        assert msg.metadata["version"] == "1.0.0"

    def test_with_provided_capabilities(self):
        """InitializeMessage should carry plugin-provided capabilities."""
        peer = PeerInfo(name="test", role="plugin")
        capability = CapabilityDescriptor(
            name="demo.echo",
            description="Echo capability",
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
            output_schema={
                "type": "object",
                "properties": {"echo": {"type": "string"}},
            },
        )
        msg = InitializeMessage(
            id="msg_caps",
            protocol_version="1.0",
            peer=peer,
            provided_capabilities=[capability],
        )

        assert [item.name for item in msg.provided_capabilities] == ["demo.echo"]

    def test_model_dump_json(self):
        """InitializeMessage should serialize to JSON correctly."""
        peer = PeerInfo(name="test", role="plugin", version="1.0.0")
        handler = HandlerDescriptor(
            id="test.handler",
            trigger=CommandTrigger(command="hello"),
        )
        msg = InitializeMessage(
            id="msg_004",
            protocol_version="1.0",
            peer=peer,
            handlers=[handler],
            metadata={"key": "value"},
        )
        json_str = msg.model_dump_json()
        data = json.loads(json_str)
        assert data["type"] == "initialize"
        assert data["id"] == "msg_004"
        assert data["peer"]["name"] == "test"
        assert len(data["handlers"]) == 1


class TestInitializeOutput:
    """Tests for InitializeOutput model."""

    def test_required_peer(self):
        """InitializeOutput requires peer."""
        peer = PeerInfo(name="core", role="core")
        output = InitializeOutput(peer=peer)
        assert output.peer == peer
        assert output.capabilities == []
        assert output.metadata == {}

    def test_with_capabilities(self):
        """InitializeOutput should accept capabilities."""
        peer = PeerInfo(name="core", role="core")
        cap = CapabilityDescriptor(
            name="llm.chat",
            description="Chat capability",
            input_schema=copy.deepcopy(BUILTIN_CAPABILITY_SCHEMAS["llm.chat"]["input"]),
            output_schema=copy.deepcopy(
                BUILTIN_CAPABILITY_SCHEMAS["llm.chat"]["output"]
            ),
        )
        output = InitializeOutput(peer=peer, capabilities=[cap])
        assert len(output.capabilities) == 1
        assert output.capabilities[0].name == "llm.chat"

    def test_with_metadata(self):
        """InitializeOutput should accept metadata."""
        peer = PeerInfo(name="core", role="core")
        output = InitializeOutput(peer=peer, metadata={"session": "abc"})
        assert output.metadata["session"] == "abc"


class TestResultMessage:
    """Tests for ResultMessage model."""

    def test_success_result(self):
        """ResultMessage for success case."""
        msg = ResultMessage(id="msg_001", success=True, output={"text": "ok"})
        assert msg.type == "result"
        assert msg.id == "msg_001"
        assert msg.success is True
        assert msg.output["text"] == "ok"
        assert msg.error is None
        assert msg.kind is None

    def test_error_result(self):
        """ResultMessage for error case."""
        error = ErrorPayload(code="not_found", message="Resource not found")
        msg = ResultMessage(id="msg_002", success=False, error=error)
        assert msg.success is False
        assert msg.error.code == "not_found"
        assert msg.error.message == "Resource not found"

    def test_with_kind(self):
        """ResultMessage should accept kind."""
        msg = ResultMessage(
            id="msg_003",
            kind="initialize_result",
            success=True,
        )
        assert msg.kind == "initialize_result"

    def test_default_output(self):
        """ResultMessage should have empty dict as default output."""
        msg = ResultMessage(id="msg_004", success=True)
        assert msg.output == {}

    def test_success_result_rejects_error(self):
        """ResultMessage success=true should not accept error payload."""
        with pytest.raises(ValidationError) as exc_info:
            ResultMessage(
                id="msg_005",
                success=True,
                error=ErrorPayload(code="bad", message="bad"),
            )
        assert "success=true 时 error 必须为空" in str(exc_info.value)

    def test_failed_result_requires_error(self):
        """ResultMessage success=false should require error payload."""
        with pytest.raises(ValidationError) as exc_info:
            ResultMessage(id="msg_006", success=False)
        assert "success=false 时必须提供 error" in str(exc_info.value)

    def test_failed_result_rejects_output(self):
        """ResultMessage success=false should not carry success output."""
        with pytest.raises(ValidationError) as exc_info:
            ResultMessage(
                id="msg_007",
                success=False,
                output={"text": "bad"},
                error=ErrorPayload(code="bad", message="bad"),
            )
        assert "success=false 时 output 必须为空" in str(exc_info.value)


class TestInvokeMessage:
    """Tests for InvokeMessage model."""

    def test_required_fields(self):
        """InvokeMessage requires id and capability."""
        msg = InvokeMessage(id="msg_001", capability="llm.chat")
        assert msg.type == "invoke"
        assert msg.id == "msg_001"
        assert msg.capability == "llm.chat"
        assert msg.input == {}
        assert msg.stream is False

    def test_with_input(self):
        """InvokeMessage should accept input payload."""
        msg = InvokeMessage(
            id="msg_002",
            capability="db.get",
            input={"key": "user:123"},
        )
        assert msg.input["key"] == "user:123"

    def test_with_stream(self):
        """InvokeMessage should accept stream flag."""
        msg = InvokeMessage(
            id="msg_003",
            capability="llm.stream",
            input={"prompt": "hello"},
            stream=True,
        )
        assert msg.stream is True

    def test_model_dump(self):
        """InvokeMessage should serialize correctly."""
        msg = InvokeMessage(
            id="msg_004",
            capability="test.cap",
            input={"data": "value"},
            stream=True,
        )
        data = msg.model_dump()
        assert data["type"] == "invoke"
        assert data["capability"] == "test.cap"
        assert data["input"] == {"data": "value"}
        assert data["stream"] is True


class TestEventMessage:
    """Tests for EventMessage model."""

    def test_started_phase(self):
        """EventMessage with started phase."""
        msg = EventMessage(id="msg_001", phase="started")
        assert msg.type == "event"
        assert msg.phase == "started"
        assert msg.data == {}
        assert msg.output == {}
        assert msg.error is None

    def test_delta_phase(self):
        """EventMessage with delta phase and data."""
        msg = EventMessage(
            id="msg_002",
            phase="delta",
            data={"text": "chunk"},
        )
        assert msg.phase == "delta"
        assert msg.data["text"] == "chunk"

    def test_completed_phase(self):
        """EventMessage with completed phase."""
        msg = EventMessage(
            id="msg_003",
            phase="completed",
            output={"result": "done"},
        )
        assert msg.phase == "completed"
        assert msg.output["result"] == "done"

    def test_failed_phase(self):
        """EventMessage with failed phase."""
        error = ErrorPayload(code="runtime_error", message="Failed")
        msg = EventMessage(
            id="msg_004",
            phase="failed",
            error=error,
        )
        assert msg.phase == "failed"
        assert msg.error.code == "runtime_error"

    def test_invalid_phase(self):
        """EventMessage should reject invalid phase."""
        with pytest.raises(ValidationError):
            EventMessage(id="msg_005", phase="invalid")


class TestCancelMessage:
    """Tests for CancelMessage model."""

    def test_default_reason(self):
        """CancelMessage should have default reason."""
        msg = CancelMessage(id="msg_001")
        assert msg.type == "cancel"
        assert msg.id == "msg_001"
        assert msg.reason == "user_cancelled"

    def test_custom_reason(self):
        """CancelMessage should accept custom reason."""
        msg = CancelMessage(id="msg_002", reason="timeout")
        assert msg.reason == "timeout"

    def test_model_dump(self):
        """CancelMessage should serialize correctly."""
        msg = CancelMessage(id="msg_003", reason="user_request")
        data = msg.model_dump()
        assert data == {
            "type": "cancel",
            "id": "msg_003",
            "reason": "user_request",
        }


class TestParseMessage:
    """Tests for parse_message function."""

    def test_parse_initialize_from_dict(self):
        """parse_message should parse InitializeMessage from dict."""
        data = {
            "type": "initialize",
            "id": "msg_001",
            "protocol_version": "1.0",
            "peer": {"name": "test", "role": "plugin"},
        }
        msg = parse_message(data)
        assert isinstance(msg, InitializeMessage)
        assert msg.id == "msg_001"
        assert msg.peer.name == "test"

    def test_parse_result_from_dict(self):
        """parse_message should parse ResultMessage from dict."""
        data = {
            "type": "result",
            "id": "msg_002",
            "success": True,
            "output": {"text": "ok"},
        }
        msg = parse_message(data)
        assert isinstance(msg, ResultMessage)
        assert msg.success is True

    def test_parse_invoke_from_dict(self):
        """parse_message should parse InvokeMessage from dict."""
        data = {
            "type": "invoke",
            "id": "msg_003",
            "capability": "test.cap",
            "input": {"key": "value"},
        }
        msg = parse_message(data)
        assert isinstance(msg, InvokeMessage)
        assert msg.capability == "test.cap"

    def test_parse_event_from_dict(self):
        """parse_message should parse EventMessage from dict."""
        data = {
            "type": "event",
            "id": "msg_004",
            "phase": "delta",
            "data": {"text": "chunk"},
        }
        msg = parse_message(data)
        assert isinstance(msg, EventMessage)
        assert msg.phase == "delta"

    def test_parse_cancel_from_dict(self):
        """parse_message should parse CancelMessage from dict."""
        data = {
            "type": "cancel",
            "id": "msg_005",
            "reason": "user_request",
        }
        msg = parse_message(data)
        assert isinstance(msg, CancelMessage)
        assert msg.reason == "user_request"

    def test_parse_from_json_string(self):
        """parse_message should parse from JSON string."""
        json_str = '{"type": "invoke", "id": "msg_006", "capability": "test"}'
        msg = parse_message(json_str)
        assert isinstance(msg, InvokeMessage)
        assert msg.capability == "test"

    def test_parse_from_bytes(self):
        """parse_message should parse from bytes."""
        json_bytes = b'{"type": "result", "id": "msg_007", "success": true}'
        msg = parse_message(json_bytes)
        assert isinstance(msg, ResultMessage)
        assert msg.success is True

    def test_parse_pass_through_model(self):
        """parse_message should return already-parsed protocol models unchanged."""
        original = InvokeMessage(id="msg_008", capability="test.cap")
        assert parse_message(original) is original

    def test_parse_non_mapping_raises(self):
        """parse_message should reject non-object payloads."""
        with pytest.raises(ValueError, match="JSON object"):
            parse_message(["not", "an", "object"])

    def test_parse_unknown_type_raises(self):
        """parse_message should raise for unknown type."""
        with pytest.raises(ValueError) as exc_info:
            parse_message({"type": "unknown"})
        assert "未知消息类型" in str(exc_info.value)

    def test_roundtrip_serialize_deserialize(self):
        """Message should survive serialize/deserialize roundtrip."""
        original = InitializeMessage(
            id="msg_008",
            protocol_version="1.0",
            peer=PeerInfo(name="test", role="plugin", version="1.0.0"),
            handlers=[
                HandlerDescriptor(
                    id="test.handler",
                    trigger=CommandTrigger(command="hello"),
                )
            ],
            metadata={"key": "value"},
        )
        json_str = original.model_dump_json()
        parsed = parse_message(json_str)
        assert isinstance(parsed, InitializeMessage)
        assert parsed.id == original.id
        assert parsed.peer.name == original.peer.name
        assert len(parsed.handlers) == 1


class TestMessageExtraForbidden:
    """Tests for extra field rejection across all message types."""

    def test_initialize_extra_forbidden(self):
        """InitializeMessage should reject extra fields."""
        with pytest.raises(ValidationError):
            InitializeMessage(
                id="msg_001",
                protocol_version="1.0",
                peer={"name": "test", "role": "plugin"},
                extra="field",
            )

    def test_result_extra_forbidden(self):
        """ResultMessage should reject extra fields."""
        with pytest.raises(ValidationError):
            ResultMessage(
                id="msg_001",
                success=True,
                extra="field",
            )

    def test_invoke_extra_forbidden(self):
        """InvokeMessage should reject extra fields."""
        with pytest.raises(ValidationError):
            InvokeMessage(
                id="msg_001",
                capability="test",
                extra="field",
            )

    def test_event_extra_forbidden(self):
        """EventMessage should reject extra fields."""
        with pytest.raises(ValidationError):
            EventMessage(
                id="msg_001",
                phase="started",
                extra="field",
            )

    def test_cancel_extra_forbidden(self):
        """CancelMessage should reject extra fields."""
        with pytest.raises(ValidationError):
            CancelMessage(id="msg_001", extra="field")
