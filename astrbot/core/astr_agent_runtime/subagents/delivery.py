"""Deliver results to their direct parent through steering or a targeted wakeup."""

from __future__ import annotations

import asyncio
import copy
import json
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.agent.input import PlainInput
from astrbot.core.agent.runtime import (
    AgentInput,
    AgentPermissions,
    AgentRuntime,
    AgentSessionRef,
)
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.utils.active_event_registry import active_event_registry

from .store import AgentScope, DeliveryStage

if TYPE_CHECKING:
    from astrbot.core.star.context import Context

    from .caller import AgentCaller
    from .store import SubAgentStore


class AgentResultDelivery:
    """Deliver completed child turns once to each direct parent session."""

    def __init__(
        self,
        store: SubAgentStore,
        callers: dict[AgentScope, AgentCaller],
        runtimes: dict[str, AgentRuntime],
    ) -> None:
        self.store = store
        self.callers = callers
        self.context: Context | None = None
        self.runtimes = runtimes
        self._notifications: dict[
            tuple[AgentScope, AgentSessionRef], asyncio.Task[None]
        ] = {}
        self._closing = False

    async def reconcile(
        self,
        scope: AgentScope,
        parent: AgentSessionRef,
        history: str,
        *,
        reset_unconfirmed: bool = True,
    ) -> None:
        """Confirm receipt markers only after they appear in saved parent history.

        Args:
            scope: Owner of delegated results.
            parent: Exact runtime conversation that created these agents.
            history: Saved parent conversation history.
            reset_unconfirmed: Whether an ended execution can release unread results.
        """
        for agent in self.store.list(scope):
            if agent.parent != parent:
                continue
            changed = False
            for turn in agent.turns:
                if not turn.finished or turn.delivery == DeliveryStage.COMMITTED:
                    continue
                receipt = f"[subagent-result:{agent.agent_id}:{turn.turn_id}]"
                delivery = (
                    DeliveryStage.COMMITTED
                    if receipt in history
                    else DeliveryStage.PENDING
                    if reset_unconfirmed
                    else turn.delivery
                )
                if turn.delivery != delivery:
                    turn.delivery, changed = delivery, True
            if changed:
                await self.store.save(agent)

    def schedule(self, scope: AgentScope) -> None:
        """Start independent delivery tasks so a parent's wait cannot block its child.

        Args:
            scope: Ownership scope whose completed tasks may need delivery.
        """
        if self._closing:
            return
        caller = self.callers.get(scope)
        if (
            caller
            and active_event_registry.get_background_stop_signal(caller.event).is_set()
        ):
            return
        parents = {
            agent.parent
            for agent in self.store.list(scope)
            if any(
                turn.finished and turn.delivery != DeliveryStage.COMMITTED
                for turn in agent.turns
            )
        }
        for parent in parents:
            key = (scope, parent)
            if key in self._notifications:
                continue
            task = asyncio.create_task(self._notify(scope, parent))
            self._notifications[key] = task

            def discard_cancelled(
                completed: asyncio.Task[None],
                key=key,
            ) -> None:
                # A task cancelled before entry cannot execute its finally.
                if completed.cancelled() and self._notifications.get(key) is completed:
                    self._notifications.pop(key, None)

            task.add_done_callback(discard_cancelled)
            if caller is not None:
                active_event_registry.register_background_task(caller.event, task)

    async def _notify(self, scope: AgentScope, parent: AgentSessionRef) -> None:
        """Offer results to their parent and queue unconsumed input on its own session.

        Args:
            scope: Original caller ownership and delivery address.
            parent: Stable parent runtime/session, never selected again from UMO.
        """
        queued = False
        attempted: set[str] = set()
        try:
            context = self.context
            if self._closing or context is None:
                return
            runtime = self.runtimes.get(parent.runtime)
            if runtime is None:
                raise ValueError(f"Parent agent runtime unavailable: {parent.runtime}")
            session = await runtime.open_session(
                scope.umo, session_id=parent.session_id
            )
            while not self._closing:
                caller = self.callers.get(scope)
                if (
                    caller
                    and active_event_registry.get_background_stop_signal(
                        caller.event
                    ).is_set()
                ):
                    return
                active = session.active_turn
                history = json.dumps(await session.history(), ensure_ascii=False)
                await self.reconcile(
                    scope, parent, history, reset_unconfirmed=active is None
                )
                records = [
                    (agent, turn)
                    for agent in self.store.list(scope)
                    if agent.parent == parent
                    for turn in agent.turns
                    if turn.finished
                    and turn.delivery == DeliveryStage.PENDING
                    and f"[subagent-result:{agent.agent_id}:{turn.turn_id}]"
                    not in attempted
                ]
                if active is not None and active.input.event.get_extra(
                    "_subagent_wakeup"
                ):
                    # Observe an already queued delivery; never steer its own input back into it.
                    body = active.input.event.message_str
                    attempted.update(
                        f"[subagent-result:{agent.agent_id}:{turn.turn_id}]"
                        for agent, turn in records
                        if f"[subagent-result:{agent.agent_id}:{turn.turn_id}]" in body
                    )
                    await active.result()
                    continue
                if not records:
                    if active is not None:
                        await active.result()
                        continue
                    return
                batch = [agent.describe(turn, result=True) for agent, turn in records]
                prompt = (
                    "<system_reminder>\n[Subagent results]\n"
                    + " ".join(item["receipt"] for item in batch)
                    + "\nReview these delegated task results and continue the original task.\n"
                    + json.dumps(batch, ensure_ascii=False)
                    + "\n</system_reminder>"
                )
                if active is not None:
                    receipt = (
                        active.steer(
                            AgentInput(
                                event=caller.event,
                                permissions=caller.agent_context.permissions
                                or AgentPermissions.from_event(caller.event),
                                content=[PlainInput(text=prompt)],
                                plugin_tools=caller.agent_context.plugin_tools,
                                plugin_skills=caller.agent_context.plugin_skills,
                            )
                        )
                        if caller is not None
                        else None
                    )
                    if receipt is not None and await receipt:
                        for agent, turn in records:
                            turn.delivery = DeliveryStage.COMMITTED
                            await self.store.save(agent)
                        continue
                    await active.result()
                    continue
                event = self._wakeup_event(scope, parent, prompt)
                await context.get_event_queue().put(event)
                queued = True
                return
        except Exception:
            logger.exception("Unable to deliver agent results to parent %s", parent)
        finally:
            if not queued:
                self._notifications.pop((scope, parent), None)

    def _wakeup_event(
        self,
        scope: AgentScope,
        parent: AgentSessionRef,
        prompt: str,
    ) -> AgentWakeupEvent:
        """Preserve the caller's transport and authorization for a targeted parent turn.

        Args:
            scope: Original message source and caller ownership.
            parent: Exact runtime conversation receiving the queued turn.
            prompt: Complete result input, including durable receipt markers.

        Returns:
            An ordinary pipeline event with an explicit parent session.

        Raises:
            ValueError: If services or the target platform are unavailable.
        """
        context = self.context
        if context is None:
            raise ValueError("Agent result delivery is not initialized")
        caller = self.callers.get(scope)
        session = MessageSession.from_str(scope.umo)
        platform = context.get_platform_inst(session.platform_id)
        if platform is None:
            raise ValueError(
                f"Platform adapter {session.platform_id!r} not found for agent wakeup"
            )
        agent = self.store.list(scope)[0]
        event = AgentWakeupEvent(
            context=context,
            session=session,
            platform_meta=platform.meta(),
            prompt=prompt,
            agent_session=parent,
            source="plugin",
            source_id="subagent",
        )
        event.set_extra(
            "_subagent_wakeup",
            [scope.umo, scope.conversation_id],
        )
        event.message_obj.sender.user_id = agent.owner["sender_id"]
        event.message_obj.sender.nickname = agent.owner.get("sender_name")
        event.plugins_name = copy.copy(
            caller.event.plugins_name if caller else agent.owner.get("plugins_name")
        )
        if caller:
            event.set_extra(
                "_background_stop_signal",
                active_event_registry.get_background_stop_signal(caller.event),
            )
            event.set_extra(
                "_api_key_allow_admin_role",
                caller.event.get_extra("_api_key_allow_admin_role"),
            )
            event.message_obj.sender = copy.copy(caller.event.message_obj.sender)
            event.message_obj.group = copy.copy(caller.event.message_obj.group)
        elif agent.owner.get("group_id"):
            from astrbot.core.platform.astrbot_message import Group

            event.message_obj.group = Group(group_id=agent.owner["group_id"])
        config = context.get_config(umo=scope.umo)
        if (
            caller.event.role == "admin"
            and caller.event.get_extra("_api_key_allow_admin_role") is not False
            if caller
            else agent.owner.get("was_admin")
        ) and event.get_sender_id() in [
            str(item) for item in config.get("admins_id", [])
        ]:
            event.role = "admin"
        return event

    async def consume_wakeup(
        self,
        scope: AgentScope,
        parent: AgentSessionRef,
        history: str,
    ) -> bool:
        """Release queued delivery and observe its real history commit through the turn.

        Args:
            scope: Ownership encoded by the wakeup.
            parent: Explicit session encoded by the wakeup.
            history: Committed parent history loaded for this execution.

        Returns:
            Whether any result still needs this delivery input.
        """
        self._notifications.pop((scope, parent), None)
        await self.reconcile(scope, parent, history)
        pending = any(
            turn.finished and turn.delivery == DeliveryStage.PENDING
            for agent in self.store.list(scope)
            if agent.parent == parent
            for turn in agent.turns
        )
        self.schedule(scope)
        return pending

    async def close(self) -> None:
        """Cancel delivery tasks without changing committed parent history."""
        self._closing = True
        tasks = list(self._notifications.values())
        for task in tasks:
            active_event_registry.cancel_background_task(task)
        await asyncio.gather(*tasks, return_exceptions=True)
        self._notifications.clear()
