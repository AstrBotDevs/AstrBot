"""
Tests for protocol/legacy_adapter.py - Legacy protocol adapter.
"""
from __future__ import annotations

import pytest

from astrbot_sdk.protocol.descriptors import EventTrigger, HandlerDescriptor, Permissions
from astrbot_sdk.protocol.legacy_adapter import (
    LEGACY_ADAPTER_MESSAGE_EVENT,
    LEGACY_CONTEXT_CAPABILITY,
    LEGACY_HANDSHAKE_METADATA_KEY,
    LEGACY_JSONRPC_VERSION,
    LEGACY_PLUGIN_KEYS_METADATA_KEY,
    LegacyAdapter,
    LegacyErrorData,
    LegacyErrorResponse,
    LegacyRequest,
    LegacySuccessResponse,
    cancel_to_legacy_request,
    event_to_legacy_notification,
    initialize_to_legacy_handshake_response,
    invoke_to_legacy_request,
    legacy_message_to_v4,
    legacy_request_to_invoke,
    legacy_response_to_message,
    parse_legacy_message,
    result_to_legacy_response,
)
from astrbot_sdk.protocol.messages import (
    CancelMessage,
    ErrorPayload,
    EventMessage,
    InitializeMessage,
    InvokeMessage,
    PeerInfo,
    ResultMessage,
)


class TestLegacyRequest:
    """Tests for LegacyRequest model."""

    def test_default_values(self):
        """LegacyRequest should have default values."""
        req = LegacyRequest(method="test_method")
        assert req.jsonrpc == LEGACY_JSONRPC_VERSION
        assert req.id is None
        assert req.method == "test_method"
        assert req.params == {}

    def test_with_all_fields(self):
        """LegacyRequest should accept all fields."""
        req = LegacyRequest(
            id="req_001",
            method="handshake",
            params={"key": "value"},
        )
        assert req.id == "req_001"
        assert req.method == "handshake"
        assert req.params["key"] == "value"


class TestLegacySuccessResponse:
    """Tests for LegacySuccessResponse model."""

    def test_with_result(self):
        """LegacySuccessResponse should accept result."""
        resp = LegacySuccessResponse(id="req_001", result={"status": "ok"})
        assert resp.jsonrpc == LEGACY_JSONRPC_VERSION
        assert resp.id == "req_001"
        assert resp.result["status"] == "ok"


class TestLegacyErrorResponse:
    """Tests for LegacyErrorResponse model."""

    def test_with_error(self):
        """LegacyErrorResponse should accept error."""
        error = LegacyErrorData(code=-32000, message="Server error")
        resp = LegacyErrorResponse(id="req_001", error=error)
        assert resp.id == "req_001"
        assert resp.error.code == -32000
        assert resp.error.message == "Server error"


class TestLegacyErrorData:
    """Tests for LegacyErrorData model."""

    def test_default_code(self):
        """LegacyErrorData should have default code."""
        error = LegacyErrorData(message="Error")
        assert error.code == -32000
        assert error.message == "Error"
        assert error.data is None

    def test_with_data(self):
        """LegacyErrorData should accept data."""
        error = LegacyErrorData(
            code=-32600,
            message="Invalid Request",
            data={"details": "Missing field"},
        )
        assert error.code == -32600
        assert error.data["details"] == "Missing field"


class TestParseLegacyMessage:
    """Tests for parse_legacy_message function."""

    def test_parse_request(self):
        """parse_legacy_message should parse LegacyRequest."""
        payload = {"jsonrpc": "2.0", "id": "1", "method": "test", "params": {}}
        msg = parse_legacy_message(payload)
        assert isinstance(msg, LegacyRequest)
        assert msg.method == "test"

    def test_parse_request_from_json(self):
        """parse_legacy_message should parse request from JSON string."""
        json_str = '{"jsonrpc": "2.0", "id": "1", "method": "handshake"}'
        msg = parse_legacy_message(json_str)
        assert isinstance(msg, LegacyRequest)
        assert msg.method == "handshake"

    def test_parse_request_from_bytes(self):
        """parse_legacy_message should parse request from bytes."""
        json_bytes = b'{"jsonrpc": "2.0", "method": "call_handler"}'
        msg = parse_legacy_message(json_bytes)
        assert isinstance(msg, LegacyRequest)
        assert msg.method == "call_handler"

    def test_parse_success_response(self):
        """parse_legacy_message should parse LegacySuccessResponse."""
        payload = {"jsonrpc": "2.0", "id": "1", "result": {"status": "ok"}}
        msg = parse_legacy_message(payload)
        assert isinstance(msg, LegacySuccessResponse)
        assert msg.result["status"] == "ok"

    def test_parse_error_response(self):
        """parse_legacy_message should parse LegacyErrorResponse."""
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "error": {"code": -32000, "message": "Error"},
        }
        msg = parse_legacy_message(payload)
        assert isinstance(msg, LegacyErrorResponse)
        assert msg.error.message == "Error"

    def test_parse_unknown_raises(self):
        """parse_legacy_message should raise for unknown type."""
        with pytest.raises(ValueError) as exc_info:
            parse_legacy_message({"jsonrpc": "2.0", "unknown": "field"})
        assert "未知" in str(exc_info.value)

    def test_pass_through_legacy_message(self):
        """parse_legacy_message should pass through already-parsed messages."""
        req = LegacyRequest(method="test")
        result = parse_legacy_message(req)
        assert result is req


