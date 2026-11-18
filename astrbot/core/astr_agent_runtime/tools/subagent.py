"""Thin LLM tools over the runtime-independent agent-session API."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_runtime.subagents.messages import SUBAGENT_MESSAGES_SCHEMA
from astrbot.core.astr_agent_runtime.tools.registry import builtin_tool

if TYPE_CHECKING:
    from astrbot.core.agent.run_context import ContextWrapper
    from astrbot.core.astr_agent_runtime.subagents.context import SubAgentContext
    from astrbot.core.astr_agent_runtime.subagents.service import SubAgentService


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
    from astrbot.core.astr_agent_runtime.runtime import AstrAgentRuntime

    runtime = context.context._runtime
    if not isinstance(runtime, AstrAgentRuntime):
        raise ValueError("Subagent service is not initialized")
    return runtime.subagents


@builtin_tool(config={"agent.config.subagents.enabled": True})
class SpawnAgentTool(FunctionTool):
    name = "spawn_agent"

    def __init__(self) -> None:
        super().__init__(
            name="spawn_agent",
            description=(
                "Open an agent session and return agent_id while the task runs asynchronously. "
                "Provide a self-contained task and explicit attachments in messages. "
                "Choose config_id from the system catalog or omit it for a generic native worker. "
                "Use wait_agent for results, send_message for follow-ups, and cancel_agent to stop work."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "messages": copy.deepcopy(SUBAGENT_MESSAGES_SCHEMA),
                    "config_id": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Optional reusable agent spec ID from the system catalog.",
                    },
                    "name": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Optional session display name.",
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
        config_id: str | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Resolve a native delegation choice and open its configured runtime.

        Args:
            context: Bound parent execution and permissions.
            messages: Self-contained structured input.
            config_id: Optional configured reusable agent.
            name: Optional session display name.
            **kwargs: Unsupported arguments, rejected to match the schema.

        Returns:
            JSON agent identity and initial state.

        Raises:
            ValueError: If delegation or the selected spec is unavailable.
            TypeError: If the tool input does not match its schema.
        """
        if messages is None or kwargs:
            raise TypeError(
                "spawn_agent requires messages and accepts only schema arguments"
            )
        from astrbot.core.astr_agent_runtime.runtime import AstrAgentRuntime

        native = context.context._runtime
        if not isinstance(native, AstrAgentRuntime):
            raise ValueError("AstrBot agent runtime is unavailable")
        return json.dumps(
            await native.spawn_agent(
                context.context, messages, config_id=config_id, name=name
            ),
            ensure_ascii=False,
        )


@builtin_tool(config={"agent.config.subagents.enabled": True})
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


@builtin_tool(config={"agent.config.subagents.enabled": True})
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


@builtin_tool(config={"agent.config.subagents.enabled": True})
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


@builtin_tool(config={"agent.config.subagents.enabled": True})
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


@builtin_tool(config={"agent.config.subagents.enabled": True})
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
