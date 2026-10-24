from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.tool import FunctionTool

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider

    from .context import AgentContextWrapper


@dataclass
class SubAgentTemplate:
    """Expert configuration without a separate callable tool."""

    agent: Agent
    description: str = ""
    provider_id: str | None = None


class SpawnAgentTool(FunctionTool):
    """Single delegation entry point for generic workers and expert templates."""

    def __init__(
        self,
        templates: list[SubAgentTemplate],
        providers: list[Provider] | None = None,
    ) -> None:
        catalog = [
            {"id": provider.provider_config["id"], "model": provider.get_model()}
            for provider in providers or []
        ]
        super().__init__(
            name="spawn_agent",
            description=(
                "Start a worker asynchronously and immediately return its agent_id. "
                "Delegate a clearly scoped task with all necessary context and expected output. "
                "Omit template for a generic worker using your available tools, or select "
                "a configured expert template. Workers do not inherit your chat history. "
                "Optionally name this worker and select a configured provider_id, "
                "overriding the expert template for this worker only. "
                "Continue independent work after submission. Use wait_agent when you need "
                "results before continuing, list_agents for status, and get_agent_result to read a result."
                " Use send_message for follow-up instructions and cancel_agent to stop a worker."
                + (
                    "\nAvailable expert templates:\n"
                    + "\n".join(
                        f"- {tool.agent.name}: {tool.description}" for tool in templates
                    )
                    if templates
                    else ""
                )
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Complete task and constraints.",
                    },
                    "template": {
                        "type": "string",
                        "description": "Optional expert template name; omit for a generic worker.",
                        **(
                            {"enum": [tool.agent.name for tool in templates]}
                            if templates
                            else {}
                        ),
                    },
                    "image_urls": {"type": "array", "items": {"type": "string"}},
                    "name": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Optional display name for this worker; defaults to the expert name or worker.",
                    },
                    "provider_id": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Optional configured chat provider ID, not a raw model name. "
                            "Overrides the expert provider; otherwise uses the expert or current conversation provider. "
                            + (
                                "Available chat providers (ID and model): "
                                + json.dumps(catalog, ensure_ascii=False)
                                if catalog
                                else "No chat providers are currently available; omit this parameter."
                            )
                        ),
                        **(
                            {"enum": [item["id"] for item in catalog]}
                            if catalog
                            else {}
                        ),
                    },
                },
                "required": ["task"],
                "additionalProperties": False,
            },
            handler_module_path=__package__ + ".main",
        )
        self.templates = list(templates)

    async def call(
        self,
        context: AgentContextWrapper,
        task: str,
        template: str | None = None,
        image_urls: list[str] | None = None,
        name: str | None = None,
        provider_id: str | None = None,
    ) -> str:
        """Start a worker without waiting for provider, image, or tool work.

        Args:
            context: Parent context bound by the plugin's lifecycle hook.
            task: Delegated instructions and expected output.
            template: Optional configured expert name.
            image_urls: Optional images for the worker.
            name: Optional instance display name without changing the expert.
            provider_id: Optional configured chat provider override for this worker.

        Returns:
            Worker identity, name, resolved provider, and initial state.
        """
        from .execution import SubAgentExecutor

        if not isinstance(task, str) or not task.strip():
            raise ValueError("spawn_agent requires a nonempty task")
        for field, value in (("name", name), ("provider_id", provider_id)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"spawn_agent {field} must be a nonempty string")
        root = context.context
        runtime = root.subagent_runtime
        if root.agent_id in runtime._instances:
            raise ValueError("Subagents cannot spawn further workers")
        if provider_id is not None:
            provider_id = provider_id.strip()
            available = [
                provider.provider_config["id"]
                for provider in root.context.get_all_providers()
            ]
            if provider_id not in available:
                raise ValueError(
                    f"Unknown or unavailable chat provider: {provider_id}. "
                    f"Available chat provider IDs: {json.dumps(available, ensure_ascii=False)}"
                )
        if template is None:
            selected = SubAgentTemplate(
                Agent(
                    name="worker",
                    instructions="Complete the delegated task. Follow its constraints and return a concise result with evidence and unresolved limitations.",
                    tools=[
                        tool
                        for tool in root.delegable_tools.tools
                        if tool.active and tool.name not in SUBAGENT_TOOL_NAMES
                    ],
                )
            )
        else:
            selected = next(
                (item for item in self.templates if item.agent.name == template), None
            )
            if selected is None:
                raise ValueError(f"Unknown subagent template: {template}")
        selected = replace(
            selected,
            agent=replace(selected.agent, name=name.strip())
            if name is not None
            else selected.agent,
            provider_id=provider_id.strip()
            if provider_id is not None
            else selected.provider_id,
        )
        if not selected.provider_id:
            selected = replace(
                selected,
                provider_id=await root.context.get_current_chat_provider_id(
                    root.event.unified_msg_origin
                ),
            )
        instance = SubAgentExecutor._submit_subagent(
            selected, context, task=task, image_urls=image_urls
        )
        await runtime.checkpoint()
        return json.dumps(
            {
                "agent_id": instance.agent_id,
                "name": instance.agent.name,
                "provider_id": instance.provider_id,
                "state": instance.state.value,
            },
            ensure_ascii=False,
        )


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