class TestLegacyAdapterInit:
    """Tests for LegacyAdapter initialization."""

    def test_default_values(self):
        """LegacyAdapter should have default values."""
        adapter = LegacyAdapter()
        assert adapter.protocol_version == "1.0"
        assert adapter.legacy_peer_name == "legacy-peer"
        assert adapter.legacy_peer_role == "plugin"
        assert adapter.legacy_peer_version is None

    def test_custom_values(self):
        """LegacyAdapter should accept custom values."""
        adapter = LegacyAdapter(
            protocol_version="2.0",
            legacy_peer_name="custom-peer",
            legacy_peer_role="core",
            legacy_peer_version="1.5.0",
        )
        assert adapter.protocol_version == "2.0"
        assert adapter.legacy_peer_name == "custom-peer"
        assert adapter.legacy_peer_role == "core"
        assert adapter.legacy_peer_version == "1.5.0"


class TestLegacyAdapterTrackHandler:
    """Tests for LegacyAdapter.track_handler method."""

    def test_track_handler(self):
        """track_handler should store handler name by request ID."""
        adapter = LegacyAdapter()
        adapter.track_handler("req_001", "module.handler")
        assert adapter._handler_names_by_request_id["req_001"] == "module.handler"

    def test_track_handler_empty_id(self):
        """track_handler should not store for empty request ID."""
        adapter = LegacyAdapter()
        adapter.track_handler("", "module.handler")
        assert "" not in adapter._handler_names_by_request_id


class TestLegacyAdapterHandshake:
    """Tests for LegacyAdapter handshake handling."""

    def test_legacy_request_to_handshake(self):
        """legacy_request_to_message should convert handshake request."""
        adapter = LegacyAdapter()
        req = LegacyRequest(id="req_001", method="handshake", params={})
        msg = adapter.legacy_request_to_message(req)

        assert isinstance(msg, InitializeMessage)
        assert msg.protocol_version == "1.0"
        assert msg.peer.name == "legacy-peer"
        assert msg.peer.role == "plugin"
        assert msg.metadata.get("legacy_handshake") is True

    def test_build_legacy_handshake_request(self):
        """build_legacy_handshake_request should create handshake request."""
        adapter = LegacyAdapter()
        result = adapter.build_legacy_handshake_request("req_001")

        assert result["jsonrpc"] == LEGACY_JSONRPC_VERSION
        assert result["id"] == "req_001"
        assert result["method"] == "handshake"


class TestLegacyAdapterCallHandler:
    """Tests for LegacyAdapter call_handler handling."""

    def test_legacy_request_to_call_handler(self):
        """legacy_request_to_message should convert call_handler request."""
        adapter = LegacyAdapter()
        req = LegacyRequest(
            id="req_001",
            method="call_handler",
            params={
                "handler_full_name": "module.handler",
                "event": {"type": "message"},
                "args": {"key": "value"},
            },
        )
        msg = adapter.legacy_request_to_message(req)

        assert isinstance(msg, InvokeMessage)
        assert msg.capability == "handler.invoke"
        assert msg.input["handler_id"] == "module.handler"
        assert msg.input["event"]["type"] == "message"

    def test_call_handler_tracks_handler(self):
        """call_handler should track handler name."""
        adapter = LegacyAdapter()
        req = LegacyRequest(
            id="req_001",
            method="call_handler",
            params={"handler_full_name": "test.handler"},
        )
        adapter.legacy_request_to_message(req)
        assert adapter._handler_names_by_request_id["req_001"] == "test.handler"


