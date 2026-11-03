"""Thin LLM tools over the runtime-independent agent-session API."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_runtime.tools.registry import builtin_tool
from astrbot.core.subagents.messages import SUBAGENT_MESSAGES_SCHEMA

if TYPE_CHECKING:
    from astrbot.core.agent.run_context import ContextWrapper
    from astrbot.core.subagents.context import SubAgentContext
    from astrbot.core.subagents.service import SubAgentService


SUBAGENT_TOOL_NAMES = frozenset(
    {
        "spawn_agent",
        "list_agents",
        "wait_agent",
        "get_agent_result",
        "send_message",
        "cancel_agent",
    }
)
_HANDLER_MODULE = "astrbot.core.astr_agent_runtime.main_agent.subagent"


def get_subagent_service(context: ContextWrapper[SubAgentContext]) -> SubAgentService:
    """Resolve the application's session API without exposing runtime implementations.

    Args:
        context: Bound main-agent tool context.

    Returns:
        Initialized agent-session service.

    Raises:
        ValueError: If application subagents have not been initialized.
    """
    service = context.context.context.subagents
    if service is None:
        raise ValueError("Subagent service is not initialized")
    return service


@builtin_tool(config={"subagent_orchestrator.main_enable": True})
class SpawnAgentTool(FunctionTool):
    name = "spawn_agent"

    def __init__(self) -> None:
        super().__init__(
            name="spawn_agent",
            description=(
                "Open an agent session and return its agent_id while the task runs asynchronously. "
                "Provide a self-contained task and explicit attachments in messages; main history and original attachments are not inherited. "
                "Omit template for a generic worker or choose an expert from the system instructions. "
                "Omit runtime for the built-in AstrBot agent runtime. Optionally override name or native provider_id. "
                "Continue independent work; use wait_agent for results, send_message for follow-ups, and cancel_agent to stop work."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "messages": copy.deepcopy(SUBAGENT_MESSAGES_SCHEMA),
                    "template": {
                        "type": "string",
                        "description": "Optional configured expert name; omit for a generic agent.",
                    },
                    "runtime": {
                        "type": "string",
                        "description": "Agent runtime name from the system instructions. Defaults to astrbot.",
                    },
                    "name": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Optional agent display name.",
                    },
                    "provider_id": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Optional native configured chat provider ID; otherwise uses the expert or current conversation provider.",
                    },
                },
                "required": ["messages"],
                "additionalProperties": False,
            },
            handler_module_path=_HANDLER_MODULE,
        )

    async def call(
        self,
        context: ContextWrapper[SubAgentContext],
        messages: list[dict] | None = None,
        template: str | None = None,
        runtime: str = "astrbot",
        name: str | None = None,
        provider_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Create an agent session through its selected agent runtime.

        Args:
            context: Main execution owning the session.
            messages: Explicit structured task input.
            template: Optional expert name.
            runtime: Registered agent runtime name.
            name: Optional instance display name.
            provider_id: Optional native provider override.
            **kwargs: Unsupported arguments, rejected to match the tool schema.

        Returns:
            JSON public agent identity and initial state.
        """
        if messages is None or kwargs:
            raise TypeError(
                "spawn_agent requires messages and accepts only schema arguments"
            )
        return json.dumps(
            await get_subagent_service(context).spawn(
                context.context,
                messages,
                runtime=runtime,
                template=template,
                name=name,
                provider_id=provider_id,
            ),
            ensure_ascii=False,
        )


@builtin_tool(config={"subagent_orchestrator.main_enable": True})
class ListAgentsTool(FunctionTool):
    name = "list_agents"

    def __init__(self) -> None:
        super().__init__(
            name="list_agents",
            description="List your opened agents across turns in this conversation, including their IDs, agent runtimes, and states. Use wait_agent instead of repeatedly polling.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler_module_path=_HANDLER_MODULE,
        )

    async def call(
        self, context: ContextWrapper[SubAgentContext], **kwargs: Any
    ) -> str:
        if kwargs:
            raise TypeError("list_agents accepts no arguments")
        return json.dumps(
            {"agents": get_subagent_service(context).list(context.context)},
            ensure_ascii=False,
        )


