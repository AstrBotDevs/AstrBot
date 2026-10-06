from __future__ import annotations

import logging
from typing import Any

from astrbot.core.star.star_handler import EventType

from .convert import to_core_chain, to_sdk_chain
from .services.assets import AssetStore

_LLM_STAGES = frozenset(
    {
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "agent_start",
        "agent_end",
    },
)

_METADATA_STAGES = frozenset({"plugin_loaded", "plugin_unloaded"})

_STAGE_EVENT_TYPES = {
    "llm_request": EventType.OnLLMRequestEvent,
    "llm_response": EventType.OnLLMResponseEvent,
    "tool_call": EventType.OnUsingLLMToolEvent,
    "tool_result": EventType.OnLLMToolRespondEvent,
    "message_result": EventType.OnDecoratingResultEvent,
    "message_sent": EventType.OnAfterMessageSentEvent,
    "agent_start": EventType.OnAgentBeginEvent,
    "agent_end": EventType.OnAgentDoneEvent,
    "waiting_llm_request": EventType.OnWaitingLLMRequestEvent,
    "plugin_error": EventType.OnPluginErrorEvent,
    "plugin_loaded": EventType.OnPluginLoadedEvent,
    "plugin_unloaded": EventType.OnPluginUnloadedEvent,
}


def stage_event_type(stage: str) -> EventType:
    """Map one SDK hook stage onto the core pipeline event type."""
    return _STAGE_EVENT_TYPES[stage]


def stage_modify_capability(stage: str) -> str:
    """Return the capability required to apply writes for one stage."""
    if stage in _LLM_STAGES:
        return "llm.modify"
    return "message.modify"


def is_metadata_stage(stage: str) -> bool:
    """Check whether the hook point passes StarMetadata instead of an event."""
    return stage in _METADATA_STAGES


def snapshot_stage(stage: str, event: Any, args: tuple) -> dict[str, Any]:
    """Build the stage DTO snapshot from the core hook arguments."""
    if stage == "llm_request":
        (req,) = args
        return {
            "prompt": req.prompt,
            "system_prompt": req.system_prompt,
            "contexts": list(req.contexts or []),
            "image_urls": list(req.image_urls or []),
            "audio_urls": list(req.audio_urls or []),
            "model": req.model,
        }
    if stage == "llm_response":
        (resp,) = args
        return {
            "content": resp.completion_text,
            "reasoning_content": resp.reasoning_content,
        }
    if stage == "tool_call":
        tool, tool_args = args
        return {
            "args": dict(tool_args or {}),
            "name": getattr(tool, "name", "") or "",
            "description": getattr(tool, "description", "") or "",
        }
    if stage == "tool_result":
        tool, tool_args, tool_result = args
        return {
            "content": _tool_result_text(tool_result),
            "name": getattr(tool, "name", "") or "",
            "description": getattr(tool, "description", "") or "",
            "args": dict(tool_args or {}),
        }
    if stage == "message_result":
        result = event.get_result()
        return {"chain": to_sdk_chain(result.chain if result else [])}
    if stage == "plugin_error":
        plugin_name, handler_name, error, tb = args
        return {
            "plugin_name": str(plugin_name),
            "handler_name": str(handler_name),
            "error": str(error),
            "traceback": str(tb),
        }
    if stage in _METADATA_STAGES:
        (metadata,) = args
        return {
            "id": metadata.plugin_id,
            "name": metadata.name or "",
            "version": metadata.version or "",
            "runtime_mode": "in_process",
            "author": metadata.author,
            "desc": metadata.desc,
            "activated": metadata.activated,
        }
    return {}


def _tool_result_text(tool_result: Any) -> str:
    """Extract plain text from a CallToolResult."""
    if tool_result is None:
        return ""
    content = getattr(tool_result, "content", None) or []
    return "".join(
        getattr(part, "text", "") for part in content if getattr(part, "text", None)
    )


def apply_hook_result(
    stage: str,
    event: Any,
    args: tuple,
    result: dict[str, Any],
    *,
    grants: Any,
    store: AssetStore | None,
    logger: logging.Logger,
) -> None:
    """Apply hook write ops and decisions back onto core objects.

    Writes are only applied when the plugin holds the stage's modify
    capability; otherwise they are dropped with a warning, matching the
    plugin-unaware authorization model.
    """
    writes = result.get("writes") or []
    if not writes:
        return

    capability = stage_modify_capability(stage)
    if not grants.has(capability):
        logger.warning(
            f"hook writes dropped for stage {stage}: {capability} not granted",
        )
        return

    for op in writes:
        _apply_write(stage, event, args, op, store)


def _apply_write(
    stage: str,
    event: Any,
    args: tuple,
    op: dict[str, Any],
    store: AssetStore | None,
) -> None:
    """Apply one recorded write operation to the core stage object."""
    field = op["field"]
    if stage == "llm_request":
        (req,) = args
        _apply_field(req, field, op)
    elif stage == "llm_response":
        (resp,) = args
        if field == "content":
            resp.completion_text = op["value"]
        elif field == "reasoning_content":
            resp.reasoning_content = op["value"]
    elif stage == "tool_call":
        _tool, tool_args = args
        if field == "args" and op["op"] == "set" and tool_args is not None:
            tool_args.clear()
            tool_args.update(op["value"])
    elif stage == "tool_result":
        _tool, _tool_args, tool_result = args
        if field == "content" and tool_result is not None:
            import mcp.types

            tool_result.content = [
                mcp.types.TextContent(type="text", text=str(op["value"])),
            ]
    elif stage == "message_result":
        result = event.get_result()
        if field == "chain" and result is not None:
            chain = _ops_to_chain(result.chain, op, store)
            result.chain = chain


def _apply_field(target: Any, field: str, op: dict[str, Any]) -> None:
    """Apply one write op to a plain-object field (set/list operations)."""
    name = op["op"]
    if name == "set" and field not in {"contexts", "image_urls", "audio_urls"}:
        setattr(target, field, op["value"])
        return
    current = getattr(target, field, None)
    if current is None:
        current = []
        setattr(target, field, current)
    if name == "append":
        current.append(op["value"])
    elif name == "extend":
        current.extend(op["value"])
    elif name == "clear":
        current.clear()
    elif name == "set":
        setattr(target, field, list(op["value"]))


def _ops_to_chain(current: list, op: dict[str, Any], store: AssetStore | None) -> list:
    """Apply one chain write op to a core result chain."""
    from astrbot_sdk.protocol.codec import decode_value

    name = op["op"]
    if name == "append":
        chain = to_core_chain(
            decode_value({"$type": "MessageChain", "value": [op["value"]]}),
            resolve_asset=store.resolve if store else None,
        )
        return current + chain
    if name == "extend":
        chain = to_core_chain(
            decode_value({"$type": "MessageChain", "value": op["value"]}),
            resolve_asset=store.resolve if store else None,
        )
        return current + chain
    if name == "clear":
        return []
    if name == "set":
        return to_core_chain(
            decode_value({"$type": "MessageChain", "value": op["value"]}),
            resolve_asset=store.resolve if store else None,
        )
    return current