class TestLegacyAdapterContextFunction:
    """Tests for LegacyAdapter call_context_function handling."""

    def test_legacy_request_to_context_function(self):
        """legacy_request_to_message should convert call_context_function."""
        adapter = LegacyAdapter()
        req = LegacyRequest(
            id="req_001",
            method="call_context_function",
            params={"name": "get_user", "args": {"user_id": 123}},
        )
        msg = adapter.legacy_request_to_message(req)

        assert isinstance(msg, InvokeMessage)
        assert msg.capability == LEGACY_CONTEXT_CAPABILITY
        assert msg.input["name"] == "get_user"
        assert msg.input["args"]["user_id"] == 123


class TestLegacyAdapterStreamMethods:
    """Tests for LegacyAdapter stream handling."""

    def test_handler_stream_start(self):
        """legacy_request_to_message should convert handler_stream_start."""
        adapter = LegacyAdapter()
        req = LegacyRequest(
            method="handler_stream_start",
            params={"id": "stream_001", "handler_full_name": "module.handler"},
        )
        msg = adapter.legacy_request_to_message(req)

        assert isinstance(msg, EventMessage)
        assert msg.phase == "started"

    def test_handler_stream_update(self):
        """legacy_request_to_message should convert handler_stream_update."""
        adapter = LegacyAdapter()
        req = LegacyRequest(
            method="handler_stream_update",
            params={
                "id": "stream_001",
                "handler_full_name": "module.handler",
                "data": {"text": "chunk"},
            },
        )
        msg = adapter.legacy_request_to_message(req)

        assert isinstance(msg, EventMessage)
        assert msg.phase == "delta"
        assert msg.data["text"] == "chunk"

    def test_handler_stream_end_completed(self):
        """legacy_request_to_message should convert handler_stream_end (completed)."""
        adapter = LegacyAdapter()
        req = LegacyRequest(
            method="handler_stream_end",
            params={"id": "stream_001", "handler_full_name": "module.handler"},
        )
        msg = adapter.legacy_request_to_message(req)

        assert isinstance(msg, EventMessage)
        assert msg.phase == "completed"

    def test_handler_stream_end_failed(self):
        """legacy_request_to_message should convert handler_stream_end (failed)."""
        adapter = LegacyAdapter()
        req = LegacyRequest(
            method="handler_stream_end",
            params={
                "id": "stream_001",
                "handler_full_name": "module.handler",
                "error": {"message": "Something went wrong"},
            },
        )
        msg = adapter.legacy_request_to_message(req)

        assert isinstance(msg, EventMessage)
        assert msg.phase == "failed"
        assert msg.error is not None
        assert msg.error.message == "Something went wrong"


class TestLegacyAdapterCancel:
    """Tests for LegacyAdapter cancel handling."""

    def test_legacy_request_to_cancel(self):
        """legacy_request_to_message should convert cancel request."""
        adapter = LegacyAdapter()
        req = LegacyRequest(
            id="req_001",
            method="cancel",
            params={"reason": "user_cancelled"},
        )
        msg = adapter.legacy_request_to_message(req)

        assert isinstance(msg, CancelMessage)
        assert msg.reason == "user_cancelled"


class TestLegacyAdapterGenericMethod:
    """Tests for LegacyAdapter generic method handling."""

    def test_unknown_method_becomes_invoke(self):
        """Unknown methods should become InvokeMessage with capability=method."""
        adapter = LegacyAdapter()
        req = LegacyRequest(
            id="req_001",
            method="custom.capability",
            params={"key": "value"},
        )
        msg = adapter.legacy_request_to_message(req)

        assert isinstance(msg, InvokeMessage)
        assert msg.capability == "custom.capability"
        assert msg.input["key"] == "value"


