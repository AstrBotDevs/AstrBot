from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .descriptors import EventTrigger, HandlerDescriptor, Permissions
from .messages import (
    CancelMessage,
    ErrorPayload,
    EventMessage,
    InitializeMessage,
    InvokeMessage,
    PeerInfo,
    ProtocolMessage,
    ResultMessage,
)

LEGACY_JSONRPC_VERSION = "2.0"
LEGACY_CONTEXT_CAPABILITY = "internal.legacy.call_context_function"
LEGACY_HANDSHAKE_METADATA_KEY = "legacy_handshake_payload"
LEGACY_PLUGIN_KEYS_METADATA_KEY = "legacy_plugin_keys"
LEGACY_ADAPTER_MESSAGE_EVENT = 3


class _LegacyMessageBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LegacyErrorData(_LegacyMessageBase):
    code: int = -32000
    message: str
    data: Any | None = None


class LegacyRequest(_LegacyMessageBase):
    jsonrpc: Literal["2.0"] = LEGACY_JSONRPC_VERSION
    id: str | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class _LegacyResponse(_LegacyMessageBase):
    jsonrpc: Literal["2.0"] = LEGACY_JSONRPC_VERSION
    id: str | None = None


class LegacySuccessResponse(_LegacyResponse):
    result: Any = Field(default_factory=dict)


class LegacyErrorResponse(_LegacyResponse):
    error: LegacyErrorData


LegacyMessage = LegacyRequest | LegacySuccessResponse | LegacyErrorResponse
LegacyToV4Message = InitializeMessage | InvokeMessage | ResultMessage | EventMessage | CancelMessage


