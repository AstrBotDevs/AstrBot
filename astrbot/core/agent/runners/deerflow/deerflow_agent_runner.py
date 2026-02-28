import asyncio
import sys
import typing as T
from collections.abc import Iterable
from dataclasses import dataclass, field

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core import sp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderRequest,
)

from ...hooks import BaseAgentRunHooks
from ...response import AgentResponseData
from ...run_context import ContextWrapper, TContext
from ..base import AgentResponse, AgentState, BaseAgentRunner
from .deerflow_api_client import DeerFlowAPIClient

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class DeerFlowAgentRunner(BaseAgentRunner[TContext]):
    """DeerFlow Agent Runner via LangGraph HTTP API."""

    @dataclass
    class _StreamState:
        streamed_text: str = ""
        fallback_stream_text: str = ""
        clarification_text: str = ""
        task_failures: list[str] = field(default_factory=list)
        seen_message_ids: set[str] = field(default_factory=set)
        baseline_initialized: bool = False
        run_values_messages: list[dict[str, T.Any]] = field(default_factory=list)
        timed_out: bool = False

    def _format_exception(self, err: Exception) -> str:
        err_type = type(err).__name__
        detail = str(err).strip()

        if isinstance(err, (asyncio.TimeoutError, TimeoutError)):
            timeout_text = (
                f"{self.timeout}s"
                if isinstance(getattr(self, "timeout", None), int | float)
                else "configured timeout"
            )
            return (
                f"{err_type}: request timed out after {timeout_text}. "
                "Please check DeerFlow service health and backend logs."
            )

        if detail:
            if detail.startswith(f"{err_type}:"):
                return detail
            return f"{err_type}: {detail}"

        return f"{err_type}: no detailed error message provided."

    @override
    async def reset(
        self,
        request: ProviderRequest,
        run_context: ContextWrapper[TContext],
        agent_hooks: BaseAgentRunHooks[TContext],
        provider_config: dict,
        **kwargs: T.Any,
    ) -> None:
        self.req = request
        self.streaming = kwargs.get("streaming", False)
        self.final_llm_resp = None
        self._state = AgentState.IDLE
        self.agent_hooks = agent_hooks
        self.run_context = run_context

        self.api_base = provider_config.get(
            "deerflow_api_base", "http://127.0.0.1:2026"
        )
        if not isinstance(self.api_base, str) or not self.api_base.startswith(
            ("http://", "https://"),
        ):
            raise Exception(
                "DeerFlow API Base URL format is invalid. It must start with http:// or https://.",
            )
        self.api_key = provider_config.get("deerflow_api_key", "")
        self.auth_header = provider_config.get("deerflow_auth_header", "")
        self.assistant_id = provider_config.get("deerflow_assistant_id", "lead_agent")
        self.model_name = provider_config.get("deerflow_model_name", "")
        self.thinking_enabled = bool(
            provider_config.get("deerflow_thinking_enabled", False),
        )
        self.plan_mode = bool(provider_config.get("deerflow_plan_mode", False))
        self.subagent_enabled = bool(
            provider_config.get("deerflow_subagent_enabled", False),
        )
        self.max_concurrent_subagents = provider_config.get(
            "deerflow_max_concurrent_subagents",
            3,
        )
        if isinstance(self.max_concurrent_subagents, str):
            self.max_concurrent_subagents = int(self.max_concurrent_subagents)
        if self.max_concurrent_subagents < 1:
            self.max_concurrent_subagents = 1

        self.timeout = provider_config.get("timeout", 300)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)
        self.recursion_limit = provider_config.get("deerflow_recursion_limit", 1000)
        if isinstance(self.recursion_limit, str):
            self.recursion_limit = int(self.recursion_limit)

        old_client = getattr(self, "api_client", None)
        if isinstance(old_client, DeerFlowAPIClient):
            try:
                await old_client.close()
            except Exception as e:
                logger.warning(
                    f"Failed to close previous DeerFlow API client cleanly: {e}"
                )

        self.api_client = DeerFlowAPIClient(
            api_base=self.api_base,
            api_key=self.api_key,
            auth_header=self.auth_header,
        )

    @override
    async def step(self):
        if not self.req:
            raise ValueError("Request is not set. Please call reset() first.")
        if self.done():
            return

        if self._state == AgentState.IDLE:
            try:
                await self.agent_hooks.on_agent_begin(self.run_context)
            except Exception as e:
                logger.error(f"Error in on_agent_begin hook: {e}", exc_info=True)

        self._transition_state(AgentState.RUNNING)

        try:
            async for response in self._execute_deerflow_request():
                yield response
        except Exception as e:
            err_msg = self._format_exception(e)
            logger.error(f"DeerFlow request failed: {err_msg}", exc_info=True)
            self._transition_state(AgentState.ERROR)
            err_chain = MessageChain().message(f"DeerFlow request failed: {err_msg}")
            self.final_llm_resp = LLMResponse(
                role="err",
                completion_text=f"DeerFlow request failed: {err_msg}",
                result_chain=err_chain,
            )
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=err_chain,
                ),
            )
        finally:
            await self.api_client.close()

    @override
    async def step_until_done(
        self, max_step: int = 30
    ) -> T.AsyncGenerator[AgentResponse, None]:
        while not self.done():
            async for resp in self.step():
                yield resp

    def _extract_text(self, content: T.Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            if isinstance(content.get("text"), str):
                return content["text"]
            if "content" in content:
                return self._extract_text(content.get("content"))
            if "kwargs" in content and isinstance(content["kwargs"], dict):
                return self._extract_text(content["kwargs"].get("content"))
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    item_type = item.get("type")
                    if item_type == "text" and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                    elif "content" in item:
                        parts.append(str(item["content"]))
            return "\n".join([p for p in parts if p]).strip()
        return str(content) if content is not None else ""

    def _extract_messages_from_values_data(self, data: T.Any) -> list[T.Any]:
        """Extract messages list from possible values event payload shapes."""
        candidates: list[T.Any] = []
        if isinstance(data, dict):
            candidates.append(data)
            if isinstance(data.get("values"), dict):
                candidates.append(data["values"])
        elif isinstance(data, list):
            candidates.extend([x for x in data if isinstance(x, dict)])

        for item in candidates:
            messages = item.get("messages")
            if isinstance(messages, list):
                return messages
        return []

    def _is_ai_message(self, message: dict[str, T.Any]) -> bool:
        role = str(message.get("role", "")).lower()
        if role in {"assistant", "ai"}:
            return True

        msg_type = str(message.get("type", "")).lower()
        if msg_type in {"ai", "assistant", "aimessage", "aimessagechunk"}:
            return True
        if "ai" in msg_type and all(
            token not in msg_type for token in ("human", "tool", "system")
        ):
            return True
        return False

    def _extract_latest_ai_text(self, messages: Iterable[T.Any]) -> str:
        # Scan backwards to get the latest assistant/ai message text.
        for msg in reversed(list(messages)):
            if not isinstance(msg, dict):
                continue
            if self._is_ai_message(msg):
                text = self._extract_text(msg.get("content"))
                if text:
                    return text
        return ""

    def _is_clarification_tool_message(self, message: dict[str, T.Any]) -> bool:
        msg_type = str(message.get("type", "")).lower()
        tool_name = str(message.get("name", "")).lower()
        return msg_type == "tool" and tool_name == "ask_clarification"

    def _extract_latest_clarification_text(self, messages: Iterable[T.Any]) -> str:
        for msg in reversed(list(messages)):
            if not isinstance(msg, dict):
                continue
            if self._is_clarification_tool_message(msg):
                text = self._extract_text(msg.get("content"))
                if text:
                    return text
        return ""

    def _get_message_id(self, message: T.Any) -> str:
        if not isinstance(message, dict):
            return ""
        msg_id = message.get("id")
        return msg_id if isinstance(msg_id, str) else ""

    def _extract_new_messages_from_values(
        self,
        values_messages: list[T.Any],
        seen_message_ids: set[str],
    ) -> list[dict[str, T.Any]]:
        new_messages: list[dict[str, T.Any]] = []
        for msg in values_messages:
            if not isinstance(msg, dict):
                continue
            msg_id = self._get_message_id(msg)
            if not msg_id or msg_id in seen_message_ids:
                continue
            seen_message_ids.add(msg_id)
            new_messages.append(msg)
        return new_messages

    def _extract_event_message_obj(self, data: T.Any) -> dict[str, T.Any] | None:
        msg_obj = data
        if isinstance(data, (list, tuple)) and data:
            msg_obj = data[0]
        if isinstance(msg_obj, dict) and isinstance(msg_obj.get("data"), dict):
            # Some servers wrap message body in {"data": {...}}
            msg_obj = msg_obj["data"]
        return msg_obj if isinstance(msg_obj, dict) else None

    def _extract_ai_delta_from_event_data(self, data: T.Any) -> str:
        # LangGraph messages-tuple events usually carry either:
        # - {"type": "ai", "content": "..."}
        # - [message_obj, metadata]
        msg_obj = self._extract_event_message_obj(data)
        if not msg_obj:
            return ""
        if self._is_ai_message(msg_obj):
            return self._extract_text(msg_obj.get("content"))
        return ""

    def _extract_clarification_from_event_data(self, data: T.Any) -> str:
        msg_obj = self._extract_event_message_obj(data)
        if not msg_obj:
            return ""
        if self._is_clarification_tool_message(msg_obj):
            return self._extract_text(msg_obj.get("content"))
        return ""

    def _iter_custom_event_items(self, data: T.Any) -> list[dict[str, T.Any]]:
        items: list[dict[str, T.Any]] = []
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    items.append(item)
                elif isinstance(item, (list, tuple)):
                    for nested in item:
                        if isinstance(nested, dict):
                            items.append(nested)
        return items

    def _extract_task_failures_from_custom_event(self, data: T.Any) -> list[str]:
        failures: list[str] = []
        for item in self._iter_custom_event_items(data):
            event_type = str(item.get("type", "")).lower()
            if event_type not in {"task_failed", "task_timed_out"}:
                continue

            task_id = str(item.get("task_id", "")).strip()
            error_text = self._extract_text(item.get("error")).strip()
            if task_id and error_text:
                failures.append(f"{task_id}: {error_text}")
            elif error_text:
                failures.append(error_text)
            elif task_id:
                failures.append(f"{task_id}: unknown error")
            else:
                failures.append("unknown task failure")
        return failures

    def _build_task_failure_summary(self, failures: list[str]) -> str:
        if not failures:
            return ""
        deduped: list[str] = []
        seen: set[str] = set()
        for failure in failures:
            if failure not in seen:
                seen.add(failure)
                deduped.append(failure)
        if len(deduped) == 1:
            return f"DeerFlow subtask failed: {deduped[0]}"
        joined = "\n".join([f"- {item}" for item in deduped[:5]])
        return f"DeerFlow subtasks failed:\n{joined}"

    def _build_user_content(self, prompt: str, image_urls: list[str]) -> T.Any:
        if not image_urls:
            return prompt

        content: list[dict[str, T.Any]] = []
        if prompt:
            content.append({"type": "text", "text": prompt})

        for image_url in image_urls:
            url = image_url
            if not isinstance(url, str):
                continue
            if not url.startswith(("http://", "https://", "data:")):
                url = f"data:image/png;base64,{url}"
            content.append({"type": "image_url", "image_url": {"url": url}})
        return content

    async def _ensure_thread_id(self, session_id: str) -> str:
        thread_id = await sp.get_async(
            scope="umo",
            scope_id=session_id,
            key="deerflow_thread_id",
            default="",
        )
        if thread_id:
            return thread_id

        thread = await self.api_client.create_thread(timeout=min(30, self.timeout))
        thread_id = thread.get("thread_id", "")
        if not thread_id:
            raise Exception(
                f"DeerFlow create thread returned invalid payload: {thread}"
            )

        await sp.put_async(
            scope="umo",
            scope_id=session_id,
            key="deerflow_thread_id",
            value=thread_id,
        )
        return thread_id

    def _build_messages(
        self,
        prompt: str,
        image_urls: list[str],
        system_prompt: str | None,
    ) -> list[dict[str, T.Any]]:
        messages: list[dict[str, T.Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append(
            {
                "role": "user",
                "content": self._build_user_content(prompt, image_urls),
            },
        )
        return messages

    def _build_runtime_context(self, thread_id: str) -> dict[str, T.Any]:
        runtime_context: dict[str, T.Any] = {
            "thread_id": thread_id,
            "thinking_enabled": self.thinking_enabled,
            "is_plan_mode": self.plan_mode,
            "subagent_enabled": self.subagent_enabled,
        }
        if self.subagent_enabled:
            runtime_context["max_concurrent_subagents"] = self.max_concurrent_subagents
        if self.model_name:
            runtime_context["model_name"] = self.model_name
        return runtime_context

    def _build_payload(
        self,
        thread_id: str,
        prompt: str,
        image_urls: list[str],
        system_prompt: str | None,
    ) -> dict[str, T.Any]:
        return {
            "assistant_id": self.assistant_id,
            "input": {
                "messages": self._build_messages(prompt, image_urls, system_prompt),
            },
            "stream_mode": ["values", "messages-tuple", "custom"],
            # LangGraph 0.6+ prefers context instead of configurable.
            "context": self._build_runtime_context(thread_id),
            "config": {
                "recursion_limit": self.recursion_limit,
            },
        }

    def _handle_values_event(
        self,
        data: T.Any,
        state: _StreamState,
    ) -> list[AgentResponse]:
        responses: list[AgentResponse] = []
        values_messages = self._extract_messages_from_values_data(data)
        if not values_messages:
            return responses

        if not state.baseline_initialized:
            state.baseline_initialized = True
            for msg in values_messages:
                msg_id = self._get_message_id(msg)
                if msg_id:
                    state.seen_message_ids.add(msg_id)
            return responses

        new_messages = self._extract_new_messages_from_values(
            values_messages,
            state.seen_message_ids,
        )
        if new_messages:
            state.run_values_messages.extend(new_messages)
            latest_text = self._extract_latest_ai_text(state.run_values_messages)
            latest_clarification = self._extract_latest_clarification_text(
                state.run_values_messages,
            )
            if latest_clarification:
                state.clarification_text = latest_clarification
        else:
            latest_text = ""

        if self.streaming and latest_text:
            if latest_text.startswith(state.streamed_text):
                delta = latest_text[len(state.streamed_text) :]
                if delta:
                    state.streamed_text = latest_text
                    responses.append(
                        AgentResponse(
                            type="streaming_delta",
                            data=AgentResponseData(
                                chain=MessageChain().message(delta),
                            ),
                        ),
                    )
            elif latest_text != state.streamed_text:
                state.streamed_text = latest_text
                responses.append(
                    AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain().message(latest_text),
                        ),
                    ),
                )
        return responses

    def _handle_message_event(
        self,
        data: T.Any,
        state: _StreamState,
    ) -> AgentResponse | None:
        delta = self._extract_ai_delta_from_event_data(data)
        if delta:
            state.fallback_stream_text += delta

        response: AgentResponse | None = None
        if self.streaming and delta and not state.streamed_text:
            response = AgentResponse(
                type="streaming_delta",
                data=AgentResponseData(chain=MessageChain().message(delta)),
            )

        maybe_clarification = self._extract_clarification_from_event_data(data)
        if maybe_clarification:
            state.clarification_text = maybe_clarification
        return response

    def _resolve_final_text(self, state: _StreamState) -> str:
        # Clarification tool output should take precedence over partial AI/tool-call text.
        if state.clarification_text:
            final_text = state.clarification_text
        else:
            final_text = self._extract_latest_ai_text(state.run_values_messages)
            if not final_text:
                final_text = state.streamed_text or state.fallback_stream_text
            if not final_text:
                final_text = self._build_task_failure_summary(state.task_failures)

        if state.timed_out:
            timeout_note = (
                f"DeerFlow stream timed out after {self.timeout}s. "
                "Returning partial result."
            )
            if final_text:
                final_text = f"{final_text}\n\n{timeout_note}"
            else:
                raise asyncio.TimeoutError(timeout_note)

        if not final_text:
            logger.warning("DeerFlow returned no text content in stream events.")
            final_text = "DeerFlow returned an empty response."
        return final_text

    async def _execute_deerflow_request(self):
        prompt = self.req.prompt or ""
        session_id = self.req.session_id or "unknown"
        image_urls = self.req.image_urls or []
        system_prompt = self.req.system_prompt

        thread_id = await self._ensure_thread_id(session_id)
        payload = self._build_payload(
            thread_id=thread_id,
            prompt=prompt,
            image_urls=image_urls,
            system_prompt=system_prompt,
        )
        state = self._StreamState()

        try:
            async for event in self.api_client.stream_run(
                thread_id=thread_id,
                payload=payload,
                timeout=self.timeout,
            ):
                event_type = event.get("event")
                data = event.get("data")

                if event_type == "values":
                    for response in self._handle_values_event(data, state):
                        yield response
                    continue

                if event_type in {"messages-tuple", "messages", "message"}:
                    response = self._handle_message_event(data, state)
                    if response:
                        yield response
                    continue

                if event_type == "custom":
                    state.task_failures.extend(
                        self._extract_task_failures_from_custom_event(data),
                    )
                    continue

                if event_type == "error":
                    raise Exception(f"DeerFlow stream returned error event: {data}")

                if event_type == "end":
                    break
        except (asyncio.TimeoutError, TimeoutError):
            state.timed_out = True

        final_text = self._resolve_final_text(state)

        chain = MessageChain(chain=[Comp.Plain(final_text)])
        self.final_llm_resp = LLMResponse(role="assistant", result_chain=chain)
        self._transition_state(AgentState.DONE)

        try:
            await self.agent_hooks.on_agent_done(self.run_context, self.final_llm_resp)
        except Exception as e:
            logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)

        yield AgentResponse(
            type="llm_result",
            data=AgentResponseData(chain=chain),
        )

    @override
    def done(self) -> bool:
        """Check whether the agent has finished or failed."""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    @override
    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