class TestLegacyAdapterResponseHandling:
    """Tests for LegacyAdapter response handling."""

    def test_success_response_to_result(self):
        """legacy_response_to_message should convert success response."""
        adapter = LegacyAdapter()
        resp = LegacySuccessResponse(id="req_001", result={"status": "ok"})
        msg = adapter.legacy_response_to_message(resp)

        assert isinstance(msg, ResultMessage)
        assert msg.success is True
        assert msg.output["status"] == "ok"

    def test_error_response_to_result(self):
        """legacy_error_to_result should convert error response."""
        adapter = LegacyAdapter()
        error = LegacyErrorData(code=-32000, message="Server error")
        resp = LegacyErrorResponse(id="req_001", error=error)
        msg = adapter.legacy_error_to_result(resp)

        assert isinstance(msg, ResultMessage)
        assert msg.success is False
        assert msg.error.code == "legacy_rpc_error"
        assert msg.error.message == "Server error"

    def test_handshake_response_to_initialize(self):
        """legacy_response_to_message should detect handshake response."""
        adapter = LegacyAdapter()
        resp = LegacySuccessResponse(
            id="req_001",
            result={
                "module.path": {
                    "name": "test-plugin",
                    "version": "1.0.0",
                    "handlers": [],
                }
            },
        )
        msg = adapter.legacy_response_to_message(resp)

        assert isinstance(msg, InitializeMessage)
        assert msg.peer.name == "test-plugin"
        assert msg.peer.version == "1.0.0"


class TestLegacyAdapterV4ToLegacy:
    """Tests for LegacyAdapter V4 to legacy conversion."""

    def test_initialize_to_legacy_handshake_response(self):
        """initialize_to_legacy_handshake_response should convert InitializeMessage."""
        adapter = LegacyAdapter()
        init_msg = InitializeMessage(
            id="msg_001",
            protocol_version="1.0",
            peer=PeerInfo(name="test", role="plugin", version="1.0.0"),
            handlers=[],
            metadata={
                "plugin_id": "test-plugin",
                "display_name": "Test Plugin",
            },
        )
        result = adapter.initialize_to_legacy_handshake_response(init_msg)

        assert result["jsonrpc"] == LEGACY_JSONRPC_VERSION
        assert result["id"] == "msg_001"
        assert "result" in result

    def test_initialize_with_legacy_payload(self):
        """initialize_to_legacy_handshake_response should preserve legacy payload."""
        adapter = LegacyAdapter()
        legacy_payload = {
            "module.path": {
                "name": "test-plugin",
                "version": "1.0.0",
                "handlers": [],
            }
        }
        init_msg = InitializeMessage(
            id="msg_001",
            protocol_version="1.0",
            peer=PeerInfo(name="test", role="plugin", version="1.0.0"),
            handlers=[],
            metadata={LEGACY_HANDSHAKE_METADATA_KEY: legacy_payload},
        )
        result = adapter.initialize_to_legacy_handshake_response(init_msg)

        assert result["result"] == legacy_payload

    def test_invoke_to_legacy_request_handler(self):
        """invoke_to_legacy_request should convert handler.invoke."""
        adapter = LegacyAdapter()
        invoke_msg = InvokeMessage(
            id="msg_001",
            capability="handler.invoke",
            input={
                "handler_id": "module.handler",
                "event": {"type": "message"},
                "args": {},
            },
        )
        result = adapter.invoke_to_legacy_request(invoke_msg)

        assert result["method"] == "call_handler"
        assert result["params"]["handler_full_name"] == "module.handler"

    def test_invoke_to_legacy_request_context_function(self):
        """invoke_to_legacy_request should convert context function."""
        adapter = LegacyAdapter()
        invoke_msg = InvokeMessage(
            id="msg_001",
            capability=LEGACY_CONTEXT_CAPABILITY,
            input={"name": "get_user", "args": {}},
        )
        result = adapter.invoke_to_legacy_request(invoke_msg)

        assert result["method"] == "call_context_function"
        assert result["params"]["name"] == "get_user"

    def test_invoke_to_legacy_request_generic(self):
        """invoke_to_legacy_request should convert generic capability."""
        adapter = LegacyAdapter()
        invoke_msg = InvokeMessage(
            id="msg_001",
            capability="custom.capability",
            input={"key": "value"},
        )
        result = adapter.invoke_to_legacy_request(invoke_msg)

        assert result["method"] == "custom.capability"
        assert result["params"]["key"] == "value"

    def test_result_to_legacy_response_success(self):
        """result_to_legacy_response should convert success result."""
        adapter = LegacyAdapter()
        result_msg = ResultMessage(
            id="msg_001",
            success=True,
            output={"status": "ok"},
        )
        result = adapter.result_to_legacy_response(result_msg)

        assert "result" in result
        assert result["result"]["status"] == "ok"

    def test_result_to_legacy_response_error(self):
        """result_to_legacy_response should convert error result."""
        adapter = LegacyAdapter()
        result_msg = ResultMessage(
            id="msg_001",
            success=False,
            error=ErrorPayload(code="error", message="Failed"),
        )
        result = adapter.result_to_legacy_response(result_msg)

        assert "error" in result
        assert result["error"]["message"] == "Failed"

    def test_event_to_legacy_notification_started(self):
        """event_to_legacy_notification should convert started event."""
        adapter = LegacyAdapter()
        adapter.track_handler("msg_001", "module.handler")
        event_msg = EventMessage(id="msg_001", phase="started")
        result = adapter.event_to_legacy_notification(event_msg)

        assert result["method"] == "handler_stream_start"
        assert result["params"]["handler_full_name"] == "module.handler"

    def test_event_to_legacy_notification_delta(self):
        """event_to_legacy_notification should convert delta event."""
        adapter = LegacyAdapter()
        event_msg = EventMessage(
            id="msg_001",
            phase="delta",
            data={"text": "chunk"},
        )
        result = adapter.event_to_legacy_notification(event_msg)

        assert result["method"] == "handler_stream_update"
        assert result["params"]["data"]["text"] == "chunk"

    def test_event_to_legacy_notification_completed(self):
        """event_to_legacy_notification should convert completed event."""
        adapter = LegacyAdapter()
        event_msg = EventMessage(id="msg_001", phase="completed")
        result = adapter.event_to_legacy_notification(event_msg)

        assert result["method"] == "handler_stream_end"

    def test_event_to_legacy_notification_failed(self):
        """event_to_legacy_notification should convert failed event."""
        adapter = LegacyAdapter()
        event_msg = EventMessage(
            id="msg_001",
            phase="failed",
            error=ErrorPayload(code="error", message="Failed"),
        )
        result = adapter.event_to_legacy_notification(event_msg)

        assert result["method"] == "handler_stream_end"
        assert result["params"]["error"]["message"] == "Failed"

    def test_cancel_to_legacy_request(self):
        """cancel_to_legacy_request should convert cancel message."""
        adapter = LegacyAdapter()
        cancel_msg = CancelMessage(id="msg_001", reason="user_request")
        result = adapter.cancel_to_legacy_request(cancel_msg)

        assert result["method"] == "cancel"
        assert result["params"]["reason"] == "user_request"


