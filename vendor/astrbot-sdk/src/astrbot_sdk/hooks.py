from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .messages import MessageChain
from .protocol.codec import encode_message_chain, encode_value
from .protocol_registry import register_protocol_dataclass
from .registration import hooks as _decorators

llm_request = _decorators.llm_request
llm_response = _decorators.llm_response
tool_call = _decorators.tool_call
tool_result = _decorators.tool_result
message_result = _decorators.message_result
message_sent = _decorators.message_sent
agent_start = _decorators.agent_start
agent_end = _decorators.agent_end
waiting_llm_request = _decorators.waiting_llm_request
plugin_error = _decorators.plugin_error
plugin_loaded = _decorators.plugin_loaded
plugin_unloaded = _decorators.plugin_unloaded


class HookWriteError(AttributeError):
    """Raised when a hook writes an undeclared DTO field."""


def _encode_item(value: Any) -> Any:
    """Encode one tracked value; message segments use the chain codec."""
    from .message_components import MessageSegment

    if isinstance(value, MessageSegment):
        # Hook chains are pass-through state; inbound unknown segments must
        # round-trip through write ops unchanged.
        return encode_message_chain(MessageChain(value), allow_unknown=True)[0]
    return encode_value(value)


class TrackedList(list):
    """List that records mutation operations for Host-side application."""

    def __init__(self, field: str, values: Any, ops: list[dict]) -> None:
        super().__init__(values or [])
        self._field = field
        self._ops = ops

    def append(self, value: Any) -> None:
        super().append(value)
        self._ops.append(
            {"field": self._field, "op": "append", "value": _encode_item(value)},
        )

    def extend(self, values: Any) -> None:
        values = list(values)
        super().extend(values)
        self._ops.append(
            {
                "field": self._field,
                "op": "extend",
                "value": [_encode_item(item) for item in values],
            },
        )

    def clear(self) -> None:
        super().clear()
        self._ops.append({"field": self._field, "op": "clear"})

    def _replace(self, values: Any) -> None:
        super().clear()
        super().extend(values)
        self._ops.append(
            {
                "field": self._field,
                "op": "set",
                "value": [_encode_item(item) for item in self],
            },
        )

    def __setitem__(self, index: Any, value: Any) -> None:
        super().__setitem__(index, value)
        self._replace(list(self))

    def __delitem__(self, index: Any) -> None:
        super().__delitem__(index)
        self._replace(list(self))

    def insert(self, index: int, value: Any) -> None:
        super().insert(index, value)
        self._replace(list(self))

    def pop(self, index: int = -1) -> Any:
        value = super().pop(index)
        self._replace(list(self))
        return value

    def remove(self, value: Any) -> None:
        super().remove(value)
        self._replace(list(self))


class HookDTO:
    """Mutable hook-stage DTO recording field writes.

    Plugins mutate fields directly, mirroring the legacy in-place hook style.
    The Runner forwards recorded operations to the Host after the handler
    returns. Undeclared fields fail fast with AttributeError.
    """

    _fields: ClassVar[frozenset[str]]
    _list_fields: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, **values: Any) -> None:
        ops: list[dict] = []
        object.__setattr__(self, "_ops", ops)
        object.__setattr__(self, "_values", dict(values))

    def __getattr__(self, name: str) -> Any:
        try:
            return object.__getattribute__(self, "_values")[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        if name not in self._fields:
            raise HookWriteError(
                f"{type(self).__name__} has no writable field {name!r}"
            )
        values = object.__getattribute__(self, "_values")
        ops = object.__getattribute__(self, "_ops")
        if name in self._list_fields:
            if not isinstance(value, TrackedList):
                value = TrackedList(name, value, ops)
            # List fields may hold message segments, which only the chain
            # codec can encode.
            encoded = [_encode_item(item) for item in value]
        else:
            encoded = encode_value(value)
        values[name] = value
        ops.append({"field": name, "op": "set", "value": encoded})

    def _init_lists(self) -> None:
        values = object.__getattribute__(self, "_values")
        ops = object.__getattribute__(self, "_ops")
        for name in self._list_fields:
            values[name] = TrackedList(name, values.get(name), ops)

    def _write_ops(self) -> list[dict]:
        return object.__getattribute__(self, "_ops")


class LLMRequest(HookDTO):
    """Mutable view of an outgoing LLM request for hooks."""

    _fields = frozenset(
        {
            "prompt",
            "system_prompt",
            "contexts",
            "image_urls",
            "audio_urls",
            "model",
        },
    )
    _list_fields = frozenset({"contexts", "image_urls", "audio_urls"})


class LLMResponse(HookDTO):
    """Mutable view of an LLM response for hooks."""

    _fields = frozenset({"content", "reasoning_content"})


class ToolCall(HookDTO):
    """Mutable view of a pending tool call for hooks."""

    _fields = frozenset({"args"})


class ToolResult(HookDTO):
    """Mutable view of a completed tool call for hooks."""

    _fields = frozenset({"content"})


class MessageResult(HookDTO):
    """Mutable view of an outbound message result for hooks."""

    _fields = frozenset({"chain"})
    _list_fields = frozenset({"chain"})


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class PluginError:
    """Details of a plugin handler failure (observe-only hook payload)."""

    plugin_name: str
    handler_name: str
    error: str
    traceback: str


def build_stage_dto(stage: str, payload: Any) -> Any:
    """Build the stage DTO for one hook stage from its snapshot payload.

    Tracked (mutable) stages return HookDTO; observe stages return a frozen
    DTO or None.
    """
    payload = dict(payload or {})
    if stage == "llm_request":
        dto: Any = LLMRequest(**payload)
    elif stage == "llm_response":
        dto = LLMResponse(**payload)
    elif stage == "tool_call":
        dto = ToolCall(**payload)
    elif stage == "tool_result":
        dto = ToolResult(**payload)
    elif stage == "message_result":
        dto = MessageResult(**payload)
    elif stage == "plugin_error":
        return PluginError(**payload)
    elif stage in {"plugin_loaded", "plugin_unloaded"}:
        from .context import PluginInfo

        return PluginInfo(**payload)
    else:
        return None
    dto._init_lists()
    return dto
