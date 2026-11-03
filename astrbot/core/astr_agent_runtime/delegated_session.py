"""A delegated native session with its own configuration and committed history."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

from astrbot import logger
from astrbot.core.agent.input import ImageInput, InputComponent, format_input_content
from astrbot.core.agent.message import (
    ContentPart,
    ImageURLPart,
    Message,
    TextPart,
    bind_checkpoint_messages,
    dump_messages_with_checkpoints,
)
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runtime import (
    AgentInput,
    AgentSession,
    AgentSessionRef,
    AgentTurn,
    InputReceipt,
    TurnResult,
)
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.astr_agent_runtime.hooks import MainAgentHooks
from astrbot.core.astr_agent_runtime.main_agent.persona import apply_skills
from astrbot.core.astr_agent_runtime.tools.message_tools import SendMessageToUserTool
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.star import star_map
from astrbot.core.subagents.caller import (
    AgentCaller,
    DelegatedAgentInput,
)
from astrbot.core.subagents.context import SubAgentContext
from astrbot.core.utils.config_number import coerce_int_config

if TYPE_CHECKING:
    from astrbot.core.agent.runners.tool_loop_agent_runner import (
        FollowUpTicket,
    )
    from astrbot.core.astr_agent_runtime.runner import AgentRunner

    from .runtime import AstrAgentRuntime


async def native_user_message(
    caller: AgentCaller, content: list[InputComponent]
) -> Message:
    """Convert explicit input once into a portable native model message.

    Args:
        caller: Current owner and workspace permissions.
        content: Validated message components.

    Returns:
        One user message, preserving component order and capturing image bytes.
    """
    from astrbot.core.agent.run_context import ContextWrapper

    parts: list[ContentPart] = []
    for item in content:
        if isinstance(item, ImageInput):
            reference = item.source
            if item.path is not None:
                resolver = caller.context.get_llm_tool_manager().get_builtin_tool(
                    SendMessageToUserTool
                )
                reference, _ = await resolver._resolve_path_from_sandbox(
                    ContextWrapper(context=caller.agent_context),
                    item.path,
                    component_type="image",
                )
            parts.append(ImageURLPart(image_url=ImageURLPart.ImageURL(url=reference)))
        else:
            parts.append(TextPart(text=format_input_content([item])))
    data = await ProviderRequest(extra_user_content_parts=parts).assemble_context()
    return Message.model_validate(data)


@dataclass
class NativeConversation:
    """The complete persisted state owned by the native runtime."""

    conversation_id: str
    provider_id: str
    instructions: str
    tools: list[str] | None
    skills: list[str] | None = None
    initial_dialogs: list[Message] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)


@dataclass
class _ActivePrompt:
    """Transient steering handles, never serialized into an agent session."""

    runner: AgentRunner | None = None
    receipts: list[tuple[FollowUpTicket, InputReceipt]] = field(default_factory=list)


class _NativeHooks(MainAgentHooks):
    def __init__(
        self,
        owner: DelegatedAgentSession,
        conversation: NativeConversation,
        active: _ActivePrompt,
        turn: AgentTurn,
    ) -> None:
        self.owner = owner
        self.conversation = conversation
        self.active = active
        self.turn = turn
        self.steps = 0
        self.failure: Exception | None = None

    async def on_agent_begin(
        self, run_context: ContextWrapper[AstrAgentContext]
    ) -> None:
        self.active.runner = run_context.runner
        await super().on_agent_begin(run_context)

    async def on_agent_step_end(
        self, run_context: ContextWrapper[AstrAgentContext]
    ) -> None:
        # Commit only complete tool-call/result pairs. Cancellation can leave the
        # caller-owned runner context incomplete; that context is never reused.
        messages = copy.deepcopy(run_context.messages)
        if messages and messages[0].role == "system":
            messages.pop(0)
        try:
            self.conversation.messages = await self.owner._save(
                self.conversation, messages
            )
            self.steps += 1
            for ticket, receipt in self.active.receipts:
                if ticket.consumed and not receipt.done():
                    receipt.resolve(True)
            self.turn.emit("step_completed", {"steps": self.steps})
        except Exception as exc:
            self.failure = exc
            raise


class DelegatedAgentSession(AgentSession):
    """A private native conversation; scheduling is inherited from AgentSession."""

    def __init__(
        self, runtime: AstrAgentRuntime, conversation: NativeConversation, umo: str
    ) -> None:
        super().__init__(conversation.conversation_id, umo)
        self.runtime = runtime
        self.db = runtime.context._db
        self.conversation = conversation
        self._active_prompt: _ActivePrompt | None = None

    @classmethod
    async def create(
        cls,
        runtime: AstrAgentRuntime,
        umo: str,
        input: DelegatedAgentInput,
        options: dict,
    ) -> DelegatedAgentSession:
        """Snapshot one expert and its capabilities when a child session opens.

        Args:
            runtime: Owner supplying storage and application services.
            umo: Owner message source.
            input: Initial caller and its currently delegable capabilities.
            options: Optional expert, provider and display name.

        Returns:
            A new persisted private session with no model work started.

        Raises:
            ValueError: If the caller, expert or configured provider is unavailable.
        """
        caller = input.caller
        if caller is None:
            raise ValueError("A delegated session requires an owning caller")
        template = options.get("template")
        instructions = "Complete the delegated task. Follow its constraints and return a concise result with evidence and unresolved limitations."
        tools = list(caller.tools.names())
        dialogs = []
        skills = None
        provider_id = options.get("provider_id")
        if template:
            config = caller.context.get_config().get("subagent_orchestrator", {})
            expert = next(
                (
                    item
                    for item in config.get("agents", [])
                    if isinstance(item, dict)
                    and item.get("enabled", True)
                    and str(item.get("name", "")).strip() == template
                ),
                None,
            )
            if expert is None:
                raise ValueError(f"Unknown subagent template: {template}")
            instructions = str(expert.get("system_prompt", "")).strip()
            tools = expert.get("tools", [])
            persona_id = str(expert.get("persona_id") or "").strip()
            persona = (
                caller.context.persona_manager.get_persona_v3_by_id(persona_id)
                if persona_id
                else None
            )
            if persona:
                instructions = str(persona.get("prompt", "")).strip() or instructions
                tools = persona.get("tools")
                dialogs = persona.get("_begin_dialogs_processed") or []
                skills = persona.get("skills")
            elif persona_id:
                logger.warning(
                    "SubAgent persona %s not found, fallback to inline prompt.",
                    persona_id,
                )
            provider_id = (
                provider_id or str(expert.get("provider_id") or "").strip() or None
            )
        if tools is not None:
            tools = (
                [str(name).strip() for name in tools if str(name).strip()]
                if isinstance(tools, list)
                else []
            )
        provider_id = provider_id or await caller.context.get_current_chat_provider_id(
            caller.scope.umo
        )
        available = [
            provider.provider_config["id"]
            for provider in caller.context.get_all_providers()
        ]
        if provider_id not in available:
            raise ValueError(
                f"Unknown or unavailable chat provider: {provider_id}. Available chat provider IDs: {available}"
            )
        conversation = NativeConversation(
            conversation_id=uuid4().hex,
            provider_id=provider_id,
            instructions=instructions,
            tools=tools,
            skills=skills,
            initial_dialogs=bind_checkpoint_messages(
                [
                    {**item.model_dump(), "_no_save": item._no_save}
                    if isinstance(item, Message)
                    else copy.deepcopy(item)
                    for item in dialogs
                ]
            ),
        )
        session = cls(runtime, conversation, umo)
        await session._save(conversation, conversation.messages)
        return session

    @classmethod
    async def restore(
        cls, runtime: AstrAgentRuntime, umo: str, session_id: str
    ) -> DelegatedAgentSession:
        """Restore exact persisted native state without replaying unfinished work.

        Args:
            runtime: Owner of the native persistence service.
            umo: Expected conversation source.
            session_id: Exact private native conversation identity.

        Returns:
            A live session with its committed history.

        Raises:
            ValueError: If the session is missing or belongs to another UMO.
        """
        row = await runtime.context._db.get_preference(
            "subagent_native", "conversation", session_id
        )
        if row is None or row.value.get("umo") != umo:
            raise ValueError(
                f"Native agent conversation not found or inaccessible: {session_id}"
            )
        data = row.value
        return cls(
            runtime,
            NativeConversation(
                conversation_id=session_id,
                provider_id=data["provider_id"],
                instructions=data["instructions"],
                tools=data["tools"],
                skills=data.get("skills"),
                initial_dialogs=bind_checkpoint_messages(
                    data.get("initial_dialogs", [])
                ),
                messages=bind_checkpoint_messages(data["messages"]),
            ),
            umo,
        )

    async def _save(
        self, conversation: NativeConversation, messages: list[Message]
    ) -> list[Message]:
        """Write canonical history independently of the public session store.

        Args:
            conversation: Native configuration owning this history.
            messages: Complete messages to commit.

        Returns:
            The committed history with temporary messages and content removed.
        """
        persisted = dump_messages_with_checkpoints(
            [message for message in messages if not message._no_save]
        )
        await self.db.insert_preference_or_update(
            "subagent_native",
            "conversation",
            conversation.conversation_id,
            {
                "umo": self.umo,
                "provider_id": conversation.provider_id,
                "instructions": conversation.instructions,
                "tools": conversation.tools,
                "skills": conversation.skills,
                "initial_dialogs": [
                    {
                        **message.model_dump(),
                        **({"_no_save": True} if message._no_save else {}),
                    }
                    for message in conversation.initial_dialogs
                ],
                "messages": persisted,
            },
        )
        return bind_checkpoint_messages(persisted)

    async def execute_turn(self, turn: AgentTurn) -> TurnResult:
        """Run explicit child input against this session's committed history.

        Args:
            turn: One delegated input and its output sink.

        Returns:
            Final output after complete-step persistence.

        Raises:
            ValueError: If delegated caller metadata is missing.
            RuntimeError: If the native model returns an error.
        """
        from astrbot.core.astr_agent_runtime.tools.subagent import SUBAGENT_TOOL_NAMES

        request = turn.input
        if (
            not isinstance(request, DelegatedAgentInput)
            or request.caller is None
            or request.content is None
        ):
            raise ValueError("Delegated native input requires an owning caller")
        caller = request.caller

        conversation = self.conversation
        user_message = (
            await native_user_message(caller, request.content)
            if request.sequence == 1
            else Message(role="user", content=format_input_content(request.content))
        )
        history = [
            *(conversation.messages or conversation.initial_dialogs),
            user_message,
        ]
        conversation.messages = await self._save(conversation, history)

        # Resolve tool implementations against fresh permissions each turn; the
        # saved native configuration stores names, never executable objects.
        manager = caller.context.get_llm_tool_manager()
        available = ToolSet(
            tools=list(request.plugin_tools.tools)
            if request.plugin_tools is not None
            else list(manager.get_full_tool_set().tools)
        )
        for tool in caller.tools:
            if request.plugin_tools is None or manager.is_builtin_tool(tool.name):
                available.add_tool(tool)
        selected = (
            available.tools
            if conversation.tools is None
            else [
                available.get_tool(name)
                or (manager.get_func(name) if manager.is_builtin_tool(name) else None)
                for name in conversation.tools
            ]
        )
        tools = ToolSet()
        for tool in selected:
            if (
                tool is None
                or not tool.active
                or tool.name in SUBAGENT_TOOL_NAMES
                or tool.name.startswith("transfer_to_")
            ):
                continue
            metadata = (
                star_map.get(tool.handler_module_path)
                if tool.handler_module_path
                else None
            )
            allowed = caller.event.plugins_name
            if (
                metadata is not None
                and not metadata.reserved
                and allowed is not None
                and allowed != ["*"]
                and metadata.name not in allowed
            ):
                continue
            tools.add_tool(tool)
        config = caller.context.get_config(umo=caller.scope.umo)
        instructions = ProviderRequest(system_prompt=conversation.instructions)
        await apply_skills(
            instructions,
            config.get("provider_settings", {}),
            caller.context,
            caller.event,
            allowed_skills=conversation.skills,
            plugin_skills=request.plugin_skills,
        )
        limits = caller.context.get_config().get("subagent_orchestrator", {})
        max_steps = min(
            coerce_int_config(
                limits.get("max_steps", 30),
                default=30,
                min_value=1,
                field_name="subagent.max_steps",
            ),
            coerce_int_config(
                config.get("agent_runner", {})
                .get("config", {})
                .get("misc", {})
                .get("max_steps", 128),
                default=128,
                min_value=1,
                field_name="agent_runner.config.misc.max_steps",
            ),
        )
        active = _ActivePrompt()
        self._active_prompt = active
        hooks = _NativeHooks(self, conversation, active, turn)
        context = SubAgentContext(
            context=caller.context,
            event=caller.event,
            subagent_scope=caller.scope,
            is_subagent=True,
            permissions=request.permissions,
            plugin_tools=request.plugin_tools,
            plugin_skills=request.plugin_skills,
            agent_session=AgentSessionRef("astrbot", self.id),
        )
        try:
            response = await caller.context.tool_loop_agent(
                event=caller.event,
                chat_provider_id=conversation.provider_id,
                system_prompt=instructions.system_prompt,
                contexts=[
                    {
                        **message.model_dump(),
                        **({"_no_save": True} if message._no_save else {}),
                    }
                    for message in history
                ],
                tools=tools if tools.tools else None,
                max_steps=max_steps,
                run_context=ContextWrapper(context=context),
                agent_hooks=hooks,
            )
            if hooks.failure is not None:
                raise hooks.failure
            if response.role == "err":
                raise RuntimeError(
                    response.completion_text or "Native agent returned an error"
                )
            text = response.completion_text or ""
            chain = response.result_chain or MessageChain().message(text)
            turn.emit("llm_result", {"chain": chain})
            return TurnResult(text=text, chain=chain)
        finally:
            self._active_prompt = None
            for _, receipt in active.receipts:
                if not receipt.done():
                    receipt.resolve(False)

    def steer_turn(self, turn: AgentTurn, input: AgentInput) -> InputReceipt | None:
        """Flatten child steering to text and confirm its persisted consumption.

        Args:
            turn: Exact active execution, checked by the public turn handle.
            input: Explicit follow-up components.

        Returns:
            A consumption receipt, or None when no safe boundary remains.
        """
        active = self._active_prompt
        if active is None or active.runner is None:
            return None
        ticket = active.runner.follow_up(
            message_text=format_input_content(input.content or [])
        )
        if ticket is None:
            return None
        receipt = InputReceipt()
        active.receipts.append((ticket, receipt))
        return receipt

    async def cancel_turn(self, turn: AgentTurn) -> None:
        """Request a native stop for this exact active child execution.

        Args:
            turn: Execution being cancelled.
        """
        active = self._active_prompt
        if (
            self.active_turn is turn
            and active is not None
            and active.runner is not None
        ):
            active.runner.request_stop()

    async def history(self) -> list[dict]:
        """Read the last complete persisted conversation state.

        Returns:
            Serialized messages including portable image data.
        """
        conversation = self.conversation
        return dump_messages_with_checkpoints(conversation.messages)