class ListAgentsTool(FunctionTool):
    """List workers owned by the calling parent agent."""

    def __init__(self) -> None:
        super().__init__(
            name="list_agents",
            description="List your workers and their current states, including earlier turns in this conversation when persistence is enabled. Use wait_agent to wait instead of repeatedly polling.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler_module_path=__package__ + ".main",
        )

    async def call(self, context: AgentContextWrapper) -> str:
        root = context.context
        return json.dumps(
            {
                "agents": [
                    instance.to_dict()
                    for instance in root.subagent_runtime.list_instances(root.agent_id)
                ]
            }
        )


class GetAgentResultTool(FunctionTool):
    """Read a worker's final result without blocking or consuming it."""

    def __init__(self) -> None:
        super().__init__(
            name="get_agent_result",
            description="Read a worker's current state, final result, or error by agent_id. Returns immediately; unfinished workers have null result/error. Results can be read repeatedly.",
            parameters={
                "type": "object",
                "properties": {"agent_id": {"type": "string", "minLength": 1}},
                "required": ["agent_id"],
                "additionalProperties": False,
            },
            handler_module_path=__package__ + ".main",
        )

    async def call(self, context: AgentContextWrapper, agent_id: str) -> str:
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a nonempty worker ID")
        root = context.context
        try:
            instance = root.subagent_runtime.get_instance(
                agent_id, parent_agent_id=root.agent_id
            )
        except KeyError:
            raise ValueError(f"Unknown subagent: {agent_id}") from None
        root.subagent_runtime.acknowledge([instance], root.agent_id)
        await root.subagent_runtime.checkpoint()
        data = instance.to_dict(include_result=True)
        if instance.finished.is_set():
            data["receipt"] = (
                f"[subagent-result:{instance.agent_id}:{instance.turn_id}]"
            )
        return json.dumps(data)


class WaitAgentTool(FunctionTool):
    """Wait for terminal worker states with an independent waiting budget."""

    def __init__(self) -> None:
        super().__init__(
            name="wait_agent",
            execution_timeout=65,
            description="Wait until any or all specified workers finish. Failed, cancelled, timed-out, and interrupted workers also count as finished. Returns states and final results. timeout_ms only limits this wait; workers continue on timeout. Use 0 for a nonblocking check.",
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
                        "maximum": 60_000,
                        "default": 30_000,
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
            handler_module_path=__package__ + ".main",
        )

    async def call(
        self,
        context: AgentContextWrapper,
        agent_ids: list[str],
        timeout_ms: int = 30_000,
        mode: str = "any",
    ) -> str:
        root = context.context
        instances, timed_out = await root.subagent_runtime.wait_instances(
            parent_agent_id=root.agent_id,
            agent_ids=agent_ids,
            timeout_ms=timeout_ms,
            mode=mode,
        )
        root.subagent_runtime.acknowledge(instances, root.agent_id)
        await root.subagent_runtime.checkpoint()
        return json.dumps(
            {
                "agents": [
                    instance.to_dict(include_result=True) for instance in instances
                ],
                "timed_out": timed_out,
                "receipts": [
                    f"[subagent-result:{item.agent_id}:{item.turn_id}]"
                    for item in instances
                    if item.finished.is_set()
                ],
            }
        )


