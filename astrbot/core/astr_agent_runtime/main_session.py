"""Prepare ordinary conversation input for the shared native session executor."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot.core.agent.input import ImageInput, format_input_content
from astrbot.core.agent.message import TextPart
from astrbot.core.agent.runtime import AgentInput, AgentTurn
from astrbot.core.agent_input import CollectedInput, collect_initial_request
from astrbot.core.astr_agent_runtime.main_agent.config import MainAgentBuildConfig
from astrbot.core.llm_error_messages import LLM_ERROR_MESSAGE_EXTRA_KEY
from astrbot.core.message.components import Reply

from .session import NativeAgentSession

if TYPE_CHECKING:
    from astrbot.core.astr_agent_runtime.main_agent.builder import MainAgentBuildResult
    from astrbot.core.provider.entities import ProviderRequest


@dataclass
class MainAgentInput(AgentInput):
    """Native input with host preprocessing and per-turn settings."""

    build_config: MainAgentBuildConfig | None = None
    request: ProviderRequest | None = None
    admit: Callable[[], Awaitable[bool]] | None = None


class MainAgentSession(NativeAgentSession):
    """Bind Core's prepared input to an ordinary native conversation."""

    async def _admit_turn(self, turn: AgentTurn) -> bool:
        """Run Core admission after serialization and before configuration resolution.

        Args:
            turn: Ordinary or programmatic main-agent input.

        Returns:
            Whether Core permits the prepared input to run.
        """
        input = turn.input
        return (
            not isinstance(input, MainAgentInput)
            or input.admit is None
            or await input.admit()
        )

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
        return super()._build_config(turn)

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
        conversation = await context.conversation_manager.get_conversation(
            self.umo, self.id
        )
        if conversation is None:
            raise ValueError("The bound agent conversation no longer exists")
        req = input.request if isinstance(input, MainAgentInput) else None
        explicit = req is not None or event.get_extra("provider_request") is not None
        if (
            req is None
            and input.content is not None
            and event.get_extra("provider_request") is None
        ):
            req = ProviderRequest(prompt=format_input_content(input.content))
            req.image_urls = [
                item.source for item in input.content if isinstance(item, ImageInput)
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
        # Explicit unbound SDK/plugin contexts keep their established semantics.
        # Ordinary turns always reload this session's history after execution admission.
        if not explicit or req.conversation is not None:
            req.conversation = conversation
            req.contexts = json.loads(conversation.history)
        if not explicit:
            event.set_extra("provider_request", req)
        collected = CollectedInput(
            req, quote_ref, quote_refs, parse_quoted=parse_quoted, source_paths=sources
        )
        result = await build_main_agent(
            event=event,
            plugin_context=context,
            config=build_config,
            req=req,
            collected_input=collected,
            plugin_tools=input.plugin_tools,
            plugin_skills=input.plugin_skills,
        )
        if result is None:
            error = event.get_extra(LLM_ERROR_MESSAGE_EXTRA_KEY)
            if error:
                raise RuntimeError(str(error))
            return None
        return result
