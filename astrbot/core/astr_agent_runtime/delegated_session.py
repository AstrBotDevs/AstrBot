"""A delegated native session with its own configuration and committed history."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

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
    AgentSessionRef,
    AgentTurn,
)
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime.execution import create_native_runner
from astrbot.core.astr_agent_runtime.main_agent.builder import MainAgentBuildResult
from astrbot.core.astr_agent_runtime.main_agent.config import MainAgentBuildConfig
from astrbot.core.astr_agent_runtime.main_agent.persona import apply_skills
from astrbot.core.astr_agent_runtime.session import NativeAgentSession
from astrbot.core.astr_agent_runtime.subagents.caller import (
    AgentCaller,
    DelegatedAgentInput,
)
from astrbot.core.astr_agent_runtime.subagents.context import SubAgentContext
from astrbot.core.astr_agent_runtime.tools.message_tools import SendMessageToUserTool
from astrbot.core.db.po import Conversation
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.star import star_map

if TYPE_CHECKING:
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
    runtime_config: dict = field(default_factory=dict)
    token_usage: int = 0


class DelegatedAgentSession(NativeAgentSession):
    """A private native conversation; scheduling is inherited from AgentSession."""

    is_main = False

    def __init__(
        self, runtime: AstrAgentRuntime, conversation: NativeConversation, umo: str
    ) -> None:
        super().__init__(runtime, conversation.conversation_id, umo)
        self.runtime = runtime
        self.db = runtime.context._db
        self.conversation = conversation

    @classmethod
    async def create(
        cls,
        runtime: AstrAgentRuntime,
        umo: str,
        input: DelegatedAgentInput,
        options: dict,
    ) -> DelegatedAgentSession:
        """Snapshot native configuration and its capabilities when a child session opens.

        Args:
            runtime: Owner supplying storage and application services.
            umo: Owner message source.
            input: Initial caller and its currently delegable capabilities.
            options: Validated runtime configuration and display metadata.

        Returns:
            A new persisted private session with no model work started.

        Raises:
            ValueError: If the caller, persona or configured provider is unavailable.
        """
        caller = input.caller
        if caller is None:
            raise ValueError("A delegated session requires an owning caller")
        overrides = runtime.normalize_config(options.get("config", {}), delegated=True)
        config = runtime.normalize_config(
            caller.context.get_config(umo=umo).get("agent", {}).get("config", {})
        )
        explicit_persona_id = overrides["persona"]["persona_id"]
        if explicit_persona_id:
            config["persona"]["persona_id"] = explicit_persona_id
        elif isinstance(
            resolved_persona_id := caller.event.get_extra("_trace_persona_id"), str
        ):
            config["persona"]["persona_id"] = resolved_persona_id
        if overrides["model"]["provider_id"]:
            config["model"]["provider_id"] = overrides["model"]["provider_id"]
        persona_config = config["persona"]
        instructions = (
            persona_config.get("system_prompt")
            or "Complete the delegated task. Follow its constraints and return a concise result with evidence and unresolved limitations."
        )
        tools = persona_config.get("tools")
        dialogs = []
        skills = persona_config.get("skills")
        persona_id = persona_config.get("persona_id")
        if persona_id:
            persona = caller.context.persona_manager.get_persona_v3_by_id(persona_id)
            if persona is None and explicit_persona_id:
                raise ValueError(f"Agent persona is unavailable: {persona_id}")
            if persona is not None:
                instructions = str(persona.get("prompt", "")).strip() or instructions
                tools = persona.get("tools")
                dialogs = persona.get("_begin_dialogs_processed") or []
                skills = persona.get("skills")
        provider_id = overrides["model"]["provider_id"]
        if tools is not None:
            tools = (
                [str(name).strip() for name in tools if str(name).strip()]
                if isinstance(tools, list)
                else []
            )
        provider_id = provider_id or await caller.context.get_current_chat_provider_id(
            caller.scope.umo
        )
        config["model"]["provider_id"] = provider_id
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
            runtime_config=config,
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
        await session._commit_history([], None)
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
                runtime_config=data.get("runtime_config", {"misc": {"max_steps": 30}}),
                initial_dialogs=bind_checkpoint_messages(
                    data.get("initial_dialogs", [])
                ),
                messages=bind_checkpoint_messages(data["messages"]),
                token_usage=data.get("token_usage", 0),
            ),
            umo,
        )

    async def _commit_history(
        self, history: list[dict], token_usage: int | None
    ) -> None:
        """Write the shared history policy's output with private session metadata.

        Args:
            history: Canonical messages already filtered by native history handling.
            token_usage: Latest context usage, if available.
        """
        conversation = self.conversation
        await self.db.insert_preference_or_update(
            "subagent_native",
            "conversation",
            self.id,
            {
                "umo": self.umo,
                "provider_id": conversation.provider_id,
                "instructions": conversation.instructions,
                "tools": conversation.tools,
                "skills": conversation.skills,
                "runtime_config": conversation.runtime_config,
                "initial_dialogs": [
                    {
                        **message.model_dump(),
                        **({"_no_save": True} if message._no_save else {}),
                    }
                    for message in conversation.initial_dialogs
                ],
                "messages": history,
                "token_usage": token_usage or 0,
            },
        )
        conversation.messages = bind_checkpoint_messages(history)
        conversation.token_usage = token_usage or 0

    def _build_config(self, turn: AgentTurn) -> MainAgentBuildConfig:
        """Apply the immutable native configuration snapshot to this turn.

        Args:
            turn: Accepted delegated input.

        Returns:
            Native execution settings shared with ordinary conversations.
        """
        effective = {
            **self.runtime.context.get_config(umo=self.umo),
            "agent": {"runtime": "astrbot", "config": self.conversation.runtime_config},
        }
        config = MainAgentBuildConfig.from_config(effective)
        config.streaming_response = False
        return config

    async def _prepare_turn(
        self, turn: AgentTurn, build_config: MainAgentBuildConfig
    ) -> MainAgentBuildResult:
        """Prepare delegated input and bound capabilities for the native executor.

        Args:
            turn: One delegated input and its output sink.
            build_config: Effective native execution settings.

        Returns:
            Prepared runner and request for the shared execution lifecycle.

        Raises:
            ValueError: If delegated caller metadata is missing.
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
                available.add_tool(available.get_tool(tool.name) or tool)
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
                or tool.name not in caller.tools.names()
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
        from astrbot.core.provider import Provider

        from .main_agent.persona import apply_safety_instructions

        provider = await caller.context.provider_manager.get_provider_by_id(
            conversation.provider_id
        )
        if not isinstance(provider, Provider):
            raise ValueError(
                f"Agent provider is unavailable: {conversation.provider_id}"
            )
        instructions = ProviderRequest(
            system_prompt=f"<persona_instructions>\n{conversation.instructions}\n</persona_instructions>\n"
        )
        await apply_skills(
            instructions,
            config.get("provider_settings", {}),
            caller.context,
            caller.event,
            allowed_skills=conversation.skills,
            plugin_skills=request.plugin_skills,
        )
        if build_config.llm_safety_mode:
            apply_safety_instructions(build_config, instructions)
        context = SubAgentContext(
            _runtime=self.runtime,
            context=caller.context,
            event=caller.event,
            subagent_scope=caller.scope,
            is_subagent=True,
            permissions=request.permissions,
            plugin_tools=request.plugin_tools,
            plugin_skills=request.plugin_skills,
            agent_session=AgentSessionRef("astrbot", self.id),
        )
        req = ProviderRequest(
            system_prompt=instructions.system_prompt,
            contexts=[
                {
                    **message.model_dump(),
                    **({"_no_save": True} if message._no_save else {}),
                }
                for message in history
            ],
            func_tool=tools if tools.tools else None,
            conversation=Conversation(
                platform_id=caller.event.get_platform_id(),
                user_id=self.umo,
                cid=self.id,
                history="[]",
                token_usage=conversation.token_usage,
            ),
        )
        runner = await create_native_runner(
            caller.context, provider, req, build_config, context
        )
        return MainAgentBuildResult(
            agent_runner=runner, provider_request=req, provider=provider
        )

    async def history(self) -> list[dict]:
        """Read the last complete persisted conversation state.

        Returns:
            Serialized messages including portable image data.
        """
        conversation = self.conversation
        return dump_messages_with_checkpoints(conversation.messages)
