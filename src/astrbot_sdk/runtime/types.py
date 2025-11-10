from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from .rpc.jsonrpc import JSONRPCRequest
from typing import Any, Literal, Type
from ..api.event.astr_message_event import AstrMessageEvent, AstrMessageEventModel


# class StarType(enum.Enum):
#     LEGACY = "legacy"
#     STDIO = "stdio"
#     WEBSOCKET = "websocket"


# class StarURI(BaseModel):
#     star_type: StarType
#     namespace: str
#     plugin_name: str

#     def __str__(self):
#         return f"astrbot://{self.star_type.value}/{self.namespace}/{self.plugin_name}"

#     @classmethod
#     def from_str(cls, uri_str: str) -> StarURI:
#         """Parse a StarURI from a string."""
#         try:
#             prefix, rest = uri_str.split("://", 1)
#             star_type_str, namespace, plugin_name = rest.split("/", 2)
#             star_type = StarType(star_type_str)
#             return cls(
#                 star_type=star_type,
#                 namespace=namespace,
#                 plugin_name=plugin_name,
#             )
#         except Exception as e:
#             raise ValueError(f"Invalid StarURI format: {uri_str}") from e

#     def is_new_star(self) -> bool:
#         """Determine if the Star is a new-style Star (stdio or websocket)."""
#         return self.star_type in {StarType.STDIO, StarType.WEBSOCKET}


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
