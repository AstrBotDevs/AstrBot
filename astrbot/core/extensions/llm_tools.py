from __future__ import annotations

import json

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.tools.permissions import check_admin_permission

from .model import ExtensionKind, InstallRequest
from .runtime import get_extension_orchestrator


def _json_result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _parse_kind(kind: str) -> ExtensionKind:
    return ExtensionKind(str(kind).strip().lower())


@dataclass
class ExtensionSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "astrbot_extension_search"
    description: str = "Search extension candidates (plugin/skill/mcp) for on-demand capability expansion."
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

        orchestrator = get_extension_orchestrator(context.context.context)
        candidates = await orchestrator.search(
            kind=kind,
            query=query,
            provider=str(kwargs.get("provider", "")).strip(),
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
        "Install plugin/skill extensions with policy enforcement and confirmation flow."
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
                requester_id=context.context.event.get_sender_id(),
                requester_role=context.context.event.role,
            )
        )
        return _json_result(
            {
                "status": result.status.value,
                "message": result.message,
                "operation_id": result.operation_id,
                "token": result.token,
                "data": result.data,
            }
        )


@dataclass
class ExtensionConfirmTool(FunctionTool[AstrAgentContext]):
    name: str = "astrbot_extension_confirm"
    description: str = "Confirm a pending extension installation operation."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "operation_id_or_token": {
                    "type": "string",
                    "description": "Pending operation id or one-time token.",
                }
            },
            "required": ["operation_id_or_token"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        denied = check_admin_permission(context, "extension confirmation")
        if denied:
            return denied
        operation_id_or_token = str(kwargs.get("operation_id_or_token", "")).strip()
        if not operation_id_or_token:
            return "error: operation_id_or_token cannot be empty."
        orchestrator = get_extension_orchestrator(context.context.context)
        result = await orchestrator.confirm(
            operation_id_or_token=operation_id_or_token,
            actor_id=context.context.event.get_sender_id(),
            actor_role=context.context.event.role,
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
class ExtensionDenyTool(FunctionTool[AstrAgentContext]):
    name: str = "astrbot_extension_deny"
    description: str = "Reject a pending extension installation operation."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "operation_id_or_token": {
                    "type": "string",
                    "description": "Pending operation id or one-time token.",
                }
            },
            "required": ["operation_id_or_token"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        denied = check_admin_permission(context, "extension rejection")
        if denied:
            return denied
        operation_id_or_token = str(kwargs.get("operation_id_or_token", "")).strip()
        if not operation_id_or_token:
            return "error: operation_id_or_token cannot be empty."
        orchestrator = get_extension_orchestrator(context.context.context)
        result = await orchestrator.deny(
            operation_id_or_token=operation_id_or_token,
            actor_role=context.context.event.role,
            reason="rejected by LLM tool",
        )
        return _json_result(
            {
                "status": result.status.value,
                "message": result.message,
                "operation_id": result.operation_id,
            }
        )


EXTENSION_SEARCH_TOOL = ExtensionSearchTool()
EXTENSION_INSTALL_TOOL = ExtensionInstallTool()
EXTENSION_CONFIRM_TOOL = ExtensionConfirmTool()
EXTENSION_DENY_TOOL = ExtensionDenyTool()
