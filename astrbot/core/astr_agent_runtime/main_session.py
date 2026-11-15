"""Prepare ordinary conversation input for the shared native session executor."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from copy import copy
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.agent.input import (
    FileInput,
    ImageInput,
    PlainInput,
    format_input_content,
)
from astrbot.core.agent.message import (
    Message,
    TextPart,
    dump_messages,
    merge_user_messages,
)
from astrbot.core.agent.runtime import AgentInput, AgentTurn, InputReceipt, TurnStatus
from astrbot.core.agent_input import (
    CollectedInput,
    PreparedRequest,
    append_system_reminders,
    prepare_input_content,
)
from astrbot.core.astr_agent_runtime.main_agent.config import MainAgentBuildConfig
from astrbot.core.astr_agent_runtime.main_agent.request import collect_initial_request
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.llm_error_messages import LLM_ERROR_MESSAGE_EXTRA_KEY
from astrbot.core.message.components import Reply
from astrbot.core.utils.event_id import new_event_id

from .session import NativeAgentSession

if TYPE_CHECKING:
    from astrbot.core.astr_agent_runtime.main_agent.builder import MainAgentBuildResult
    from astrbot.core.provider.entities import ProviderRequest

    from .runtime import AstrAgentRuntime


@dataclass
class MainAgentInput(AgentInput):
    """Native input with host preprocessing and per-turn settings."""

    build_config: MainAgentBuildConfig | None = None
    request: ProviderRequest | None = None


class MainAgentSession(NativeAgentSession):
    """Bind Core's prepared input to an ordinary native conversation."""

    def __init__(self, runtime: AstrAgentRuntime, session_id: str, umo: str) -> None:
        super().__init__(runtime, session_id, umo)
        self._input_tasks: set[asyncio.Task] = set()
        self._input_lock = asyncio.Lock()
        self._deferred_inputs: list[AgentInput] = []
        self._fallback_outputs: set[asyncio.Task] = set()
        self._steer_receipts: dict[str, InputReceipt] = {}
        self._accepted_inputs: dict[str, AgentInput] = {}
        self._input_turns: dict[str, AgentTurn] = {}
        self._prepared_inputs: dict[str, PreparedRequest] = {}

    async def _persist_input(
        self, input: AgentInput, *, steering: bool = False
    ) -> bool:
        """Store a received user message independently of its execution position.

        Args:
            input: Authorized input, retaining its message event ID across retries.
            steering: Preserve the text-reference contract for mid-turn input.

        Returns:
            Whether this session supports the durable conversation journal.
        """
        manager = self.runtime.context.conversation_manager
        if not isinstance(manager, ConversationManager):
            return False
        if input.message_event_id is None:
            input.message_event_id = new_event_id()
        from astrbot.core.astr_agent_runtime.main_agent import providers
        from astrbot.core.provider.entities import ProviderRequest

        if await manager.db.conversation_store.received_messages(
            self.id, [input.message_event_id]
        ):
            return True
        config = (
            input.build_config if isinstance(input, MainAgentInput) else None
        ) or MainAgentBuildConfig.from_config(
            self.runtime.context.get_config(umo=self.umo)
        )
        paths: list[str] = []
        if steering:
            text = (
                format_input_content(input.content)
                if input.content is not None
                else input.event.get_message_str() or input.event.get_message_outline()
            )
            req = ProviderRequest(prompt=text)
            req.conversation = manager.to_legacy_conversation(
                await manager.db.get_conversation_by_id(self.id)
            )
            append_system_reminders(
                input.event, req, config.provider_settings, config.timezone
            )
            prepared = PreparedRequest(req)
        else:
            req = input.request if isinstance(input, MainAgentInput) else None
            req = req or input.event.get_extra("provider_request")
            explicit = req is not None
            if req is not None:
                req = copy(req)
                req.extra_user_content_parts = list(req.extra_user_content_parts)
                req.image_urls = list(req.image_urls)
                req.audio_urls = list(req.audio_urls)
            if (
                not explicit
                and input.content is not None
                and any(
                    isinstance(part, (ImageInput, FileInput)) for part in input.content
                )
            ):
                req = ProviderRequest(prompt=format_input_content(input.content))
                req.image_urls = [
                    part.source
                    for part in input.content
                    if isinstance(part, ImageInput)
                ]
            quote_refs: set[str] = set()
            parse_quoted = req is None or (
                any(isinstance(part, Reply) for part in input.event.message_obj.message)
                and not any(
                    isinstance(part, TextPart)
                    and part.text.startswith("<Quoted Message>\n")
                    for part in req.extra_user_content_parts
                )
            )
            req, quote_ref = await collect_initial_request(
                input.event,
                self.runtime.context,
                config,
                req=req,
                quoted_image_refs=quote_refs,
                materialized_paths=paths,
            )
            if req is None:
                raise ValueError("Input was rejected during preparation")
            if input.content is not None and not explicit:
                req.prompt = format_input_content(input.content)
            if not explicit or req.conversation is not None:
                conversation = await manager.db.get_conversation_by_id(self.id)
                req.conversation = manager.to_legacy_conversation(conversation)
            provider = await providers.select_chat_provider(
                input.event, self.runtime.context
            )
            if provider is not None:
                prepared = await prepare_input_content(
                    input.event,
                    self.runtime.context,
                    config,
                    provider,
                    req,
                    collected_request=parse_quoted,
                    quote_image_ref=quote_ref,
                    quoted_image_refs=quote_refs,
                )
                if prepared is None:
                    raise ValueError("Input was rejected during preparation")
            else:
                append_system_reminders(
                    input.event, req, config.provider_settings, config.timezone
                )
                prepared = PreparedRequest(req)
        message = await req.assemble_context()
        # Capture generated reminders and portable media exactly once, before
        # accepting ownership. Later execution binds fresh history to this input.
        self._prepared_inputs[input.message_event_id] = prepared
        await manager.db.conversation_store.append(
            self.id,
            [
                {
                    "event_id": input.message_event_id,
                    "type": "message.appended",
                    "payload": {
                        "message": message,
                        "delivery": {
                            "role": input.permissions.role.value,
                            "send_to_user": input.send_to_user,
                            "plugins": input.event.plugins_name,
                            "content": [part.model_dump() for part in input.content]
                            if input.content is not None
                            else None,
                        },
                    },
                }
            ],
            link_display=False,
        )
        for path in paths:
            input.event.untrack_temporary_local_file(path)
        return True

    async def _discard_inputs(self, message_ids: list[str]) -> None:
        """Discard still-pending input without changing immutable receipt records.

        Args:
            message_ids: Received inputs to discard after cancellation or refusal.
        """
        from astrbot.core.db.conversation import ConversationConflictError

        store = self.runtime.context.conversation_manager.db.conversation_store
        pending = await store.pending_messages(self.id)
        drafts = [
            {"type": "message.discarded", "payload": {"source_event_id": item.event_id}}
            for item in pending
            if item.event_id in message_ids
        ]
        if drafts:
            try:
                await store.append(self.id, drafts, link_display=False)
            except ConversationConflictError:
                # A concurrent consumer may have won before cancellation acquired
                # the write lock. Never label an already-consumed input discarded.
                if any(
                    item.event_id in message_ids
                    for item in await store.pending_messages(self.id)
                ):
                    raise
        for message_id in message_ids:
            self._prepared_inputs.pop(message_id, None)

    async def run_turn(
        self,
        input: AgentInput,
        *,
        admit: Callable[[], Awaitable[bool]] | None = None,
    ) -> AgentTurn:
        """Persist queued input before handing ownership to the execution task.

        Args:
            input: Independently authorized user input.
            admit: Core admission check performed when execution starts.

        Returns:
            Scheduled turn, or the existing handle for a repeated submission.
        """
        if self.closed or input.event.unified_msg_origin != self.umo:
            raise ValueError("Agent session is closed or input belongs elsewhere")
        async with self._input_lock:
            existing = self._input_turns.get(input.message_event_id)
            if existing is not None:
                return existing
            durable = await self._persist_input(input)
            if durable:
                pending = await self.runtime.context.conversation_manager.db.conversation_store.pending_messages(
                    self.id
                )
                if not any(item.event_id == input.message_event_id for item in pending):
                    raise ValueError(
                        "This message has already been consumed or discarded"
                    )

            async def admission() -> bool:
                accepted = admit is None or await admit()
                if not accepted and durable:
                    await self._discard_inputs([input.message_event_id])
                return accepted

            turn = await super().run_turn(input, admit=admission)
            if durable:
                self._input_turns[input.message_event_id] = turn
                turn._task.add_done_callback(
                    lambda _: self._input_turns.pop(input.message_event_id, None)
                )
            return turn

    def steer_turn(self, turn: AgentTurn, input: AgentInput) -> InputReceipt | None:
        """Accept steering durably before allowing the runner to consume it.

        Args:
            turn: Current execution whose safe boundary may receive the message.
            input: Independently authorized additional input.

        Returns:
            Receipt confirming durable ownership. Accepted late input becomes a
            follow-up; storage failures raise through the receipt instead of
            falsely declaring the message safe to resubmit.
        """
        if not isinstance(
            self.runtime.context.conversation_manager, ConversationManager
        ):
            return super().steer_turn(turn, input)
        if self._runner is None or self._runner.done():
            return None
        text = (
            format_input_content(input.content)
            if input.content is not None
            else input.event.get_message_str() or input.event.get_message_outline()
        )
        if not text.strip():
            return None
        if input.message_event_id is None:
            input.message_event_id = new_event_id()
        if input.message_event_id in self._steer_receipts:
            return self._steer_receipts[input.message_event_id]
        receipt = InputReceipt()
        self._steer_receipts[input.message_event_id] = receipt
        runner = self._runner

        async def accept() -> None:
            try:
                await self._persist_input(input, steering=True)
                pending = await self.runtime.context.conversation_manager.db.conversation_store.pending_messages(
                    self.id
                )
                if not any(item.event_id == input.message_event_id for item in pending):
                    receipt.resolve(True)
                    return
                self._accepted_inputs[input.message_event_id] = input
                stored = await self.runtime.context.conversation_manager.db.conversation_store.received_messages(
                    self.id, [input.message_event_id]
                )
                ticket = runner.follow_up(message_text=text)
                if ticket is not None:
                    ticket.message_event_id = input.message_event_id
                    ticket.message = stored[0].payload["message"]
                    self._prepared_inputs.pop(input.message_event_id, None)
                    self._steering.append((ticket, receipt))
                else:
                    self._deferred_inputs.append(input)
                receipt.resolve(True)
            except Exception as exc:
                self._steer_receipts.pop(input.message_event_id, None)
                if not receipt.done():
                    receipt._future.set_exception(exc)

        task = asyncio.create_task(accept())
        self._input_tasks.add(task)
        task.add_done_callback(self._input_tasks.discard)
        return receipt

    async def _finish_turn(
        self, turn: AgentTurn, result: MainAgentBuildResult, status: TurnStatus | None
    ) -> None:
        """Settle received steering without transferring durable inputs back.

        Args:
            turn: Execution being finalized.
            result: Prepared native runner and persistence writer.
            status: Execution outcome, or None on failure.
        """
        if self._input_tasks:
            await asyncio.gather(*tuple(self._input_tasks))
        pending = [
            self._accepted_inputs[ticket.message_event_id]
            for ticket, _ in self._steering
            if ticket.message_event_id and not ticket.consumed
        ]
        pending.extend(self._deferred_inputs)
        self._deferred_inputs = []
        self._accepted_inputs.clear()
        await super()._finish_turn(turn, result, status)
        self._steer_receipts.clear()
        stopped = (
            turn.cancellation_requested
            or turn._stop_task is not None
            or turn.input.event.is_stopped()
        )
        if stopped and turn.input.message_event_id:
            await self._discard_inputs(
                [
                    turn.input.message_event_id,
                    *[item.message_event_id for item in pending],
                ]
            )
        elif status == TurnStatus.COMPLETED:
            from astrbot.core.agent_output import deliver_agent_turn

            def delivered(task: asyncio.Task) -> None:
                self._fallback_outputs.discard(task)
                if not task.cancelled() and task.exception() is not None:
                    logger.error(
                        "Could not deliver deferred input output: %s", task.exception()
                    )

            for input in pending:
                # Captured platform events have already finished their pipeline.
                # Give the follow-up a fresh output scope while retaining the
                # original message identity and captured capabilities.
                content = input.content or [
                    PlainInput.model_construct(
                        text=input.event.get_message_str()
                        or input.event.get_message_outline()
                    )
                ]
                event = self.runtime.context.agent._make_event(
                    self.umo, content, input.event
                )
                event.plugins_name = input.event.plugins_name
                follow_up = await self.run_turn(replace(input, event=event))
                if input.send_to_user:
                    task = asyncio.create_task(
                        deliver_agent_turn(self.runtime.context, follow_up)
                    )
                    self._fallback_outputs.add(task)
                    task.add_done_callback(delivered)

    async def close(self) -> None:
        """Settle execution and the output observers of internally queued turns."""
        await super().close()
        if self._fallback_outputs:
            await asyncio.gather(*tuple(self._fallback_outputs), return_exceptions=True)

    async def cancel_turn(self, turn: AgentTurn) -> None:
        """Persist an explicit cancellation even when the input is still queued.

        Args:
            turn: Exact execution whose accepted input must not be recovered.
        """
        if turn.input.message_event_id is not None:
            await self._discard_inputs([turn.input.message_event_id])
        await super().cancel_turn(turn)

    def _build_config(self, turn: AgentTurn) -> MainAgentBuildConfig:
        """Resolve per-input overrides or the current profile settings.

        Args:
            turn: Input about to execute.

        Returns:
            Effective native execution settings.
        """
        input = turn.input
        if isinstance(input, MainAgentInput) and input.build_config is not None:
            return input.build_config
        config = super()._build_config(turn)
        return replace(
            config,
            streaming_response=turn.input.streaming
            if turn.input.streaming is not None
            else config.streaming_response,
            call_request_hook=True,
            validate_provider_endpoint=True,
        )

    async def _prepare_turn(
        self, turn: AgentTurn, build_config: MainAgentBuildConfig
    ) -> MainAgentBuildResult | None:
        """Bind committed native history before building capabilities and hooks.

        Args:
            turn: Input admitted under this conversation's execution lock.
            build_config: Native settings resolved for this execution.

        Returns:
            Prepared native execution, or None when input or a hook rejects it.
        """
        from astrbot.core.astr_agent_runtime.main_agent.builder import build_main_agent
        from astrbot.core.provider.entities import ProviderRequest

        input = turn.input
        event = input.event
        context = self.runtime.context
        manager = context.conversation_manager
        loaded = await manager.db.conversation_store.read_for_execution(self.id)
        if loaded is None:
            raise ValueError("The bound agent conversation no longer exists")
        conversation, snapshot = loaded
        stored_inputs = (
            await manager.db.conversation_store.received_messages(
                self.id, [input.message_event_id]
            )
            if input.message_event_id
            else []
        )
        prepared = self._prepared_inputs.pop(input.message_event_id, None)
        if stored_inputs:
            req = prepared.request if prepared is not None else ProviderRequest()
            explicit = req.conversation is None and prepared is not None
            # Reconstruct the prepared user content from the receipt even after
            # restart, without regenerating its timestamp or prompt prefix.
            saved = Message.model_validate(stored_inputs[0].payload["message"])
            parts = (
                [TextPart(text=saved.content)]
                if isinstance(saved.content, str)
                else list(saved.content or [])
            )
            req.prompt = (
                parts.pop(0).text if parts and isinstance(parts[0], TextPart) else ""
            )
            req.extra_user_content_parts = []
            req.image_urls = []
            req.audio_urls = []
            for part in parts:
                if part.type == "image_url":
                    req.image_urls.append(part.image_url.url)
                elif part.type == "audio_url":
                    req.audio_urls.append(part.audio_url.url)
                else:
                    req.extra_user_content_parts.append(part)
            prepared = PreparedRequest(req) if prepared is None else prepared
            collected = None
        else:
            req = input.request if isinstance(input, MainAgentInput) else None
            explicit = (
                req is not None or event.get_extra("provider_request") is not None
            )
            # Portable attachments replace source media; a text override retains it.
            if (
                not explicit
                and input.content is not None
                and any(
                    isinstance(part, (ImageInput, FileInput)) for part in input.content
                )
            ):
                req = ProviderRequest(prompt=format_input_content(input.content))
                req.image_urls = [
                    part.source
                    for part in input.content
                    if isinstance(part, ImageInput)
                ]
            parse_quoted = req is None or (
                any(isinstance(part, Reply) for part in event.message_obj.message)
                and not any(
                    isinstance(part, TextPart)
                    and part.text.startswith("<Quoted Message>\n")
                    for part in req.extra_user_content_parts
                )
            )
            quote_refs: set[str] = set()
            sources: list[str] = []
            req, quote_ref = await collect_initial_request(
                event,
                context,
                build_config,
                req=req,
                quoted_image_refs=quote_refs,
                materialized_paths=sources,
            )
            if req is None:
                return None
            if input.content is not None and not explicit:
                req.prompt = format_input_content(input.content)
            collected = CollectedInput(
                req,
                quote_ref,
                quote_refs,
                parse_quoted=parse_quoted,
                source_paths=sources,
            )
        # Explicit unbound SDK/plugin contexts keep their established semantics.
        # Ordinary turns always reload this session's history after execution admission.
        if not explicit or req.conversation is not None:
            req.conversation = manager.to_legacy_conversation(conversation)
            req.contexts = []
            outstanding = {}
            for message in [*(conversation.content or []), {"role": "user"}]:
                if message["role"] != "tool" and outstanding:
                    req.contexts.extend(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": "Execution was interrupted; the result is unavailable. Do not assume the operation did not take effect.",
                        }
                        for call_id in outstanding
                    )
                    outstanding.clear()
                if message["role"] == "assistant":
                    outstanding.update(
                        (call["id"], call) for call in message.get("tool_calls", [])
                    )
                elif message["role"] == "tool":
                    outstanding.pop(message.get("tool_call_id"), None)
                req.contexts.append(message)
            req.contexts.pop()  # Remove the sentinel used to close an unfinished batch.
        if not explicit:
            event.set_extra("provider_request", req)
        result = await build_main_agent(
            event=event,
            plugin_context=context,
            config=build_config,
            req=req,
            collected_input=collected,
            prepared_input=prepared,
            plugin_tools=input.plugin_tools,
            plugin_skills=input.plugin_skills,
            runtime=self.runtime,
            conversation_snapshot=snapshot if req.conversation is not None else None,
        )
        if result is None:
            error = event.get_extra(LLM_ERROR_MESSAGE_EXTRA_KEY)
            if error:
                raise RuntimeError(str(error))
            return None
        if input.message_event_id and result.conversation_events is not None:
            pending = await manager.db.conversation_store.pending_messages(self.id)
            recovered = [
                item
                for item in pending
                if item.event_id != input.message_event_id
                and (
                    item.event_id not in self._input_turns
                    or self._input_turns[item.event_id].done
                )
                and item.payload["delivery"]["role"] == input.permissions.role.value
                and item.payload["delivery"]["send_to_user"] == input.send_to_user
                and item.payload["delivery"]["plugins"] == event.plugins_name
            ]
            runner = result.agent_runner
            # The prepared current input is last. Insert received, unconsumed
            # text before it; attachment inputs retain their explicit retry path.
            recovered = [
                item
                for item in recovered
                if all(
                    part.get("type") == "plain"
                    for part in (item.payload["delivery"].get("content") or [])
                )
            ]
            # All inputs adopted at this boundary form one user message. Its
            # sources and ordering are reproduced by consecutive consumption events.
            current = runner.run_context.messages[-1]
            runner.run_context.messages[-1] = Message.model_validate(
                merge_user_messages(
                    [
                        *[item.payload["message"] for item in recovered],
                        dump_messages([current], include_temporary=True)[0],
                    ]
                )
            )
            runner._received_message_ids = [
                *[item.event_id for item in recovered],
                input.message_event_id,
            ]
            runner._received_messages = [
                item.payload["message"] for item in [*recovered, *stored_inputs]
            ]
        return result