class LegacyAdapter:
    def __init__(
        self,
        *,
        protocol_version: str = "1.0",
        legacy_peer_name: str = "legacy-peer",
        legacy_peer_role: Literal["plugin", "core"] = "plugin",
        legacy_peer_version: str | None = None,
    ) -> None:
        self.protocol_version = protocol_version
        self.legacy_peer_name = legacy_peer_name
        self.legacy_peer_role = legacy_peer_role
        self.legacy_peer_version = legacy_peer_version
        self._handler_names_by_request_id: dict[str, str] = {}
        self._pending_handshake_ids: set[str] = set()

    def track_handler(self, request_id: str, handler_full_name: str) -> None:
        if request_id:
            self._handler_names_by_request_id[request_id] = handler_full_name

    def legacy_to_v4(
        self,
        payload: str | bytes | dict[str, Any] | LegacyMessage,
    ) -> LegacyToV4Message:
        message = parse_legacy_message(payload)
        if isinstance(message, LegacyRequest):
            return self.legacy_request_to_message(message)
        if isinstance(message, LegacySuccessResponse):
            return self.legacy_response_to_message(message)
        return self.legacy_error_to_result(message)

    def legacy_request_to_message(
        self,
        payload: LegacyRequest | dict[str, Any],
    ) -> InitializeMessage | InvokeMessage | EventMessage | CancelMessage:
        message = payload if isinstance(payload, LegacyRequest) else LegacyRequest.model_validate(payload)
        params = message.params or {}
        method = message.method

        if method == "handshake":
            request_id = self._request_id(message.id, "legacy-handshake")
            self._pending_handshake_ids.add(request_id)
            return InitializeMessage(
                id=request_id,
                protocol_version=self.protocol_version,
                peer=PeerInfo(
                    name=self.legacy_peer_name,
                    role=self.legacy_peer_role,
                    version=self.legacy_peer_version,
                ),
                handlers=[],
                metadata={"legacy_handshake": True},
            )

        if method == "call_handler":
            request_id = self._request_id(message.id, "legacy-call-handler")
            handler_full_name = str(params.get("handler_full_name", ""))
            self.track_handler(request_id, handler_full_name)
            return InvokeMessage(
                id=request_id,
                capability="handler.invoke",
                input={
                    "handler_id": handler_full_name,
                    "event": self._as_dict(params.get("event"), field_name="data"),
                    "args": self._as_dict(params.get("args"), field_name="value"),
                },
                stream=False,
            )

        if method == "call_context_function":
            request_id = self._request_id(message.id, "legacy-context")
            return InvokeMessage(
                id=request_id,
                capability=LEGACY_CONTEXT_CAPABILITY,
                input={
                    "name": str(params.get("name", "")),
                    "args": self._as_dict(params.get("args"), field_name="value"),
                },
                stream=False,
            )

        if method == "handler_stream_start":
            request_id = self._request_id(params.get("id"), "legacy-stream")
            handler_full_name = str(params.get("handler_full_name", ""))
            self.track_handler(request_id, handler_full_name)
            return EventMessage(id=request_id, phase="started")

        if method == "handler_stream_update":
            request_id = self._request_id(params.get("id"), "legacy-stream")
            handler_full_name = str(params.get("handler_full_name", ""))
            self.track_handler(request_id, handler_full_name)
            return EventMessage(
                id=request_id,
                phase="delta",
                data=self._as_dict(params.get("data"), field_name="value"),
            )

        if method == "handler_stream_end":
            request_id = self._request_id(params.get("id"), "legacy-stream")
            handler_full_name = str(params.get("handler_full_name", ""))
            self.track_handler(request_id, handler_full_name)
            error = params.get("error")
            if isinstance(error, dict):
                return EventMessage(
                    id=request_id,
                    phase="failed",
                    error=ErrorPayload.model_validate(self._coerce_error_payload(error)),
                )
            return EventMessage(id=request_id, phase="completed")

        if method == "cancel":
            return CancelMessage(
                id=self._request_id(message.id, "legacy-cancel"),
                reason=str(params.get("reason", "user_cancelled")),
            )

        return InvokeMessage(
            id=self._request_id(message.id, "legacy-invoke"),
            capability=method,
            input=self._as_dict(params, field_name="data"),
            stream=False,
        )

    def legacy_response_to_message(
        self,
        payload: LegacySuccessResponse | dict[str, Any],
    ) -> InitializeMessage | ResultMessage:
        message = payload if isinstance(payload, LegacySuccessResponse) else LegacySuccessResponse.model_validate(payload)
        request_id = self._request_id(message.id, "legacy-result")

        if request_id in self._pending_handshake_ids or self._looks_like_handshake_payload(message.result):
            self._pending_handshake_ids.discard(request_id)
            payload_dict = self._as_dict(message.result, field_name="data")
            peer_name, peer_version = self._legacy_peer_from_handshake_payload(payload_dict)
            return InitializeMessage(
                id=request_id,
                protocol_version=self.protocol_version,
                peer=PeerInfo(
                    name=peer_name,
                    role=self.legacy_peer_role,
                    version=peer_version,
                ),
                handlers=self._legacy_handlers_to_descriptors(payload_dict),
                metadata={
                    LEGACY_HANDSHAKE_METADATA_KEY: payload_dict,
                    LEGACY_PLUGIN_KEYS_METADATA_KEY: sorted(payload_dict.keys()),
                },
            )

        return ResultMessage(
            id=request_id,
            success=True,
            output=self._as_dict(message.result, field_name="data"),
        )

    def legacy_error_to_result(
        self,
        payload: LegacyErrorResponse | dict[str, Any],
    ) -> ResultMessage:
        message = payload if isinstance(payload, LegacyErrorResponse) else LegacyErrorResponse.model_validate(payload)
        request_id = self._request_id(message.id, "legacy-error")
        kind = None
        if request_id in self._pending_handshake_ids:
            self._pending_handshake_ids.discard(request_id)
            kind = "initialize_result"
        return ResultMessage(
            id=request_id,
            kind=kind,
            success=False,
            error=ErrorPayload.model_validate(self._legacy_error_to_payload(message.error)),
        )

    def build_legacy_handshake_request(self, request_id: str) -> dict[str, Any]:
        self._pending_handshake_ids.add(request_id)
        return {
            "jsonrpc": LEGACY_JSONRPC_VERSION,
            "id": request_id,
            "method": "handshake",
            "params": {},
        }

    def initialize_to_legacy_handshake_response(
        self,
        message: InitializeMessage,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        response_id = request_id or message.id
        payload = self._legacy_handshake_payload_from_initialize(message)
        return {
            "jsonrpc": LEGACY_JSONRPC_VERSION,
            "id": response_id,
            "result": payload,
        }

    def invoke_to_legacy_request(self, message: InvokeMessage) -> dict[str, Any]:
        if message.capability == "handler.invoke":
            handler_full_name = str(message.input.get("handler_id", ""))
            self.track_handler(message.id, handler_full_name)
            return {
                "jsonrpc": LEGACY_JSONRPC_VERSION,
                "id": message.id,
                "method": "call_handler",
                "params": {
                    "handler_full_name": handler_full_name,
                    "event": self._as_dict(message.input.get("event"), field_name="data"),
                    "args": self._as_dict(message.input.get("args"), field_name="value"),
                },
            }

        if message.capability == LEGACY_CONTEXT_CAPABILITY:
            return {
                "jsonrpc": LEGACY_JSONRPC_VERSION,
                "id": message.id,
                "method": "call_context_function",
                "params": {
                    "name": str(message.input.get("name", "")),
                    "args": self._as_dict(message.input.get("args"), field_name="value"),
                },
            }

        return {
            "jsonrpc": LEGACY_JSONRPC_VERSION,
            "id": message.id,
            "method": message.capability,
            "params": self._as_dict(message.input, field_name="data"),
        }

    def result_to_legacy_response(self, message: ResultMessage) -> dict[str, Any]:
        self._handler_names_by_request_id.pop(message.id, None)
        if message.success:
            return {
                "jsonrpc": LEGACY_JSONRPC_VERSION,
                "id": message.id,
                "result": message.output,
            }
        return {
            "jsonrpc": LEGACY_JSONRPC_VERSION,
            "id": message.id,
            "error": {
                "code": -32000,
                "message": message.error.message if message.error else "unknown error",
                "data": message.error.model_dump() if message.error else None,
            },
        }

    def event_to_legacy_notification(self, message: EventMessage) -> dict[str, Any]:
        method = {
            "started": "handler_stream_start",
            "delta": "handler_stream_update",
            "completed": "handler_stream_end",
            "failed": "handler_stream_end",
        }[message.phase]
        params: dict[str, Any] = {
            "id": message.id,
            "handler_full_name": self._handler_names_by_request_id.get(message.id, ""),
        }
        if message.phase == "delta":
            params["data"] = message.data
        if message.phase == "failed" and message.error is not None:
            params["error"] = message.error.model_dump()
        return {
            "jsonrpc": LEGACY_JSONRPC_VERSION,
            "method": method,
            "params": params,
        }

    def cancel_to_legacy_request(self, message: CancelMessage) -> dict[str, Any]:
        return {
            "jsonrpc": LEGACY_JSONRPC_VERSION,
            "id": message.id,
            "method": "cancel",
            "params": {"reason": message.reason},
        }

    @staticmethod
    def _request_id(value: Any, fallback: str) -> str:
        text = "" if value is None else str(value)
        return text or fallback

    @staticmethod
    def _as_dict(value: Any, *, field_name: str) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        return {field_name: value}

    @staticmethod
    def _looks_like_handshake_payload(value: Any) -> bool:
        if not isinstance(value, dict) or not value:
            return False
        return all(isinstance(item, dict) and "handlers" in item for item in value.values())

    @staticmethod
    def _coerce_error_payload(value: dict[str, Any]) -> dict[str, Any]:
        if {"code", "message"}.issubset(value):
            return {
                "code": str(value.get("code", "legacy_rpc_error")),
                "message": str(value.get("message", "legacy error")),
                "hint": str(value.get("hint", "")),
                "retryable": bool(value.get("retryable", False)),
            }
        return {
            "code": "legacy_rpc_error",
            "message": str(value.get("message", "legacy error")),
            "hint": "",
            "retryable": False,
        }

    @staticmethod
    def _legacy_error_to_payload(error: LegacyErrorData) -> dict[str, Any]:
        if isinstance(error.data, dict) and {"code", "message"}.issubset(error.data):
            return LegacyAdapter._coerce_error_payload(error.data)
        return {
            "code": "legacy_rpc_error",
            "message": error.message,
            "hint": "",
            "retryable": False,
        }

    def _legacy_handlers_to_descriptors(
        self,
        payload: dict[str, Any],
    ) -> list[HandlerDescriptor]:
        handlers: list[HandlerDescriptor] = []
        for star_info in payload.values():
            star_handlers = star_info.get("handlers") or []
            if not isinstance(star_handlers, list):
                continue
            for handler_data in star_handlers:
                if isinstance(handler_data, dict):
                    handlers.append(self._legacy_handler_to_descriptor(handler_data))
        return handlers

    @staticmethod
    def _legacy_handler_to_descriptor(handler_data: dict[str, Any]) -> HandlerDescriptor:
        extras_configs = handler_data.get("extras_configs")
        extras = extras_configs if isinstance(extras_configs, dict) else {}
        handler_id = str(
            handler_data.get("handler_full_name")
            or f"{handler_data.get('handler_module_path', 'legacy')}.{handler_data.get('handler_name', 'handler')}"
        )
        event_type = handler_data.get("event_type", LEGACY_ADAPTER_MESSAGE_EVENT)
        permissions = Permissions(
            require_admin=bool(extras.get("require_admin", False)),
            level=int(extras.get("level", 0) or 0),
        )
        return HandlerDescriptor(
            id=handler_id,
            trigger=EventTrigger(event_type=str(event_type)),
            priority=int(extras.get("priority", 0) or 0),
            permissions=permissions,
        )

    def _legacy_handshake_payload_from_initialize(
        self,
        message: InitializeMessage,
    ) -> dict[str, Any]:
        raw_payload = message.metadata.get(LEGACY_HANDSHAKE_METADATA_KEY)
        if isinstance(raw_payload, dict) and raw_payload:
            return raw_payload

        plugin_name = str(message.metadata.get("plugin_id") or message.peer.name)
        display_name = str(message.metadata.get("display_name") or plugin_name)
        module_path = str(message.metadata.get("module_path") or f"{plugin_name}.main")
        root_dir_name = str(message.metadata.get("root_dir_name") or plugin_name)
        handlers = [self._descriptor_to_legacy_handler(item) for item in message.handlers]
        return {
            module_path: {
                "name": plugin_name,
                "author": message.metadata.get("author", "legacy-adapter"),
                "desc": message.metadata.get("desc", ""),
                "version": message.peer.version,
                "repo": message.metadata.get("repo"),
                "module_path": module_path,
                "root_dir_name": root_dir_name,
                "reserved": bool(message.metadata.get("reserved", False)),
                "activated": bool(message.metadata.get("activated", True)),
                "config": message.metadata.get("config"),
                "star_handler_full_names": [item["handler_full_name"] for item in handlers],
                "display_name": display_name,
                "logo_path": message.metadata.get("logo_path"),
                "handlers": handlers,
            }
        }

    @staticmethod
    def _descriptor_to_legacy_handler(descriptor: HandlerDescriptor) -> dict[str, Any]:
        module_path, _, handler_name = descriptor.id.rpartition(".")
        if not module_path:
            module_path = descriptor.id
            handler_name = descriptor.id
        desc = getattr(descriptor.trigger, "description", None)
        event_type: int | str = LEGACY_ADAPTER_MESSAGE_EVENT
        if isinstance(descriptor.trigger, EventTrigger):
            event_type = (
                int(descriptor.trigger.event_type)
                if descriptor.trigger.event_type.isdigit()
                else descriptor.trigger.event_type
            )
        return {
            "event_type": event_type,
            "handler_full_name": descriptor.id,
            "handler_name": handler_name,
            "handler_module_path": module_path,
            "desc": desc or "",
            "extras_configs": {
                "priority": descriptor.priority,
                "require_admin": descriptor.permissions.require_admin,
                "level": descriptor.permissions.level,
            },
        }

    def _legacy_peer_from_handshake_payload(
        self,
        payload: dict[str, Any],
    ) -> tuple[str, str | None]:
        first_star = next(iter(payload.values()), {})
        if not isinstance(first_star, dict):
            return self.legacy_peer_name, self.legacy_peer_version
        peer_name = str(first_star.get("name") or self.legacy_peer_name)
        version_value = first_star.get("version")
        peer_version = None if version_value is None else str(version_value)
        return peer_name, peer_version or self.legacy_peer_version


def parse_legacy_message(
    payload: str | bytes | dict[str, Any] | LegacyMessage,
) -> LegacyMessage:
    if isinstance(payload, (LegacyRequest, LegacySuccessResponse, LegacyErrorResponse)):
        return payload
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    if "method" in payload:
        return LegacyRequest.model_validate(payload)
    if "result" in payload:
        return LegacySuccessResponse.model_validate(payload)
    if "error" in payload:
        return LegacyErrorResponse.model_validate(payload)
    raise ValueError("未知 legacy JSON-RPC 消息类型")


def legacy_message_to_v4(
    payload: str | bytes | dict[str, Any] | LegacyMessage,
) -> LegacyToV4Message:
    return LegacyAdapter().legacy_to_v4(payload)


def legacy_request_to_invoke(payload: dict[str, Any]) -> InvokeMessage:
    message = LegacyAdapter().legacy_request_to_message(payload)
    if not isinstance(message, InvokeMessage):
        raise ValueError("legacy request 不能直接映射为 invoke")
    return message


def legacy_response_to_message(
    payload: dict[str, Any],
) -> InitializeMessage | ResultMessage:
    message = LegacyAdapter().legacy_response_to_message(payload)
    return message


def initialize_to_legacy_handshake_response(
    message: InitializeMessage,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    return LegacyAdapter().initialize_to_legacy_handshake_response(
        message,
        request_id=request_id,
    )


def invoke_to_legacy_request(message: InvokeMessage) -> dict[str, Any]:
    return LegacyAdapter().invoke_to_legacy_request(message)


def result_to_legacy_response(message: ResultMessage) -> dict[str, Any]:
    return LegacyAdapter().result_to_legacy_response(message)


def event_to_legacy_notification(
    message: EventMessage,
    *,
    handler_full_name: str | None = None,
) -> dict[str, Any]:
    adapter = LegacyAdapter()
    if handler_full_name:
        adapter.track_handler(message.id, handler_full_name)
    return adapter.event_to_legacy_notification(message)


def cancel_to_legacy_request(message: CancelMessage) -> dict[str, Any]:
    return LegacyAdapter().cancel_to_legacy_request(message)


__all__ = [
    "LEGACY_ADAPTER_MESSAGE_EVENT",
    "LEGACY_CONTEXT_CAPABILITY",
    "LEGACY_HANDSHAKE_METADATA_KEY",
    "LEGACY_PLUGIN_KEYS_METADATA_KEY",
    "LegacyAdapter",
    "LegacyErrorData",
    "LegacyErrorResponse",
    "LegacyRequest",
    "LegacySuccessResponse",
    "cancel_to_legacy_request",
    "event_to_legacy_notification",
    "initialize_to_legacy_handshake_response",
    "invoke_to_legacy_request",
    "legacy_message_to_v4",
    "legacy_request_to_invoke",
    "legacy_response_to_message",
    "parse_legacy_message",
    "result_to_legacy_response",
]
