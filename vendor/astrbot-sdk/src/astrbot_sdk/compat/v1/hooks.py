"""Legacy hook facades: adapt old hook signatures onto tracked stage DTOs."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from ...hooks import HookDTO, build_stage_dto
from ...protocol.codec import decode_message_chain
from ...registration import HandlerKind
from .components import (
    MessageChain,
    MessageEventResult,
    from_sdk_segment,
    to_sdk_segment,
)
from .event import AstrMessageEvent
from .platform_events import build_legacy_event

# Legacy filter-decorator stage -> new hook HandlerKind.
HOOK_STAGE_KINDS: dict[str, HandlerKind] = {
    "llm_request": HandlerKind.HOOK_LLM_REQUEST,
    "llm_response": HandlerKind.HOOK_LLM_RESPONSE,
    "tool_call": HandlerKind.HOOK_TOOL_CALL,
    "tool_result": HandlerKind.HOOK_TOOL_RESULT,
    "message_result": HandlerKind.HOOK_MESSAGE_RESULT,
    "message_sent": HandlerKind.HOOK_MESSAGE_SENT,
    "agent_start": HandlerKind.HOOK_AGENT_START,
    "agent_end": HandlerKind.HOOK_AGENT_END,
    "waiting_llm_request": HandlerKind.HOOK_WAITING_LLM_REQUEST,
    "plugin_error": HandlerKind.HOOK_PLUGIN_ERROR,
    "plugin_loaded": HandlerKind.HOOK_PLUGIN_LOADED,
    "plugin_unloaded": HandlerKind.HOOK_PLUGIN_UNLOADED,
}

_LLM_REQUEST_FIELDS = frozenset(
    {"prompt", "system_prompt", "contexts", "image_urls", "audio_urls", "model"},
)


class _HookProviderRequest:
    """Legacy ProviderRequest facade writing through to the tracked DTO."""

    def __init__(self, dto: HookDTO) -> None:
        object.__setattr__(self, "_dto", dto)
        object.__setattr__(self, "_local", {"func_tool": None, "conversation": None})

    def __getattr__(self, name: str) -> Any:
        if name in _LLM_REQUEST_FIELDS:
            return getattr(object.__getattribute__(self, "_dto"), name)
        return object.__getattribute__(self, "_local").get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _LLM_REQUEST_FIELDS:
            setattr(object.__getattribute__(self, "_dto"), name, value)
        else:
            object.__getattribute__(self, "_local")[name] = value


class _HookLLMResponse:
    """Legacy LLMResponse facade writing through to the tracked DTO."""

    def __init__(self, dto: HookDTO) -> None:
        object.__setattr__(self, "_dto", dto)
        object.__setattr__(self, "_local", {"role": "assistant", "result_chain": None})

    def __getattr__(self, name: str) -> Any:
        if name == "completion_text":
            return getattr(object.__getattribute__(self, "_dto"), "content")
        if name == "reasoning_content":
            return getattr(object.__getattribute__(self, "_dto"), "reasoning_content")
        return object.__getattribute__(self, "_local").get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "completion_text":
            setattr(object.__getattribute__(self, "_dto"), "content", value)
        elif name == "reasoning_content":
            setattr(object.__getattribute__(self, "_dto"), "reasoning_content", value)
        else:
            object.__getattribute__(self, "_local")[name] = value


def _tool_namespace(payload: dict[str, Any]) -> SimpleNamespace:
    """Build the legacy FunctionTool-shaped object for tool hooks."""
    return SimpleNamespace(
        name=payload.get("name", ""),
        description=payload.get("description", ""),
        parameters=payload.get("parameters", {}),
    )


async def invoke_compat_hook(
    plugin: Any,
    method: Any,
    stage: str,
    event: Any,
    stage_payload: dict[str, Any],
) -> dict[str, Any]:
    """Invoke one legacy hook handler against a tracked stage DTO.

    The legacy facade writes through to the tracked DTO where the stage
    supports modification; recorded write ops are returned for the Host.
    """
    from ...events import MessageEvent

    payload = dict(stage_payload or {})
    dto = (
        build_stage_dto(stage, payload) if not stage.startswith("lifecycle.") else None
    )
    context = plugin.context

    facade_event: AstrMessageEvent | None = None
    if isinstance(event, MessageEvent):
        facade_event = build_legacy_event(event, context)

    args: list[Any] = []
    if stage == "llm_request":
        args = [facade_event, _HookProviderRequest(dto)]
    elif stage == "llm_response":
        args = [facade_event, _HookLLMResponse(dto)]
    elif stage == "message_result":
        if facade_event is not None and dto is not None:
            result = MessageEventResult()
            # A plain list of compat components, exactly like the in-process
            # chain: isinstance(list) checks and in-place edits both work.
            # The whole chain is copied back after the hook (see below).
            # The chain arrives as SDK segments when the payload crossed the
            # wire as a MessageChain envelope, or as raw segment dicts when
            # the host passed plain JSON; normalize both to SDK segments.
            raw_items = list(dto.chain)
            wire_items = [item for item in raw_items if isinstance(item, Mapping)]
            sdk_items = (
                list(decode_message_chain(wire_items))
                if len(wire_items) == len(raw_items)
                else raw_items
            )
            result.chain = [from_sdk_segment(segment) for segment in sdk_items]
            facade_event.set_result(result)
        args = [facade_event]
    elif stage == "tool_call":
        args = [facade_event, _tool_namespace(payload), getattr(dto, "args", {})]
    elif stage == "tool_result":
        args = [
            facade_event,
            _tool_namespace(payload),
            payload.get("args", {}),
            getattr(dto, "content", None),
        ]
    elif stage == "agent_start":
        args = [facade_event, SimpleNamespace(**payload)]
    elif stage == "agent_end":
        args = [
            facade_event,
            SimpleNamespace(**payload),
            _HookLLMResponse(dto) if dto is not None else None,
        ]
    elif stage == "plugin_error":
        error = dto
        args = [
            facade_event,
            getattr(error, "plugin_name", ""),
            getattr(error, "handler_name", ""),
            getattr(error, "error", ""),
            getattr(error, "traceback", ""),
        ]
    elif stage in {"plugin_loaded", "plugin_unloaded"}:
        args = [dto]
    elif stage in {"message_sent", "waiting_llm_request"}:
        args = [facade_event]
    elif stage.startswith("lifecycle."):
        args = []
    else:
        raise ValueError(f"unsupported legacy hook stage: {stage}")

    outcome = method(*args)
    if inspect.isasyncgen(outcome):
        await outcome.aclose()
        raise ValueError("legacy hook handler cannot yield results")
    await outcome

    # Copy the (possibly mutated or replaced) result chain back. The plugin
    # received a plain list, so every mutation form lands in that list.
    if stage == "message_result" and facade_event is not None and dto is not None:
        result = facade_event.get_result()
        if result is not None and result.chain is not None:
            chain = result.chain
            if isinstance(chain, MessageChain):
                chain = chain.chain
            dto.chain = [to_sdk_segment(c) for c in chain]

    return {
        "writes": dto._write_ops() if isinstance(dto, HookDTO) else [],
    }