class SendAgentMessageTool(FunctionTool):
    """Steer a running worker or start its next turn through one entry point."""

    def __init__(self) -> None:
        super().__init__(
            name="send_message",
            description=(
                "Send follow-up instructions to one of your workers. Returns immediately. "
                "A running worker receives them in its next tool response. If its current "
                "turn completes before receiving them, or has already ended, a new turn "
                "starts automatically with the same agent_id and conversation context. "
                "No separate followup_task or queue/steer option is needed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "minLength": 1},
                    "message": {"type": "string", "minLength": 1},
                },
                "required": ["agent_id", "message"],
                "additionalProperties": False,
            },
            handler_module_path=__package__ + ".main",
        )

    async def call(
        self, context: AgentContextWrapper, agent_id: str, message: str
    ) -> str:
        """Accept follow-up input and schedule a continuation when needed.

        Args:
            context: Parent execution that owns the target worker.
            agent_id: Worker returned by spawn_agent.
            message: Nonempty instructions for the worker.

        Returns:
            Acceptance metadata for the worker's current turn.

        Raises:
            ValueError: If input, ownership, or execution state prevents delivery.
        """
        from astrbot.core.utils.active_event_registry import active_event_registry

        from .execution import SubAgentExecutor as FunctionToolExecutor

        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a nonempty worker ID")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be nonempty text")
        root = context.context
        if active_event_registry.get_background_stop_signal(root.event).is_set():
            raise ValueError("Cannot send a message after the session was stopped")
        if (
            root.subagent_runtime.store is not None
            and root.subagent_runtime.store.closing
        ):
            raise ValueError("Cannot send a message while AstrBot is shutting down")
        try:
            instance = root.subagent_runtime.get_instance(
                agent_id, parent_agent_id=root.agent_id
            )
        except KeyError:
            raise ValueError(f"Unknown subagent: {agent_id}") from None
        if instance.cancel_requested and not instance.finished.is_set():
            raise ValueError("Subagent cancellation is still in progress")

        ticket = (
            instance.runner.follow_up(message_text=message) if instance.runner else None
        )
        if ticket is not None:
            instance.steering_tickets.append(ticket)
        else:
            instance.pending_messages.append(message)
        if instance.finished.is_set():
            FunctionToolExecutor._submit_subagent(
                SubAgentTemplate(instance.agent, provider_id=instance.provider_id),
                context,
                instance=instance,
                image_urls_prepared=True,
            )
        await root.subagent_runtime.checkpoint()
        return json.dumps(
            {
                "agent_id": instance.agent_id,
                "turn_id": instance.turn_id,
                "state": instance.state.value,
                "accepted": True,
            }
        )


class CancelAgentTool(FunctionTool):
    """Cancel one worker without stopping its parent or siblings."""

    def __init__(self) -> None:
        super().__init__(
            name="cancel_agent",
            description="Cancel a queued or running worker by agent_id. Does not cancel its parent or other workers. Use wait_agent to observe the final state.",
            parameters={
                "type": "object",
                "properties": {"agent_id": {"type": "string", "minLength": 1}},
                "required": ["agent_id"],
                "additionalProperties": False,
            },
            handler_module_path=__package__ + ".main",
        )

    async def call(self, context: AgentContextWrapper, agent_id: str) -> str:
        """Discard pending input and request cancellation of one worker.

        Args:
            context: Parent execution that owns the target worker.
            agent_id: Worker to stop.

        Returns:
            Current worker state and whether cancellation was requested.

        Raises:
            ValueError: If the ID is invalid or does not belong to this parent.
        """
        from astrbot.core.utils.active_event_registry import active_event_registry

        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a nonempty worker ID")
        root = context.context
        try:
            instance = root.subagent_runtime.get_instance(
                agent_id, parent_agent_id=root.agent_id
            )
        except KeyError:
            raise ValueError(f"Unknown subagent: {agent_id}") from None
        instance.pending_messages.clear()
        for ticket in instance.steering_tickets:
            ticket.resolved.set()
        instance.steering_tickets.clear()
        if not instance.finished.is_set():
            instance.cancel_requested = True
            if instance.execution_task is not None:
                active_event_registry.cancel_background_task(instance.execution_task)
        await root.subagent_runtime.checkpoint()
        return json.dumps(
            {
                **instance.to_dict(),
                "cancel_requested": instance.cancel_requested,
            }
        )
