from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from astrbot import logger
from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.provider.entities import LLMResponse

if TYPE_CHECKING:
    from astrbot.core.astr_agent_context import AstrAgentContext

DEFAULT_CONTEXT_PERSISTENCE: dict[str, Any] = {
    "enable": False,
    "max_turns": 10,
    "ttl_seconds": 3600,
}


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _ttl_seconds(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed == -1:
        return parsed
    return parsed if parsed > 0 else default


def normalize_context_persistence(raw: Any) -> dict[str, Any]:
    defaults = DEFAULT_CONTEXT_PERSISTENCE
    data = raw if isinstance(raw, dict) else {}
    return {
        "enable": bool(data.get("enable", defaults["enable"])),
        "max_turns": _positive_int(data.get("max_turns"), defaults["max_turns"]),
        "ttl_seconds": _ttl_seconds(data.get("ttl_seconds"), defaults["ttl_seconds"]),
    }


def build_subagent_config_fingerprint(payload: dict[str, Any]) -> str:
    stable_payload = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(stable_payload.encode("utf-8")).hexdigest()


@dataclass
class _SubAgentContextRecord:
    messages: list[Message]
    last_used_at: float
    config_fingerprint: str


class SubAgentSessionManager:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], _SubAgentContextRecord] = {}
        self._locks: dict[tuple[str, str, str], asyncio.Lock] = {}

    def build_key(
        self,
        run_context: ContextWrapper[AstrAgentContext],
        subagent_name: str,
    ) -> tuple[str, str, str]:
        event = run_context.context.event
        unified_msg_origin = getattr(event, "unified_msg_origin", "") or ""
        session_id = getattr(event, "session_id", "") or unified_msg_origin
        return (unified_msg_origin, session_id, subagent_name)

    def get_lock(self, key: tuple[str, str, str]) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def clear(self, key: tuple[str, str, str]) -> None:
        self._records.pop(key, None)

    def clear_except_agents(self, agent_names: set[str]) -> None:
        stale_keys = [key for key in self._records if key[2] not in agent_names]
        for key in stale_keys:
            self.clear(key)

    def get_messages(
        self,
        key: tuple[str, str, str],
        *,
        ttl_seconds: int,
        config_fingerprint: str,
        now: float | None = None,
    ) -> list[Message] | None:
        record = self._records.get(key)
        if record is None:
            return None

        now = time.monotonic() if now is None else now
        if ttl_seconds != -1 and now - record.last_used_at > ttl_seconds:
            self.clear(key)
            return None
        if record.config_fingerprint != config_fingerprint:
            self.clear(key)
            return None
        return [self._clone_message(message) for message in record.messages]

    def set_messages(
        self,
        key: tuple[str, str, str],
        messages: list[Message],
        *,
        config_fingerprint: str,
        context_persistence: dict[str, Any],
        now: float | None = None,
    ) -> None:
        trimmed = self._trim_messages(
            messages,
            max_turns=context_persistence["max_turns"],
        )
        self._records[key] = _SubAgentContextRecord(
            messages=trimmed,
            last_used_at=time.monotonic() if now is None else now,
            config_fingerprint=config_fingerprint,
        )

    def _trim_messages(
        self,
        messages: list[Message],
        *,
        max_turns: int,
    ) -> list[Message]:
        groups = self._group_messages(messages)
        groups = self._trim_groups_by_turns(groups, max_turns)
        return [message for group in groups for message in group]

    def _group_messages(self, messages: list[Message]) -> list[list[Message]]:
        groups: list[list[Message]] = []
        index = 0
        while index < len(messages):
            message = messages[index]
            if message.role in {"system", "_checkpoint"}:
                index += 1
                continue
            if message.role == "tool":
                index += 1
                continue

            cloned = self._clone_message(message)
            group = [cloned]
            if message.role == "assistant" and message.tool_calls:
                expected_ids = {
                    tool_call.get("id") if isinstance(tool_call, dict) else tool_call.id
                    for tool_call in message.tool_calls
                }
                next_index = index + 1
                while next_index < len(messages):
                    next_message = messages[next_index]
                    if (
                        next_message.role == "tool"
                        and next_message.tool_call_id in expected_ids
                    ):
                        group.append(self._clone_message(next_message))
                        next_index += 1
                        continue
                    break
                index = next_index
            else:
                index += 1
            groups.append(group)
        return groups

    def _trim_groups_by_turns(
        self, groups: list[list[Message]], max_turns: int
    ) -> list[list[Message]]:
        user_group_indexes = [
            index
            for index, group in enumerate(groups)
            if group and group[0].role == "user"
        ]
        if len(user_group_indexes) <= max_turns:
            return groups
        first_kept_index = user_group_indexes[-max_turns]
        return groups[first_kept_index:]

    @staticmethod
    def _clone_message(message: Message) -> Message:
        return Message.model_validate(copy.deepcopy(message.model_dump()))


class SubAgentRunner:
    def __init__(self, session_manager: SubAgentSessionManager) -> None:
        self._session_manager = session_manager

    async def run(
        self,
        *,
        tool: Any,
        run_context: ContextWrapper[AstrAgentContext],
        event: Any,
        ctx: Any,
        provider_id: str,
        input_: str | None,
        image_urls: list[str],
        system_prompt: str,
        tools: Any,
        begin_contexts: list[Message] | None,
        max_steps: int,
        tool_call_timeout: int,
        stream: bool,
    ) -> LLMResponse:
        context_persistence = normalize_context_persistence(
            getattr(tool, "context_persistence", None)
        )
        key = self._session_manager.build_key(run_context, tool.agent.name)
        if not context_persistence["enable"]:
            self._session_manager.clear(key)
            return await ctx.tool_loop_agent(
                event=event,
                chat_provider_id=provider_id,
                prompt=input_,
                image_urls=image_urls,
                system_prompt=system_prompt,
                tools=tools,
                contexts=begin_contexts,
                max_steps=max_steps,
                tool_call_timeout=tool_call_timeout,
                stream=stream,
            )

        internal_run = getattr(ctx, "_run_tool_loop_agent_internal", None)
        if internal_run is None:
            logger.debug(
                "Context._run_tool_loop_agent_internal is unavailable; falling "
                "back to stateless SubAgent handoff."
            )
            return await ctx.tool_loop_agent(
                event=event,
                chat_provider_id=provider_id,
                prompt=input_,
                image_urls=image_urls,
                system_prompt=system_prompt,
                tools=tools,
                contexts=begin_contexts,
                max_steps=max_steps,
                tool_call_timeout=tool_call_timeout,
                stream=stream,
            )

        config_fingerprint = getattr(tool, "config_fingerprint", "")
        lock = self._session_manager.get_lock(key)
        async with lock:
            persisted_contexts = self._session_manager.get_messages(
                key,
                ttl_seconds=context_persistence["ttl_seconds"],
                config_fingerprint=config_fingerprint,
            )
            contexts = (
                persisted_contexts if persisted_contexts is not None else begin_contexts
            )

            result = await internal_run(
                event=event,
                chat_provider_id=provider_id,
                prompt=input_,
                image_urls=image_urls,
                system_prompt=system_prompt,
                tools=tools,
                contexts=contexts,
                max_steps=max_steps,
                tool_call_timeout=tool_call_timeout,
                stream=stream,
            )
            self._session_manager.set_messages(
                key,
                result.run_context.messages,
                config_fingerprint=config_fingerprint,
                context_persistence=context_persistence,
            )
            return result.llm_response
