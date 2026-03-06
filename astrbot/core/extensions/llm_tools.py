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
                "limit": {
                    "type": "integer",
                    "description": "Optional max number of results to return.",
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
                conversation_id=context.context.event.unified_msg_origin,
                requester_id=context.context.event.get_sender_id(),
                requester_role=context.context.event.role,
            )
        )
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
