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


class CallContextFunctionRequest(JSONRPCRequest):
    class Params(BaseModel):
        name: str
        args: dict[str, Any] = {}

    method: Literal["call_context_function"]
    params: Params | dict = Field(default_factory=dict)
