from __future__ import annotations

import json

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.tools.permissions import check_admin_permission

from .model import ExtensionKind, InstallRequest, InstallResultStatus
from .runtime import get_extension_orchestrator


def _json_result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _parse_kind(kind: str) -> ExtensionKind:
    return ExtensionKind(str(kind).strip().lower())


@dataclass
class ExtensionSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "astrbot_extension_search"
    description: str = (
        "Search extension candidates (plugin/skill/mcp) for on-demand capability "
        "expansion. The bot may choose the optional limit to widen or narrow the "
        "search result set."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keywords."},
                "kind": {
                    "type": "string",
                    "description": "Extension kind: plugin, skill, mcp.",
                },
                "provider": {
                    "type": "string",
                    "description": "Optional provider filter.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional max number of results to return. The bot may choose this based on how broad the search should be.",
                    "minimum": 1,
                },
            },
            "required": ["query", "kind"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        denied = check_admin_permission(context, "extension search")
        if denied:
            return denied
        query = str(kwargs.get("query", "")).strip()
        if not query:
            return "error: query cannot be empty."
        try:
            kind = _parse_kind(str(kwargs.get("kind", "")))
        except ValueError:
            return "error: kind must be one of plugin|skill|mcp."
        raw_limit = kwargs.get("limit")
        limit: int | None = None
        if raw_limit is not None:
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                return "error: limit must be a positive integer."
            if limit <= 0:
                return "error: limit must be a positive integer."

        orchestrator = get_extension_orchestrator(context.context.context)
        candidates = await orchestrator.search(
            kind=kind,
            query=query,
            provider=str(kwargs.get("provider", "")).strip(),
            limit=limit,
        )
        return _json_result(
            {
                "status": "ok",
                "count": len(candidates),
                "items": [
                    {
                        "kind": c.kind.value,
                        "provider": c.provider,
                        "identifier": c.identifier,
                        "name": c.name,
                        "description": c.description,
                        "version": c.version,
                        "source": c.source,
                    }
                    for c in candidates
                ],
            }
        )


@dataclass
class ExtensionInstallTool(FunctionTool[AstrAgentContext]):
    name: str = "astrbot_extension_install"
    description: str = (
        "Install plugin/skill extensions with policy enforcement and confirmation flow. "
        "When the result status is 'pending', you MUST clearly tell the user which "
        "extension is about to be installed (name and description) and ask them to "
        "reply with a confirmation or rejection in natural language. "
        "Do NOT show the raw operation_id to the user."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": "Extension kind: plugin, skill, mcp.",
                },
                "target": {
                    "type": "string",
                    "description": "Target identifier, repository URL, local zip path, or locator.",
                },
                "provider": {
                    "type": "string",
                    "description": "Optional provider name.",
                },
            },
            "required": ["kind", "target"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        denied = check_admin_permission(context, "extension install")
        if denied:
            return denied
        try:
            kind = _parse_kind(str(kwargs.get("kind", "")))
        except ValueError:
            return "error: kind must be one of plugin|skill|mcp."
        target = str(kwargs.get("target", "")).strip()
        if not target:
            return "error: target cannot be empty."
        provider = str(kwargs.get("provider", "")).strip()
        orchestrator = get_extension_orchestrator(context.context.context)
        result = await orchestrator.install(
            InstallRequest(
                kind=kind,
                target=target,
                provider=provider,
                conversation_id=context.context.event.unified_msg_origin,
                requester_id=context.context.event.get_sender_id(),
                requester_role=context.context.event.role,
            )
        )
        payload: dict = {
            "status": result.status.value,
            "message": result.message,
            "operation_id": result.operation_id,
            "data": result.data,
        }
        if result.status == InstallResultStatus.PENDING:
            payload["hint"] = (
                "Tell the user which extension is about to be installed "
                "(use candidate_name and candidate_description) and ask "
                "them to confirm or reject in natural language."
            )
            payload["candidate_name"] = result.data.get("candidate_name", "")
            payload["candidate_description"] = result.data.get(
                "candidate_description", ""
            )
        return _json_result(payload)


@dataclass
class ExtensionDenyTool(FunctionTool[AstrAgentContext]):
    name: str = "astrbot_extension_deny"
    description: str = (
        "Reject a pending extension install request. This can reject a single "
        "operation by operation_id or reject all pending installs in the current "
        "conversation when no operation_id is provided."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "operation_id": {
                    "type": "string",
                    "description": "Optional operation_id for rejecting a single pending install.",
                }
            },
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        orchestrator = get_extension_orchestrator(context.context.context)
        operation_id = str(kwargs.get("operation_id", "")).strip()
        if operation_id:
            result = await orchestrator.deny(
                operation_id_or_token=operation_id,
                actor_id=context.context.event.get_sender_id(),
                actor_role=context.context.event.role,
                reason="rejected by agent",
            )
        else:
            result = await orchestrator.deny_for_conversation(
                conversation_id=context.context.event.unified_msg_origin,
                actor_id=context.context.event.get_sender_id(),
                actor_role=context.context.event.role,
                reason="rejected by agent",
            )
        return _json_result(
            {
                "status": result.status.value,
                "message": result.message,
                "operation_id": result.operation_id,
                "data": result.data,
            }
        )


@dataclass
class ExtensionDenyAllTool(FunctionTool[AstrAgentContext]):
    name: str = "astrbot_extension_deny_all"
    description: str = (
        "Reject multiple pending extension install requests. Use scope=conversation "
        "to clear the current conversation, or scope=all to clear every pending "
        "install the actor is allowed to reject."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "Reject scope: conversation or all.",
                    "enum": ["conversation", "all"],
                },
                "kind": {
                    "type": "string",
                    "description": "Optional kind filter for global rejection: plugin, skill, mcp.",
                },
            },
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        orchestrator = get_extension_orchestrator(context.context.context)
        scope = (
            str(kwargs.get("scope", "conversation")).strip().lower() or "conversation"
        )
        kind: ExtensionKind | None = None
        raw_kind = str(kwargs.get("kind", "")).strip()
        if raw_kind:
            try:
                kind = _parse_kind(raw_kind)
            except ValueError:
                return "error: kind must be one of plugin|skill|mcp."
        if scope == "all":
            result = await orchestrator.deny_all(
                actor_id=context.context.event.get_sender_id(),
                actor_role=context.context.event.role,
                kind=kind,
                reason="rejected by agent",
            )
        elif scope == "conversation":
            result = await orchestrator.deny_for_conversation(
                conversation_id=context.context.event.unified_msg_origin,
                actor_id=context.context.event.get_sender_id(),
                actor_role=context.context.event.role,
                reason="rejected by agent",
            )
        else:
            return "error: scope must be one of conversation|all."
        return _json_result(
            {
                "status": result.status.value,
                "message": result.message,
                "operation_id": result.operation_id,
                "data": result.data,
            }
        )


EXTENSION_SEARCH_TOOL = ExtensionSearchTool()
EXTENSION_INSTALL_TOOL = ExtensionInstallTool()
EXTENSION_DENY_TOOL = ExtensionDenyTool()
EXTENSION_DENY_ALL_TOOL = ExtensionDenyAllTool()
