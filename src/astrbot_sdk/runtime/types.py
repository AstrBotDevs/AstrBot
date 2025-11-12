from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from .rpc.jsonrpc import JSONRPCRequest
from typing import Any, Literal, Type
from ..api.event.astr_message_event import AstrMessageEventModel

class HandshakeRequest(JSONRPCRequest):
    class Params(BaseModel):
        pass

    method: Literal["handshake"]
    params: Params = Field(default_factory=Params)


class CallHandlerRequest(JSONRPCRequest):
    class Params(BaseModel):
        handler_full_name: str
        event: AstrMessageEventModel
        args: dict[str, Any] = {}

        @model_validator(mode="before")
        @classmethod
        def validate_event_data(cls: Type[CallHandlerRequest.Params], data: Any) -> Any:
            if isinstance(data, dict):
                event_data = data.get("event")
                if isinstance(event_data, dict):
                    data["event"] = AstrMessageEventModel.model_validate(event_data)
            return data

    method: Literal["call_handler"]
    params: Params | dict = Field(default_factory=dict)


class HandlerStreamStartNotification(JSONRPCRequest):
    """Notification sent when a handler stream starts."""
    
    class Params(BaseModel):
        id: str | None  # The original request ID
        handler_full_name: str
    
    method: Literal["handler_stream_start"] = "handler_stream_start"
    params: Params  # type: ignore[assignment]


class HandlerStreamUpdateNotification(JSONRPCRequest):
    """Notification sent when a handler stream has new data."""
    
    class Params(BaseModel):
        id: str | None  # The original request ID
        handler_full_name: str
        data: Any  # The streamed data
    
    method: Literal["handler_stream_update"] = "handler_stream_update"
    params: Params  # type: ignore[assignment]


class HandlerStreamEndNotification(JSONRPCRequest):
    """Notification sent when a handler stream ends."""
    
    class Params(BaseModel):
        id: str | None  # The original request ID
        handler_full_name: str
    
    method: Literal["handler_stream_end"] = "handler_stream_end"
    params: Params  # type: ignore[assignment]
