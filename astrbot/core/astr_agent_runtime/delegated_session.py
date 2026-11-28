"""A delegated native session with its own configuration and committed history."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

from astrbot.core.agent.input import ImageInput, InputComponent, format_input_content
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.message import (
    ContentPart,
    ImageURLPart,
    Message,
    TextPart,
    dump_messages,
    load_messages,
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
from astrbot.core.capabilities import CapabilitySelection, resolve_tools, tool_ref
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
                resolver = SendMessageToUserTool()
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
    """An open child conversation with resolved settings and committed history."""

    conversation_id: str
    provider_id: str
    instructions: str
    tools: CapabilitySelection
    skills: CapabilitySelection = None
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
        self.store = runtime.context._db.conversation_store
        self.conversation = conversation

    @classmethod
    async def open(
        cls,
        runtime: AstrAgentRuntime,
        umo: str,
        input: DelegatedAgentInput,
        options: dict,
        *,
        session_id: str | None = None,
    ) -> DelegatedAgentSession:
        """Open a child conversation with current settings and persisted history.

        Args:
            runtime: Owner supplying storage and application services.
            umo: Owner message source.
            input: Current caller and its delegable capabilities.
            options: Runtime configuration and display metadata for a new child.
            session_id: Existing registered conversation to restore, if any.

        Returns:
            An open child session, ready to accept a turn.

        Raises:
            ValueError: If ownership or the requested configuration is invalid.
        """
        caller = input.caller
        if caller is None or caller.scope.umo != umo:
            raise ValueError("A delegated session requires an owning caller")
        store = runtime.context._db.conversation_store
        overrides = options.get("config", {})
        history = []
        token_usage = 0
        if session_id is not None:
            agent = runtime.subagents.store.find_native_conversation(umo, session_id)
            loaded = await store.read_for_execution(session_id) if agent else None
            if agent is None or loaded is None or loaded[0].user_id != umo:
                raise ValueError(
                    f"Native agent conversation not found or inaccessible: {session_id}"
                )
            record, _ = loaded
            history = load_messages(record.content or [])
            token_usage = record.token_usage
            config_id = agent.options.get("config_id")
            overrides = {}
            if config_id is not None:
                selected = await runtime.agent_configs.get(config_id)
                if not selected.enabled or selected.runtime != "astrbot":
                    raise ValueError(
                        f"Native agent configuration is unavailable: {config_id}"
                    )
                overrides = selected.config
        overrides = runtime.normalize_config(overrides, delegated=True)
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
        if tools is not None and not isinstance(tools, list):
            tools = []
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
            conversation_id=session_id or uuid4().hex,
            provider_id=provider_id,
            instructions=instructions,
            tools=tools,
            skills=skills,
            runtime_config=config,
            messages=history,
            token_usage=token_usage,
            initial_dialogs=load_messages(
                [
                    {**item.model_dump(), "_no_save": item._no_save}
                    if isinstance(item, Message)
                    else copy.deepcopy(item)
                    for item in dialogs
                ]
            ),
        )
        return cls(runtime, conversation, umo)

    async def _commit_history(
        self, history: list[dict], token_usage: int | None
    ) -> None:
        """Commit the filtered history to the private conversation journal.

        Args:
            history: Canonical messages already filtered by native history handling.
            token_usage: Latest context usage, if available.
        """
        conversation = self.conversation
        await self.store.append(
            self.id,
            [
                {
                    "type": "conversation.updated",
                    "payload": {"changes": {}, "token_usage": token_usage or 0},
                }
            ],
            history=history,
            origin="system",
            link_display=False,
        )
        conversation.messages = load_messages(history)
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
            or request.caller.scope.umo != self.umo
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

        manager = caller.context.get_llm_tool_manager()
        plugin_tools = request.plugin_tools
        if plugin_tools is None:
            plugin_tools = manager.get_full_tool_set()
        parent_plugin_tools = caller.agent_context.plugin_tools
        selected = resolve_tools(conversation.tools, caller.tools.tools)
        registered_by_ref = {tool_ref(tool): tool for tool in plugin_tools}
        tools = ToolSet()
        for tool in selected:
            if (
                tool is None
                or tool.name in SUBAGENT_TOOL_NAMES
                or tool.name.startswith("transfer_to_")
            ):
                continue
            # Refresh plugin and MCP instances while keeping the runtime
            # instance the parent selected, including same-named variants.
            if parent_plugin_tools is None:
                tool = registered_by_ref.get(tool_ref(tool)) or tool
            elif (
                parent_plugin_tools.get_tool(tool.name) is tool
                or tool.handler is not None
                or tool.handler_module_path
                or isinstance(tool, MCPTool)
                or manager.get_func(tool.name) is tool
            ):
                tool = registered_by_ref.get(tool_ref(tool))
            if tool is None or not tool.active:
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
            send_to_user=request.send_to_user,
            _output_turn=caller.agent_context._output_turn
            if not request.send_to_user
            else None,
        )
        req = ProviderRequest(
            system_prompt=instructions.system_prompt,
            contexts=dump_messages(history, include_temporary=True),
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
        return dump_messages(conversation.messages)
