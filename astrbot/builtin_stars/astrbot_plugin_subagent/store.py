"""Durable, conversation-scoped worker checkpoints using AstrBot's database."""

from __future__ import annotations

import asyncio
import copy
import json
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.message import (
    Message,
    bind_checkpoint_messages,
    dump_messages_with_checkpoints,
)
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.platform.astrbot_message import Group, MessageMember
from astrbot.core.platform.message_session import MessageSession

from .runtime import SubAgentCompletion, SubAgentRuntime, SubAgentState

if TYPE_CHECKING:
    from astrbot.core.db import BaseDatabase
    from astrbot.core.star.context import Context

    from .context import SubAgentContext as AstrAgentContext


class SubAgentStore:
    """Keep worker identities and checkpoints scoped to conversation and sender."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        self.settings: dict = {}
        self.scheduler = None
        self.runtimes: dict[tuple[str, str, str], SubAgentRuntime] = {}
        self._load_lock = asyncio.Lock()
        self._writes: set[asyncio.Task] = set()
        self.closing = False

    async def bind(self, parent: AstrAgentContext) -> None:
        """Attach a root request to its sender's persisted conversation runtime.

        Args:
            parent: Fresh parent context; worker contexts are left attached.

        Raises:
            ValueError: If stored data has an unsupported schema or wrong scope.
        """
        if parent.agent_id in parent.subagent_runtime._instances:
            return
        sender = parent.event.get_sender_id()
        if not parent.conversation_id or not sender:
            return
        scope = (parent.event.unified_msg_origin, parent.conversation_id, str(sender))
        async with self._load_lock:
            if self.closing:
                raise ValueError("Cannot bind workers while AstrBot is shutting down")
            conversation = await parent.context.conversation_manager.get_conversation(
                scope[0], scope[1]
            )
            if conversation is None:
                raise ValueError("Cannot bind workers to a deleted conversation")
            if conversation.user_id != scope[0]:
                raise ValueError("Subagent conversation belongs to another session")
            runtime = self.runtimes.get(scope)
            if runtime is None:
                row = await self.db.get_preference(
                    "subagent_runtime", scope[0], json.dumps(scope[1:])
                )
                if row is not None:
                    runtime = self._restore(row.value, parent, scope)
                else:
                    runtime = parent.subagent_runtime
                    if runtime.storage_scope not in (None, scope) or any(
                        item.conversation_id != scope[1]
                        or item.unified_msg_origin != scope[0]
                        for item in runtime._instances.values()
                    ):
                        runtime = SubAgentRuntime()
                    runtime.parent_agent_id = parent.agent_id
                runtime.store = self
                runtime.storage_scope = scope
                self.runtimes[scope] = runtime
            runtime.settings = self.settings
            if self.scheduler is not None:
                runtime.scheduler = self.scheduler
            parent.agent_id = runtime.parent_agent_id or parent.agent_id
            parent.subagent_runtime = runtime
            # New user turns supply fresh permissions and plugin restrictions.
            runtime.parent_context = ContextWrapper(context=parent)
            await self.reconcile(runtime, conversation.history)
            await runtime.checkpoint()

    def _restore(
        self, data: dict, parent: AstrAgentContext, scope: tuple[str, str, str]
    ) -> SubAgentRuntime:
        """Reconstruct private histories without replaying interrupted tool work.

        Args:
            data: Persisted JSON checkpoint.
            parent: Request carrying current ownership and permissions.
            scope: Expected session, conversation, and sender binding.

        Returns:
            Runtime with terminal workers and a restored result mailbox.

        Raises:
            ValueError: If checkpoint schema, scope, or worker records are invalid.
        """
        if data.get("version") != 1 or tuple(data.get("scope", [])) != scope:
            raise ValueError("Invalid subagent checkpoint schema or ownership")
        runtime = SubAgentRuntime()
        runtime.parent_agent_id = data["parent_agent_id"]
        parent.agent_id = runtime.parent_agent_id
        parent.subagent_runtime = runtime
        wrapper = ContextWrapper(context=parent)
        runtime._durable_received = {tuple(key) for key in data.get("received", [])}
        runtime._received_results = set(runtime._durable_received)
        stopped = bool(data.get("stopped"))
        interrupted = []
        for entry in data.get("workers", []):
            if (
                entry["conversation_id"] != scope[1]
                or entry["parent_agent_id"] != parent.agent_id
            ):
                raise ValueError("Worker checkpoint belongs to another conversation")
            instance = runtime.create_instance(
                agent=Agent(
                    name=entry["name"],
                    instructions=entry["instructions"],
                    tools=entry["tools"],
                    begin_dialogs=entry.get("begin_dialogs"),
                ),
                parent_context=wrapper,
                task=entry.get("task"),
                provider_id=entry.get("provider_id"),
            )
            runtime._instances.pop(instance.agent_id)
            instance.agent_id = entry["agent_id"]
            instance.run_context.context.agent_id = instance.agent_id
            instance.run_context.context.extra = entry.get("extra", {})
            instance.run_context.tool_call_timeout = entry.get("tool_call_timeout", 120)
            instance.run_context.messages = bind_checkpoint_messages(
                entry.get("messages", [])
            )
            instance.checkpoint_messages = copy.deepcopy(instance.run_context.messages)
            instance.turn_id = entry["turn_id"]
            instance.created_at = entry["created_at"]
            instance.completed_steps = entry.get("completed_steps", 0)
            instance.updated_at = entry.get("updated_at", instance.created_at)
            instance.started_at = entry.get("started_at")
            instance.finished_at = entry.get("finished_at")
            instance.result = entry.get("result")
            instance.error = entry.get("error")
            instance._state = SubAgentState(entry["state"])
            instance.pending_messages = (
                [] if stopped else list(entry.get("pending_messages", []))
            )
            instance.cancel_requested = bool(entry.get("cancel_requested"))
            runtime._instances[instance.agent_id] = instance
            if instance.state in (SubAgentState.PENDING, SubAgentState.RUNNING):
                cancelled = stopped or instance.cancel_requested
                instance.finish(
                    SubAgentState.CANCELLED if cancelled else SubAgentState.INTERRUPTED,
                    error=(
                        "Stopped before restart."
                        if cancelled
                        else "Interrupted by restart. Completed steps were retained. "
                        "Inspect any tool work that may have been in flight before "
                        "using send_message to resume."
                    ),
                )
                interrupted.append(instance)
            else:
                instance.finished.set()
            instance.result_received = (
                instance.agent_id,
                instance.turn_id,
            ) in runtime._durable_received
        for result in data.get("results", []):
            completion = SubAgentCompletion(
                agent_id=result["agent_id"],
                parent_agent_id=parent.agent_id,
                unified_msg_origin=scope[0],
                conversation_id=scope[1],
                turn_id=result["turn_id"],
                data=result,
            )
            runtime.publish_result(completion)
        for instance in interrupted:
            runtime.publish_result(instance)
        if stopped:
            runtime._received_results.update(runtime._completions)
            runtime._durable_received.update(runtime._completions)
            runtime._pending_results.clear()
        return runtime

    async def save(self, runtime: SubAgentRuntime) -> None:
        """Write one detached snapshot while the runtime's writer lock is held.

        Args:
            runtime: Runtime with a conversation storage binding.
        """
        if runtime.storage_scope is None or runtime.parent_context is None:
            return
        event = runtime.parent_context.context.event
        workers = []
        for instance in runtime._instances.values():
            if (
                instance.finished.is_set()
                and (instance.agent_id, instance.turn_id) not in runtime._completions
            ):
                runtime.publish_result(instance)
            tools = instance.agent.tools
            dialogs = [
                item.model_dump() if isinstance(item, Message) else item
                for item in instance.agent.begin_dialogs or []
            ]
            workers.append(
                {
                    **instance.to_dict(include_result=True),
                    "conversation_id": instance.conversation_id,
                    "task": instance.task,
                    "provider_id": instance.provider_id,
                    "instructions": instance.agent.instructions,
                    "tools": [
                        item.name if isinstance(item, FunctionTool) else item
                        for item in tools
                    ]
                    if tools is not None
                    else None,
                    "begin_dialogs": dialogs,
                    "messages": dump_messages_with_checkpoints(
                        [
                            message
                            for message in (
                                instance.checkpoint_messages
                                if instance.checkpoint_messages is not None
                                else instance.run_context.messages
                            )
                            if not message._no_save
                        ]
                    ),
                    "extra": instance.run_context.context.extra,
                    "tool_call_timeout": instance.run_context.tool_call_timeout,
                    "pending_messages": [
                        ticket.text for ticket in instance.steering_tickets
                    ]
                    + instance.pending_messages,
                    "cancel_requested": instance.cancel_requested,
                }
            )
        payload = copy.deepcopy(
            {
                "version": 1,
                "scope": runtime.storage_scope,
                "parent_agent_id": runtime.parent_agent_id,
                "sender_name": event.message_obj.sender.nickname,
                "group_id": event.get_group_id(),
                "plugins_name": event.plugins_name,
                "was_admin": event.role == "admin"
                and event.get_extra("_api_key_allow_admin_role") is not False,
                "stopped": bool(event.get_extra("agent_stop_requested")),
                "workers": workers,
                "results": [
                    item.to_dict(include_result=True)
                    for item in runtime._completions.values()
                ],
                "received": list(runtime._durable_received),
            }
        )
        scope = runtime.storage_scope
        await self.db.insert_preference_or_update(
            "subagent_runtime",
            scope[0],
            json.dumps(scope[1:]),
            payload,
        )

    def schedule_save(self, runtime: SubAgentRuntime) -> None:
        """Retain a checkpoint requested by a synchronous task-completion callback.

        Args:
            runtime: Runtime whose terminal state changed.
        """
        if self.closing:
            return
        task = asyncio.create_task(runtime.checkpoint())
        self._writes.add(task)

        def done(completed: asyncio.Task) -> None:
            self._writes.discard(completed)
            if not completed.cancelled() and completed.exception() is not None:
                logger.error(
                    "Failed to checkpoint subagent runtime: %s", completed.exception()
                )

        task.add_done_callback(done)

    async def reconcile(self, runtime: SubAgentRuntime, history: str) -> None:
        """Confirm only result IDs present in the saved original-conversation history.

        Args:
            runtime: Conversation-owned delivery state.
            history: Persisted history, including any compaction checkpoints.
        """
        saved = set()
        for key in runtime._completions:
            marker = f"[subagent-result:{key[0]}:{key[1]}]"
            if marker in history:
                saved.add(key)
        if saved:
            runtime.acknowledge(
                [runtime._completions[key] for key in saved], runtime.parent_agent_id
            )
            await runtime.commit_received(saved)
        # Unconfirmed in-memory receipts remain recoverable after a restart.
        # Do not repeatedly wake main for a result it has already consumed.

    async def recover(self, context: Context) -> None:
        """Restore owned records and enqueue undelivered results after startup.

        Args:
            context: Initialized plugin context with models and platforms ready.
        """
        from astrbot.core.utils.active_event_registry import active_event_registry

        from .context import SubAgentContext as AstrAgentContext
        from .execution import SubAgentExecutor as FunctionToolExecutor

        rows = await self.db.get_preferences(scope="subagent_runtime")
        for row in rows:
            if self.closing:
                return
            try:
                data = row.value
                scope = tuple(data["scope"])
                if (
                    len(scope) != 3
                    or row.scope_id != scope[0]
                    or row.key != json.dumps(scope[1:])
                ):
                    raise ValueError("Mismatched subagent checkpoint storage key")
                if scope in self.runtimes:
                    continue
                conv = await context.conversation_manager.get_conversation(
                    scope[0], scope[1]
                )
                if conv is None:
                    await self.db.remove_preference(row.scope, row.scope_id, row.key)
                    continue
                if conv.user_id != scope[0]:
                    raise ValueError("Subagent conversation belongs to another session")
                session = MessageSession.from_str(scope[0])
                event = CronMessageEvent(
                    context=context,
                    session=session,
                    message="Subagent recovery",
                    message_type=session.message_type,
                )
                event.message_obj.sender = MessageMember(
                    user_id=scope[2], nickname=data.get("sender_name")
                )
                if data.get("group_id"):
                    event.message_obj.group = Group(group_id=data["group_id"])
                event.plugins_name = data.get("plugins_name")
                cfg = context.get_config(umo=scope[0]) or {}
                if data.get("was_admin") and scope[2] in [
                    str(item) for item in cfg.get("admins_id", [])
                ]:
                    event.role = "admin"
                parent = AstrAgentContext(
                    context=context, event=event, conversation_id=scope[1]
                )
                await self.bind(parent)
                if self.closing:
                    return
                runtime = parent.subagent_runtime
                current_cid = (
                    await context.conversation_manager.get_curr_conversation_id(
                        scope[0]
                    )
                )
                if (
                    runtime._pending_results
                    and self.settings.get("enabled", True)
                    and current_cid == scope[1]
                ):
                    task = asyncio.create_task(
                        FunctionToolExecutor._dispatch_subagent_results(
                            runtime.parent_context
                        )
                    )
                    runtime.wakeup_task = task
                    active_event_registry.register_background_task(event, task)
            except Exception as exc:
                if self.closing:
                    return
                logger.error(
                    "Unable to recover subagent runtime %s: %s",
                    row.key,
                    exc,
                    exc_info=True,
                )

    async def close(self) -> None:
        """Stop execution and flush checkpoints before models and storage close."""
        self.closing = True
        # Include bindings already loading, and reject any later binding.
        async with self._load_lock:
            runtimes = list(self.runtimes.values())
        for runtime in runtimes:
            interrupted = [
                item
                for item in runtime._instances.values()
                if not item.finished.is_set()
            ]
            tasks = [
                item.execution_task
                for item in runtime._instances.values()
                if item.execution_task is not None
            ]
            if runtime.wakeup_task is not None:
                tasks.append(runtime.wakeup_task)
            from astrbot.core.utils.active_event_registry import active_event_registry

            for task in tasks:
                active_event_registry.cancel_background_task(task)
            await asyncio.gather(*tasks, return_exceptions=True)
            for instance in interrupted:
                instance.pending_messages[:0] = [
                    ticket.text for ticket in instance.steering_tickets
                ]
                instance.steering_tickets.clear()
                error = "Interrupted by service shutdown. Use send_message to resume from the last checkpoint."
                if not instance.finished.is_set():
                    instance.finish(
                        SubAgentState.CANCELLED
                        if instance.cancel_requested
                        else SubAgentState.INTERRUPTED,
                        error="Subagent execution was cancelled."
                        if instance.cancel_requested
                        else error,
                    )
                elif not instance.cancel_requested:
                    instance._state = SubAgentState.INTERRUPTED
                    instance.error = error
                runtime.publish_result(instance)
            await runtime.checkpoint()
        await asyncio.gather(*self._writes, return_exceptions=False)
