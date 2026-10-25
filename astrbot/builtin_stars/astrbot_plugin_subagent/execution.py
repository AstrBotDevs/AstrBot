from __future__ import annotations

import asyncio
import copy
import typing as T
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from time import time

import mcp

from astrbot import logger
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolSet
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.message.components import Image
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.star.star import star_map
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.config_number import coerce_int_config
from astrbot.core.utils.image_ref_utils import is_supported_image_ref
from astrbot.core.utils.session_lock import session_lock_manager
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

from .context import SubAgentContext as AstrAgentContext
from .runtime import SubAgentInstance, SubAgentState
from .tools import SUBAGENT_TOOL_NAMES, SubAgentTemplate


class WorkerHooks(BaseAgentRunHooks):
    async def on_agent_begin(self, context):
        worker = context.context.subagent_runtime._instances[context.context.agent_id]
        worker.checkpoint_messages = copy.deepcopy(context.messages)
        context.context.subagent_runtime.begin_parent(context, context.runner)

    async def on_agent_step_end(self, context):
        worker = context.context.subagent_runtime._instances[context.context.agent_id]
        worker.completed_steps += 1
        worker.updated_at = time()
        worker.checkpoint_messages = copy.deepcopy(context.messages)
        await context.context.subagent_runtime.checkpoint(context)

    async def on_agent_done(self, context, response):
        worker = context.context.subagent_runtime._instances[context.context.agent_id]
        if (
            context.run_end_reason in ("cancelled", "error")
            and worker.checkpoint_messages is not None
        ):
            context.messages = copy.deepcopy(worker.checkpoint_messages)
        context.context.subagent_runtime.end_parent(context)