@builtin_tool(config={"subagent_orchestrator.main_enable": True})
class GetAgentResultTool(FunctionTool):
    name = "get_agent_result"

    def __init__(self) -> None:
        super().__init__(
            name="get_agent_result",
            description="Read an agent's current state and final result by agent_id. Returns immediately; unfinished results are null. Results can be read repeatedly.",
            parameters={
                "type": "object",
                "properties": {"agent_id": {"type": "string", "minLength": 1}},
                "required": ["agent_id"],
                "additionalProperties": False,
            },
            handler_module_path=_HANDLER_MODULE,
        )

    async def call(
        self,
        context: ContextWrapper[SubAgentContext],
        agent_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        if agent_id is None or kwargs:
            raise TypeError("get_agent_result requires only agent_id")
        return json.dumps(
            await get_subagent_service(context).result(context.context, agent_id),
            ensure_ascii=False,
        )


@builtin_tool(config={"subagent_orchestrator.main_enable": True})
class WaitAgentTool(FunctionTool):
    name = "wait_agent"

    def __init__(self) -> None:
        super().__init__(
            name="wait_agent",
            execution_timeout=65,
            description="Wait for any or all selected agents to finish. timeout_ms only limits waiting; agents continue on timeout. Use 0 for an immediate status check.",
            parameters={
                "type": "object",
                "properties": {
                    "agent_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 60000,
                        "default": 30000,
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["any", "all"],
                        "default": "any",
                    },
                },
                "required": ["agent_ids"],
                "additionalProperties": False,
            },
            handler_module_path=_HANDLER_MODULE,
        )

    async def call(
        self,
        context: ContextWrapper[SubAgentContext],
        agent_ids: list[str] | None = None,
        timeout_ms: int = 30000,
        mode: str = "any",
        **kwargs: Any,
    ) -> str:
        if agent_ids is None or kwargs:
            raise TypeError(
                "wait_agent requires agent_ids and accepts only schema arguments"
            )
        return json.dumps(
            await get_subagent_service(context).wait(
                context.context, agent_ids, timeout_ms, mode
            ),
            ensure_ascii=False,
        )


@builtin_tool(config={"subagent_orchestrator.main_enable": True})
class SendAgentMessageTool(FunctionTool):
    name = "send_message"

    def __init__(self) -> None:
        super().__init__(
            name="send_message",
            description=(
                "Send structured input to an existing agent by agent_id. Returns immediately. "
                "Its agent runtime may merge input at a safe boundary or queue a new turn using the same conversation. "
                "Native running follow-ups are currently converted to text with attachment references."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "minLength": 1},
                    "messages": copy.deepcopy(SUBAGENT_MESSAGES_SCHEMA),
                },
                "required": ["agent_id", "messages"],
                "additionalProperties": False,
            },
            handler_module_path=_HANDLER_MODULE,
        )

    async def call(
        self,
        context: ContextWrapper[SubAgentContext],
        agent_id: str | None = None,
        messages: list[dict] | None = None,
        **kwargs: Any,
    ) -> str:
        if agent_id is None or messages is None or kwargs:
            raise TypeError("send_message requires agent_id and messages")
        return json.dumps(
            await get_subagent_service(context).send(
                context.context, agent_id, messages
            ),
            ensure_ascii=False,
        )


@builtin_tool(config={"subagent_orchestrator.main_enable": True})
class CancelAgentTool(FunctionTool):
    name = "cancel_agent"

    def __init__(self) -> None:
        super().__init__(
            name="cancel_agent",
            description="Cancel an agent's active and queued inputs without stopping main or other agents. Its conversation remains available for send_message.",
            parameters={
                "type": "object",
                "properties": {"agent_id": {"type": "string", "minLength": 1}},
                "required": ["agent_id"],
                "additionalProperties": False,
            },
            handler_module_path=_HANDLER_MODULE,
        )

    async def call(
        self,
        context: ContextWrapper[SubAgentContext],
        agent_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        if agent_id is None or kwargs:
            raise TypeError("cancel_agent requires only agent_id")
        return json.dumps(
            await get_subagent_service(context).cancel(context.context, agent_id),
            ensure_ascii=False,
        )
