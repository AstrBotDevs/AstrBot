from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _JSONRPCBaseMessage(BaseModel):
    jsonrpc: Literal["2.0"]

    model_config = ConfigDict(extra="forbid")


class JSONRPCRequest(_JSONRPCBaseMessage):
    id: str | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    """A request that expects a response."""


class _Result(_JSONRPCBaseMessage):
    id: str | None


class JSONRPCSuccessResponse(_Result):
    result: dict[str, Any] = Field(default_factory=dict)
    """A successful response to a request."""


class JSONRPCErrorData(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JSONRPCErrorResponse(_Result):
    error: JSONRPCErrorData
    """An error response to a request."""


JSONRPCMessage = JSONRPCRequest | JSONRPCSuccessResponse | JSONRPCErrorResponse