class SubAgentExecutor:
    @classmethod
    def _collect_image_urls_from_args(cls, image_urls_raw: T.Any) -> list[str]:
        if image_urls_raw is None:
            return []

        if isinstance(image_urls_raw, str):
            return [image_urls_raw]

        if isinstance(image_urls_raw, (Sequence, AbstractSet)) and not isinstance(
            image_urls_raw, (str, bytes, bytearray)
        ):
            return [item for item in image_urls_raw if isinstance(item, str)]

        logger.debug(
            "Unsupported image_urls type in template tool args: %s",
            type(image_urls_raw).__name__,
        )
        return []

    @classmethod
    async def _collect_image_urls_from_message(
        cls, run_context: ContextWrapper[AstrAgentContext]
    ) -> list[str]:
        urls: list[str] = []
        event = getattr(run_context.context, "event", None)
        message_obj = getattr(event, "message_obj", None)
        message = getattr(message_obj, "message", None)
        if message:
            for idx, component in enumerate(message):
                if not isinstance(component, Image):
                    continue
                try:
                    path = await component.convert_to_file_path()
                    if path:
                        urls.append(path)
                except Exception as e:
                    logger.error(
                        "Failed to convert template image component at index %d: %s",
                        idx,
                        e,
                        exc_info=True,
                    )
        return urls

    @classmethod
    async def _collect_subagent_image_urls(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
        image_urls_raw: T.Any,
    ) -> list[str]:
        candidates: list[str] = []
        candidates.extend(cls._collect_image_urls_from_args(image_urls_raw))
        candidates.extend(await cls._collect_image_urls_from_message(run_context))

        normalized = normalize_and_dedupe_strings(candidates)
        extensionless_local_roots = (get_astrbot_temp_path(),)
        sanitized = [
            item
            for item in normalized
            if is_supported_image_ref(
                item,
                allow_extensionless_existing_local_file=True,
                extensionless_local_roots=extensionless_local_roots,
            )
        ]
        dropped_count = len(normalized) - len(sanitized)
        if dropped_count > 0:
            logger.debug(
                "Dropped %d invalid image_urls entries in template image inputs.",
                dropped_count,
            )
        return sanitized

    @classmethod
    def _build_subagent_toolset(cls, run_context, tools):
        root = run_context.context
        available = ToolSet()
        for candidate in root.context.get_llm_tool_manager().get_full_tool_set():
            available.add_tool(candidate)
        parent = root.subagent_runtime.parent_context
        if parent is not None:
            available.merge(parent.context.delegable_tools)
        selected = (
            available.tools
            if tools is None
            else [
                available.get_tool(item) if isinstance(item, str) else item
                for item in tools
            ]
        )
        result = ToolSet()
        allowed = root.event.plugins_name
        for tool in selected:
            if tool is None or not tool.active or tool.name in SUBAGENT_TOOL_NAMES:
                continue
            if tool.name.startswith("transfer_to_"):
                continue
            metadata = star_map.get(tool.handler_module_path)
            if (
                metadata is not None
                and not metadata.reserved
                and allowed is not None
                and allowed != ["*"]
                and metadata.name not in allowed
            ):
                continue
            result.add_tool(tool)
        return None if result.empty() else result

    @classmethod
    async def _execute_subagent(
        cls,
        tool: SubAgentTemplate,
        run_context: ContextWrapper[AstrAgentContext],
        *,
        image_urls_prepared: bool = False,
        instance: SubAgentInstance | None = None,
        **tool_args: T.Any,
    ):
        instance = instance or run_context.context.subagent_runtime.create_instance(
            agent=tool.agent,
            parent_context=run_context,
            task=tool_args.get("task"),
            provider_id=tool.provider_id,
        )
        config = run_context.context.context.get_config(umo=instance.unified_msg_origin)
        limits = instance.run_context.context.subagent_runtime.settings
        concurrent = coerce_int_config(
            limits.get("max_concurrent_agents", 3),
            default=3,
            min_value=1,
            field_name="subagent.max_concurrent_agents",
        )
        timeout = coerce_int_config(
            limits.get("task_timeout", 600),
            default=600,
            min_value=1,
            field_name="subagent.task_timeout",
        )
        max_steps = coerce_int_config(
            limits.get("max_steps", 30),
            default=30,
            min_value=1,
            field_name="subagent.max_steps",
        )
        parent_max_steps = coerce_int_config(
            config.get("agent_runner", {})
            .get("config", {})
            .get("misc", {})
            .get("max_steps", 128),
            default=128,
            min_value=1,
            field_name="agent_runner.config.misc.max_steps",
        )

        async def run() -> mcp.types.CallToolResult:
            async with run_context.context.subagent_runtime.scheduler.slot(
                instance.unified_msg_origin, concurrent
            ):
                instance.start()
                await run_context.context.subagent_runtime.checkpoint()
                return await cls._run_subagent(
                    instance,
                    image_urls_prepared=image_urls_prepared,
                    max_steps=min(max_steps, parent_max_steps),
                    **tool_args,
                )

        try:
            response = await asyncio.wait_for(run(), timeout=timeout)
        except asyncio.CancelledError:
            instance.finish(
                SubAgentState.CANCELLED, error="Subagent execution was cancelled."
            )
            raise
        except (TimeoutError, asyncio.TimeoutError) as exc:
            instance.finish(SubAgentState.TIMED_OUT, error=str(exc) or "Timed out")
            raise
        except Exception as exc:
            instance.finish(SubAgentState.FAILED, error=str(exc) or type(exc).__name__)
            raise

        instance.finish(
            SubAgentState.FAILED if response.isError else SubAgentState.COMPLETED,
            result=None if response.isError else response.content[0].text,
            error=(response.content[0].text or "Subagent returned an error response.")
            if response.isError
            else None,
        )
        yield response

    @classmethod
    async def _run_subagent(
        cls,
        instance: SubAgentInstance,
        *,
        image_urls_prepared: bool,
        max_steps: int,
        **tool_args: T.Any,
    ) -> mcp.types.CallToolResult:
        """Prepare and run a worker while its scheduler slot is held.

        Args:
            instance: Execution snapshot with a private message context.
            image_urls_prepared: Whether image inputs have already been normalized.
            max_steps: Effective worker step budget.
            **tool_args: Image references supplied by the parent.

        Returns:
            Final worker text and the provider's error status.
        """
        if image_urls_prepared:
            prepared = tool_args.get("image_urls")
            image_urls = list(prepared) if isinstance(prepared, list) else []
        else:
            image_urls = await cls._collect_subagent_image_urls(
                instance.run_context, tool_args.get("image_urls")
            )
        toolset = cls._build_subagent_toolset(
            instance.run_context, instance.agent.tools
        )
        ctx = instance.run_context.context.context
        event = instance.run_context.context.event
        instance.provider_id = (
            instance.provider_id
            or await ctx.get_current_chat_provider_id(instance.unified_msg_origin)
        )
        contexts = None
        if instance.turn_id > 1:
            # Retain accepted input even if provider setup fails before runner reset.
            if not instance.run_context.messages and instance.task:
                instance.run_context.messages.append(
                    Message(role="user", content=instance.task)
                )
            instance.run_context.messages.extend(
                Message(role="user", content=text) for text in instance.pending_messages
            )
            instance.pending_messages.clear()
            contexts = list(instance.run_context.messages)
            instance.checkpoint_messages = copy.deepcopy(contexts)
            if contexts and contexts[0].role == "system":
                contexts.pop(0)
        elif instance.agent.begin_dialogs:
            contexts = []
            for dialog in instance.agent.begin_dialogs:
                try:
                    contexts.append(
                        dialog
                        if isinstance(dialog, Message)
                        else Message.model_validate(dialog)
                    )
                except Exception:
                    continue
        settings = ctx.get_config(umo=instance.unified_msg_origin).get(
            "provider_settings", {}
        )
        response = await ctx.tool_loop_agent(
            event=event,
            chat_provider_id=instance.provider_id,
            prompt=instance.task if instance.turn_id == 1 else None,
            image_urls=image_urls,
            system_prompt=instance.agent.instructions,
            tools=toolset,
            contexts=contexts,
            max_steps=max_steps,
            tool_call_timeout=instance.run_context.tool_call_timeout,
            stream=settings.get("stream", False),
            run_context=instance.run_context,
            agent_hooks=WorkerHooks(),
        )
        return mcp.types.CallToolResult(
            content=[
                mcp.types.TextContent(type="text", text=response.completion_text or "")
            ],
            isError=response.role == "err",
        )

    @classmethod
    def _submit_subagent(
        cls,
        tool: SubAgentTemplate,
        run_context: ContextWrapper[AstrAgentContext],
        *,
        instance: SubAgentInstance | None = None,
        **tool_args: T.Any,
    ) -> SubAgentInstance:
        """Create a worker before scheduling it, returning without model or image I/O.

        Args:
            tool: Generic worker or configured expert template.
            run_context: Parent execution and session binding.
            instance: Existing terminal worker to resume with its private history.
            **tool_args: Explicit task and optional image references.

        Returns:
            A registered pending worker with a retained background task.

        Raises:
            ValueError: If the session has already been stopped.
        """
        event = run_context.context.event
        if active_event_registry.get_background_stop_signal(event).is_set():
            raise ValueError("Cannot submit a subagent after the session was stopped")
        runtime = run_context.context.subagent_runtime
        if runtime.store is not None and runtime.store.closing:
            raise ValueError("Cannot submit a subagent while AstrBot is shutting down")
        if instance is None:
            instance = runtime.create_instance(
                agent=tool.agent,
                parent_context=run_context,
                task=tool_args.get("task"),
                provider_id=tool.provider_id,
            )
        else:
            if not instance.finished.is_set():
                raise ValueError("Cannot start a new turn while the worker is running")
            instance.turn_id += 1
            instance._state = SubAgentState.PENDING
            instance.started_at = None
            instance.finished_at = None
            instance.result = None
            instance.error = None
            instance.result_received = False
            instance.cancel_requested = False
            instance.completed_steps = 0
            instance.updated_at = time()
            instance.finished.clear()
            instance.run_context.context.event = event

        async def _run_subagent_in_background() -> None:
            try:
                await cls._do_subagent_background(
                    tool=tool,
                    run_context=run_context,
                    instance=instance,
                    **tool_args,
                )
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"Background subagent {instance.agent_id} ({instance.agent.name}) failed: {e!s}",
                    exc_info=True,
                )

        task = asyncio.create_task(_run_subagent_in_background())
        instance.execution_task = task

        def on_done(completed: asyncio.Task) -> None:
            if instance.execution_task is not completed:
                return
            # A task cancelled before its first instruction never enters the runner.
            if not instance.finished.is_set():
                if completed.cancelled():
                    instance.finish(
                        SubAgentState.CANCELLED,
                        error="Subagent execution was cancelled.",
                    )
                else:
                    instance.finish(
                        SubAgentState.FAILED, error="Subagent stopped without a result."
                    )
            if (
                completed.cancelled()
                and not active_event_registry.get_background_stop_signal(event).is_set()
                and (runtime.store is None or not runtime.store.closing)
            ):
                runtime.publish_result(instance)
                if runtime.wakeup_task is None or runtime.wakeup_task.done():
                    notification = asyncio.create_task(
                        cls._dispatch_subagent_results(run_context)
                    )
                    runtime.wakeup_task = notification
                    active_event_registry.register_background_task(event, notification)
            if runtime.store is not None:
                runtime.store.schedule_save(runtime)

        task.add_done_callback(on_done)
        active_event_registry.register_background_task(event, task)
        return instance

    @classmethod
    async def _do_subagent_background(
        cls,
        tool: SubAgentTemplate,
        run_context: ContextWrapper[AstrAgentContext],
        instance: SubAgentInstance,
        **tool_args,
    ) -> None:
        """Run a worker and enqueue its result for boundary or idle delivery."""
        try:
            async for _ in cls._execute_subagent(
                tool,
                run_context,
                instance=instance,
                **tool_args,
            ):
                pass
        except Exception as e:
            if not instance.finished.is_set():
                instance.finish(SubAgentState.FAILED, error=str(e) or type(e).__name__)
        event = run_context.context.event
        if active_event_registry.get_background_stop_signal(event).is_set():
            return
        runtime = run_context.context.subagent_runtime
        instance.pending_messages[:0] = [
            ticket.text for ticket in instance.steering_tickets
        ]
        instance.steering_tickets.clear()
        runtime.publish_result(instance)
        if (
            instance.pending_messages
            and instance.state == SubAgentState.COMPLETED
            and not instance.cancel_requested
        ):
            cls._submit_subagent(
                tool, run_context, instance=instance, image_urls_prepared=True
            )
        await runtime.checkpoint()
        if runtime.store is not None and runtime.store.closing:
            return
        if runtime.wakeup_task is None or runtime.wakeup_task.done():
            task = asyncio.create_task(cls._dispatch_subagent_results(run_context))
            runtime.wakeup_task = task
            active_event_registry.register_background_task(event, task)

    @classmethod
    async def _dispatch_subagent_results(cls, run_context):
        """Reconcile saved receipts and enqueue one main turn through its normal queue.

        Args:
            run_context: Parent identity and the plugin-owned conversation runtime.
        """
        root = run_context.context
        runtime = root.subagent_runtime
        signal = active_event_registry.get_background_stop_signal(root.event)
        queued = False
        marked = False
        try:
            await runtime.parent_idle.wait()
            async with session_lock_manager.acquire_lock(root.event.unified_msg_origin):
                if signal.is_set() or runtime.wakeup_queued:
                    return
                if runtime.parent_context is not None:
                    root = runtime.parent_context.context
                signal = active_event_registry.get_background_stop_signal(root.event)
                if signal.is_set():
                    return
                current_cid = (
                    await root.context.conversation_manager.get_curr_conversation_id(
                        root.event.unified_msg_origin
                    )
                )
                if current_cid != root.conversation_id:
                    return
                conversation = await root.context.conversation_manager.get_conversation(
                    root.event.unified_msg_origin, root.conversation_id
                )
                if conversation is None:
                    return
                if runtime.store is not None:
                    await runtime.store.reconcile(runtime, conversation.history)
                if not runtime._pending_results:
                    return
                session = MessageSession.from_str(root.event.unified_msg_origin)
                event = CronMessageEvent(
                    context=root.context,
                    session=session,
                    message_type=session.message_type,
                    message="Delegated tasks have finished. Review their results and continue the original task.",
                    extras={
                        "_subagent_wakeup": runtime.storage_scope,
                        "_background_stop_signal": signal,
                        "_api_key_allow_admin_role": root.event.get_extra(
                            "_api_key_allow_admin_role"
                        ),
                    },
                )
                event.message_obj.sender = copy.copy(root.event.message_obj.sender)
                event.message_obj.group = copy.copy(root.event.message_obj.group)
                event.plugins_name = copy.copy(root.event.plugins_name)
                config = root.context.get_config(umo=root.event.unified_msg_origin)
                if root.event.role == "admin" and str(event.get_sender_id()) in [
                    str(item) for item in config.get("admins_id", [])
                ]:
                    event.role = "admin"
                runtime.wakeup_queued = True
                marked = True
                await root.context.get_event_queue().put(event)
                queued = True
        except Exception:
            logger.exception(
                "Failed to enqueue subagent results; retaining them for the parent"
            )
        finally:
            if marked and not queued:
                runtime.wakeup_queued = False
            if runtime.wakeup_task is asyncio.current_task():
                runtime.wakeup_task = None
