"""
Extension Hub LLM 工具模块

本模块提供了 AI 代理可调用的扩展管理工具，包括:

工具列表:
- ExtensionSearchTool: 搜索可用扩展
- ExtensionInstallTool: 安装扩展（支持确认流程）
- ExtensionDenyTool: 拒绝单个或会话级别的挂起安装
- ExtensionDenyAllTool: 批量拒绝挂起安装

设计要点:
1. 工具描述中包含 AI 使用指南，指导如何处理 PENDING 状态
2. 安装结果包含 candidate_name/description 供 AI 展示给用户
3. deny 工具支持灵活的拒绝范围（单个/会话/全局）

相关提交:
- 350fdf13: Extension Hub v1 初始实现
- e64503cf: 会话级别确认工作流
- ef0bc377: 新增 deny 和 deny_all 工具
"""

from __future__ import annotations

import json

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.tools.permissions import check_admin_permission

from .model import ExtensionKind, InstallRequest, InstallResultStatus
from .runtime import get_extension_confirm_keywords, get_extension_orchestrator


def _json_result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _parse_kind(kind: str) -> ExtensionKind:
    return ExtensionKind(str(kind).strip().lower())


@dataclass
class ExtensionSearchTool(FunctionTool[AstrAgentContext]):
    """扩展搜索工具

    供 AI 代理搜索可用的扩展（插件/技能/MCP）。

    参数:
        query: 搜索关键词
        kind: 扩展类型 (plugin/skill/mcp)
        provider: 可选的提供者过滤
        limit: 可选的结果数量限制，AI 可根据搜索广度选择
    """

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

        umo = context.context.event.unified_msg_origin
        orchestrator = get_extension_orchestrator(context.context.context, umo=umo)
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
    """扩展安装工具

    供 AI 代理发起扩展安装请求。根据策略配置，可能需要用户确认。

    工作流程:
    1. AI 调用此工具发起安装
    2. 若返回 PENDING 状态，AI 必须告知用户扩展名称和描述
    3. 用户通过自然语言确认或拒绝
    4. AI 调用 deny 工具或等待确认结果

    重要: 当状态为 PENDING 时，AI 不应向用户展示原始 operation_id，
    而应使用 candidate_name 和 candidate_description 展示友好信息。
    """

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
        umo = context.context.event.unified_msg_origin
        orchestrator = get_extension_orchestrator(context.context.context, umo=umo)
        result = await orchestrator.install(
            InstallRequest(
                kind=kind,
                target=target,
                provider=provider,
                conversation_id=umo,
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
            confirm_keyword, deny_keyword = get_extension_confirm_keywords(
                context.context.context.get_config(umo=umo)
            )
            payload["hint"] = (
                "Tell the user which extension is about to be installed "
                "(use candidate_name and candidate_description) and ask "
                f"them to reply with the configured confirmation keyword "
                f"'{confirm_keyword}' or rejection keyword '{deny_keyword}'."
            )
            payload["candidate_name"] = result.data.get("candidate_name", "")
            payload["candidate_description"] = result.data.get(
                "candidate_description", ""
            )
            payload["confirm_keyword"] = confirm_keyword
            payload["deny_keyword"] = deny_keyword
        return _json_result(payload)


@dataclass
class ExtensionDenyTool(FunctionTool[AstrAgentContext]):
    """扩展拒绝工具

    供 AI 代理拒绝挂起的安装请求。

    使用场景:
    - 用户明确表示"不要安装"、"取消"等拒绝意图
    - AI 判断安装请求不合适

    行为:
    - 提供 operation_id: 拒绝指定操作
    - 不提供 operation_id: 拒绝当前会话中的所有挂起操作
    """

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
        orchestrator = get_extension_orchestrator(
            context.context.context,
            umo=context.context.event.unified_msg_origin,
        )
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
    """批量拒绝工具

    供 AI 代理批量拒绝挂起的安装请求。

    参数:
        scope: 拒绝范围
            - "conversation": 仅当前会话
            - "all": 全局所有挂起操作
        kind: 可选的扩展类型过滤
    """

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
        orchestrator = get_extension_orchestrator(
            context.context.context,
            umo=context.context.event.unified_msg_origin,
        )
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
