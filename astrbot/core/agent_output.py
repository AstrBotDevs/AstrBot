"""Core-owned presentation of runtime output for messaging platforms."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from astrbot.core.agent.runtime import AgentTurn, TurnStatus
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.persona_error_reply import (
    extract_persona_custom_error_message_from_event,
)
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.provider import Provider

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


def _truncate_tool_result(text: str, limit: int = 70) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3]}..."


def _extract_chain_json_data(msg_chain: MessageChain) -> dict | None:
    if not msg_chain.chain:
        return None
    first_comp = msg_chain.chain[0]
    if isinstance(first_comp, Json) and isinstance(first_comp.data, dict):
        return first_comp.data
    return None


def _record_tool_call_name(
    tool_info: dict | None, tool_name_by_call_id: dict[str, str]
) -> None:
    if not isinstance(tool_info, dict):
        return
    tool_call_id = tool_info.get("id")
    tool_name = tool_info.get("name")
    if tool_call_id is None or tool_name is None:
        return
    tool_name_by_call_id[str(tool_call_id)] = str(tool_name)


def _build_tool_call_status_message(tool_info: dict | None) -> str:
    if tool_info:
        return f"🔨 调用工具: {tool_info.get('name', 'unknown')}"
    return "🔨 调用工具..."


def _build_tool_result_status_message(
    msg_chain: MessageChain, tool_name_by_call_id: dict[str, str]
) -> str:
    tool_name = "unknown"
    tool_result = ""

    result_data = _extract_chain_json_data(msg_chain)
    if result_data:
        tool_call_id = result_data.get("id")
        if tool_call_id is not None:
            tool_name = tool_name_by_call_id.pop(str(tool_call_id), "unknown")
        tool_result = str(result_data.get("result", ""))

    if not tool_result:
        tool_result = msg_chain.get_plain_text(with_other_comps_mark=True)
    tool_result = _truncate_tool_result(tool_result, 70)

    status_msg = f"🔨 调用工具: {tool_name}"
    if tool_result:
        status_msg = f"{status_msg}\n📎 返回结果: {tool_result}"
    return status_msg


async def present_turn(
    turn: AgentTurn,
    *,
    streaming: bool,
    stream_to_general: bool = False,
    show_tool_use: bool = True,
    show_tool_call_result: bool = False,
    show_reasoning: bool = False,
    buffer_intermediate_messages: bool = False,
    context: Context | None = None,
) -> AsyncGenerator[MessageChain, None]:
    """Apply Core's output preferences without accessing a runner or its history.

    Args:
        turn: A runtime execution that proceeds independently of this consumer.
        streaming: Whether this platform receives incremental output.
        stream_to_general: Whether only complete messages should be displayed.
        show_tool_use: Whether non-WebChat platforms show tool activity.
        show_tool_call_result: Whether activity includes a short result excerpt.
        show_reasoning: Whether streaming reasoning is displayed.
        buffer_intermediate_messages: Whether non-streaming model replies are combined.
        context: Optional Core provider service for WebChat title generation.

    Yields:
        Platform-neutral message chains ready for the normal delivery pipeline.
    """
    event = turn.input.event
    names: dict[str, str] = {}
    buffered = MessageChain()
    buffer = buffer_intermediate_messages and not streaming and not stream_to_general
    error_emitted = False
    async for output in turn.events():
        if output.type == "turn_finished":
            if buffered.chain:
                yield buffered
            result = output.data
            if result.status == TurnStatus.FAILED and not error_emitted:
                text = (
                    extract_persona_custom_error_message_from_event(event)
                    or f"Error occurred during AI execution.\n{result.error}"
                )
                yield MessageChain().message(text)
            return
        if output.type == "prepared":
            metadata = output.data
            event.set_extra("_agent_chat_model", metadata["chat_provider"]["model"])
            if (
                context is not None
                and event.get_platform_name() == "webchat"
                and not isinstance(event, AgentWakeupEvent)
            ):
                from astrbot.core.pipeline.process_stage.method.agent_sub_stages.webchat import (
                    generate_conversation_title,
                )

                provider = context.get_provider_by_id(metadata["chat_provider"]["id"])
                if isinstance(provider, Provider):
                    asyncio.create_task(
                        generate_conversation_title(
                            event, metadata["user_prompt"], provider
                        )
                    )
            continue
        if output.type in ("turn_started", "step_completed"):
            continue
        if output.type == "aborted":
            event.set_extra("agent_user_aborted", True)
            event.set_extra("agent_stop_requested", False)
            continue
        data = output.data if isinstance(output.data, dict) else {}
        chain = data.get("chain")
        if not isinstance(chain, MessageChain):
            continue
        if output.type == "agent_stats":
            if event.get_platform_name() == "webchat":
                await event.send(chain)
            continue
        if output.type == "tool_call":
            if streaming and show_tool_use:
                yield MessageChain(chain=[], type="break")
            info = _extract_chain_json_data(chain)
            _record_tool_call_name(info, names)
            event.trace.record("agent_tool_call", tool_name=info or "unknown")
            if event.get_platform_name() == "webchat":
                await event.send(chain)
            elif show_tool_use and not (
                show_tool_call_result and isinstance(info, dict)
            ):
                await event.send(
                    MessageChain(type="tool_call").message(
                        _build_tool_call_status_message(info)
                    )
                )
            continue
        if output.type == "tool_call_result":
            event.trace.record(
                "agent_tool_result",
                tool_result=chain.get_plain_text(with_other_comps_mark=True),
            )
            if (
                chain.type == "tool_direct_result"
                or event.get_platform_id() == "webchat"
            ):
                await event.send(chain)
            elif show_tool_use and show_tool_call_result:
                await event.send(
                    MessageChain(type="tool_call").message(
                        _build_tool_result_status_message(chain, names)
                    )
                )
            continue
        if output.type == "err":
            error_emitted = True
            yield chain
        elif output.type == "streaming_delta":
            if (
                streaming
                and not stream_to_general
                and (chain.type != "reasoning" or show_reasoning)
            ):
                yield chain
        elif output.type == "llm_result":
            if chain.type == "reasoning":
                continue
            if stream_to_general or not streaming:
                if buffer:
                    buffered.chain.extend(chain.chain)
                else:
                    yield chain


async def deliver_agent_turn(context: Context, turn: AgentTurn) -> None:
    """Present SDK output through the existing decoration and response stages.

    Args:
        context: Host configuration and plugin services.
        turn: Independently executing turn whose output should be presented.
    """
    from astrbot.core.message.message_event_result import (
        MessageEventResult,
        ResultContentType,
    )
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.pipeline.respond.stage import RespondStage
    from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
    from astrbot.core.pipeline.scheduler import PipelineScheduler

    event = turn.input.event
    config = context.get_config(umo=turn.session.umo)
    manager = context._star_manager
    if manager is None:
        raise RuntimeError("Plugin manager is unavailable for agent output")
    pipeline = PipelineScheduler(
        PipelineContext(config, manager, event.get_platform_id())
    )
    # Input admission and execution are already owned by the service and runtime.
    pipeline.stages = [ResultDecorateStage(), RespondStage()]
    for stage in pipeline.stages:
        await stage.initialize(pipeline.ctx)
    settings = config.get("provider_settings", {})
    async for chain in present_turn(
        turn,
        streaming=False,
        show_tool_use=settings.get("show_tool_use_status", True),
        show_tool_call_result=settings.get("show_tool_call_result", False),
        show_reasoning=settings.get("display_reasoning_text", False),
        buffer_intermediate_messages=settings.get(
            "buffer_intermediate_messages", False
        ),
        context=context,
    ):
        if not chain.chain or event.is_stopped():
            continue
        event.set_result(
            MessageEventResult(
                chain=chain.chain, result_content_type=ResultContentType.LLM_RESULT
            )
        )
        try:
            await pipeline.execute(event)
        finally:
            event.clear_result()
