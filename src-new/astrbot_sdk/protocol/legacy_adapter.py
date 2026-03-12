from __future__ import annotations

from typing import Any

from .messages import CancelMessage, EventMessage, InvokeMessage, ResultMessage


def legacy_request_to_invoke(payload: dict[str, Any]) -> InvokeMessage:
    method = str(payload.get("method", ""))
    params = payload.get("params") or {}
    request_id = str(payload.get("id", ""))
    if method == "call_handler":
        return InvokeMessage(
            id=request_id,
            capability="handler.invoke",
            input={
                "handler_id": params.get("handler_full_name", ""),
                "event": params.get("event", {}),
                "args": params.get("args", {}),
            },
            stream=False,
        )
    return InvokeMessage(
        id=request_id,
        capability=method,
        input=params if isinstance(params, dict) else {},
        stream=False,
    )


def invoke_to_legacy_request(message: InvokeMessage) -> dict[str, Any]:
    if message.capability == "handler.invoke":
        return {
            "jsonrpc": "2.0",
            "id": message.id,
            "method": "call_handler",
            "params": {
                "handler_full_name": message.input.get("handler_id"),
                "event": message.input.get("event", {}),
                "args": message.input.get("args", {}),
            },
        }
    return {
        "jsonrpc": "2.0",
        "id": message.id,
        "method": message.capability,
        "params": message.input,
    }


def result_to_legacy_response(message: ResultMessage) -> dict[str, Any]:
    if message.success:
        return {
            "jsonrpc": "2.0",
            "id": message.id,
            "result": message.output,
        }
    return {
        "jsonrpc": "2.0",
        "id": message.id,
        "error": {
            "code": -32000,
            "message": message.error.message if message.error else "unknown error",
            "data": message.error.model_dump() if message.error else None,
        },
    }


def event_to_legacy_notification(message: EventMessage) -> dict[str, Any]:
    method = {
        "started": "handler_stream_start",
        "delta": "handler_stream_update",
        "completed": "handler_stream_end",
        "failed": "handler_stream_end",
    }[message.phase]
    params: dict[str, Any] = {"id": message.id}
    if message.phase == "delta":
        params["data"] = message.data
    if message.phase == "failed" and message.error is not None:
        params["error"] = message.error.model_dump()
    return {"jsonrpc": "2.0", "method": method, "params": params}


def cancel_to_legacy_request(message: CancelMessage) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message.id,
        "method": "cancel",
        "params": {"reason": message.reason},
    }