class TestLegacyAdapterHandlerDescriptors:
    """Tests for LegacyAdapter handler descriptor conversion."""

    def test_legacy_handlers_to_descriptors(self):
        """_legacy_handlers_to_descriptors should convert handlers."""
        adapter = LegacyAdapter()
        payload = {
            "module.path": {
                "handlers": [
                    {
                        "handler_full_name": "module.handler",
                        "event_type": "3",
                        "extras_configs": {
                            "priority": 10,
                            "require_admin": True,
                            "level": 5,
                        },
                    }
                ]
            }
        }
        handlers = adapter._legacy_handlers_to_descriptors(payload)

        assert len(handlers) == 1
        assert handlers[0].id == "module.handler"
        assert handlers[0].priority == 10
        assert handlers[0].permissions.require_admin is True
        assert handlers[0].permissions.level == 5

    def test_descriptor_to_legacy_handler(self):
        """_descriptor_to_legacy_handler should convert HandlerDescriptor."""
        descriptor = HandlerDescriptor(
            id="module.handler",
            trigger=EventTrigger(event_type="3"),
            priority=10,
            permissions=Permissions(require_admin=True, level=5),
        )
        result = LegacyAdapter._descriptor_to_legacy_handler(descriptor)

        assert result["handler_full_name"] == "module.handler"
        assert result["event_type"] == 3
        assert result["extras_configs"]["priority"] == 10
        assert result["extras_configs"]["require_admin"] is True


class TestLegacyAdapterHelpers:
    """Tests for LegacyAdapter helper methods."""

    def test_request_id_with_value(self):
        """_request_id should return string value."""
        result = LegacyAdapter._request_id("req_001", "fallback")
        assert result == "req_001"

    def test_request_id_with_none(self):
        """_request_id should return fallback for None."""
        result = LegacyAdapter._request_id(None, "fallback")
        assert result == "fallback"

    def test_request_id_with_empty_string(self):
        """_request_id should return fallback for empty string."""
        result = LegacyAdapter._request_id("", "fallback")
        assert result == "fallback"

    def test_as_dict_with_dict(self):
        """_as_dict should pass through dict."""
        result = LegacyAdapter._as_dict({"key": "value"}, field_name="data")
        assert result == {"key": "value"}

    def test_as_dict_with_none(self):
        """_as_dict should return empty dict for None."""
        result = LegacyAdapter._as_dict(None, field_name="data")
        assert result == {}

    def test_as_dict_with_other(self):
        """_as_dict should wrap other values."""
        result = LegacyAdapter._as_dict("value", field_name="data")
        assert result == {"data": "value"}

    def test_looks_like_handshake_payload_valid(self):
        """_looks_like_handshake_payload should detect valid payload."""
        payload = {"module.path": {"handlers": []}}
        assert LegacyAdapter._looks_like_handshake_payload(payload) is True

    def test_looks_like_handshake_payload_invalid(self):
        """_looks_like_handshake_payload should reject invalid payload."""
        assert LegacyAdapter._looks_like_handshake_payload({}) is False
        assert LegacyAdapter._looks_like_handshake_payload({"key": "value"}) is False
        assert LegacyAdapter._looks_like_handshake_payload(None) is False


class TestLegacyConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_legacy_message_to_v4(self):
        """legacy_message_to_v4 should convert legacy message."""
        payload = {"jsonrpc": "2.0", "method": "handshake"}
        msg = legacy_message_to_v4(payload)
        assert isinstance(msg, InitializeMessage)

    def test_legacy_request_to_invoke(self):
        """legacy_request_to_invoke should convert to InvokeMessage."""
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "custom.capability",
            "params": {},
        }
        msg = legacy_request_to_invoke(payload)
        assert isinstance(msg, InvokeMessage)
        assert msg.capability == "custom.capability"

    def test_legacy_request_to_invoke_non_invoke_raises(self):
        """legacy_request_to_invoke should raise for non-invoke messages."""
        payload = {"jsonrpc": "2.0", "method": "handshake"}
        with pytest.raises(ValueError, match="不能直接映射为 invoke"):
            legacy_request_to_invoke(payload)

    def test_legacy_response_to_message(self):
        """legacy_response_to_message should convert response."""
        payload = {"jsonrpc": "2.0", "id": "1", "result": {"status": "ok"}}
        msg = legacy_response_to_message(payload)
        assert isinstance(msg, ResultMessage)

    def test_initialize_to_legacy_handshake_response(self):
        """initialize_to_legacy_handshake_response should convert."""
        msg = InitializeMessage(
            id="msg_001",
            protocol_version="1.0",
            peer=PeerInfo(name="test", role="plugin"),
            handlers=[],
        )
        result = initialize_to_legacy_handshake_response(msg)
        assert result["jsonrpc"] == LEGACY_JSONRPC_VERSION

    def test_invoke_to_legacy_request(self):
        """invoke_to_legacy_request should convert."""
        msg = InvokeMessage(id="msg_001", capability="test.cap", input={})
        result = invoke_to_legacy_request(msg)
        assert result["method"] == "test.cap"

    def test_result_to_legacy_response(self):
        """result_to_legacy_response should convert."""
        msg = ResultMessage(id="msg_001", success=True, output={"ok": True})
        result = result_to_legacy_response(msg)
        assert result["result"]["ok"] is True

    def test_event_to_legacy_notification(self):
        """event_to_legacy_notification should convert."""
        msg = EventMessage(id="msg_001", phase="started")
        result = event_to_legacy_notification(msg, handler_full_name="test.handler")
        assert result["method"] == "handler_stream_start"

    def test_cancel_to_legacy_request(self):
        """cancel_to_legacy_request should convert."""
        msg = CancelMessage(id="msg_001", reason="test")
        result = cancel_to_legacy_request(msg)
        assert result["method"] == "cancel"


class TestLegacyConstants:
    """Tests for legacy adapter constants."""

    def test_jsonrpc_version(self):
        """LEGACY_JSONRPC_VERSION should be 2.0."""
        assert LEGACY_JSONRPC_VERSION == "2.0"

    def test_context_capability(self):
        """LEGACY_CONTEXT_CAPABILITY should be internal capability."""
        assert LEGACY_CONTEXT_CAPABILITY == "internal.legacy.call_context_function"

    def test_message_event(self):
        """LEGACY_ADAPTER_MESSAGE_EVENT should be 3."""
        assert LEGACY_ADAPTER_MESSAGE_EVENT == 3

    def test_metadata_keys(self):
        """Metadata keys should be defined."""
        assert LEGACY_HANDSHAKE_METADATA_KEY == "legacy_handshake_payload"
        assert LEGACY_PLUGIN_KEYS_METADATA_KEY == "legacy_plugin_keys"
