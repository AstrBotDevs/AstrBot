import asyncio
import sys
import typing as T
from collections import deque
from dataclasses import dataclass, field
from uuid import uuid4

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
from .deerflow_stream_utils import (
    build_task_failure_summary,
    extract_ai_delta_from_event_data,
    extract_clarification_from_event_data,
    extract_latest_ai_text,
    extract_latest_clarification_text,
    extract_messages_from_values_data,
    extract_task_failures_from_custom_event,
    get_message_id,
)

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class DeerFlowAgentRunner(BaseAgentRunner[TContext]):
    """DeerFlow Agent Runner via LangGraph HTTP API."""

    _MAX_VALUES_HISTORY = 200

    @dataclass
    class _StreamState:
        streamed_text: str = ""
        fallback_stream_text: str = ""
        clarification_text: str = ""
        task_failures: list[str] = field(default_factory=list)
        seen_message_ids: set[str] = field(default_factory=set)
        seen_message_order: deque[str] = field(default_factory=deque)
        baseline_initialized: bool = False
        run_values_messages: list[dict[str, T.Any]] = field(default_factory=list)
        timed_out: bool = False

    def _format_exception(self, err: Exception) -> str:
        err_type = type(err).__name__
        detail = str(err).strip()

        if isinstance(err, (asyncio.TimeoutError, TimeoutError)):
            timeout_text = (
                f"{self.timeout}s"
                if isinstance(getattr(self, "timeout", None), (int, float))
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

    def _coerce_int_config(
        self,
        field_name: str,
        value: T.Any,
        default: int,
        min_value: int | None = None,
    ) -> int:
        if isinstance(value, bool):
            logger.warning(
                f"DeerFlow config '{field_name}' should be numeric, got boolean. "
                f"Fallback to {default}."
            )
            parsed = default
        elif isinstance(value, int):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = int(value.strip())
            except ValueError:
                logger.warning(
                    f"DeerFlow config '{field_name}' value '{value}' is not numeric. "
                    f"Fallback to {default}."
                )
                parsed = default
        else:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                logger.warning(
                    f"DeerFlow config '{field_name}' has unsupported type "
                    f"{type(value).__name__}. Fallback to {default}."
                )
                parsed = default

        if min_value is not None and parsed < min_value:
            logger.warning(
                f"DeerFlow config '{field_name}'={parsed} is below minimum {min_value}. "
                f"Fallback to {min_value}."
            )
            parsed = min_value
        return parsed

    async def close(self) -> None:
        """Explicit cleanup hook for long-lived workers."""
        api_client = getattr(self, "api_client", None)
        if isinstance(api_client, DeerFlowAPIClient) and not api_client.is_closed:
            await api_client.close()

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
        self.max_concurrent_subagents = self._coerce_int_config(
            "deerflow_max_concurrent_subagents",
            provider_config.get(
                "deerflow_max_concurrent_subagents",
                3,
            ),
            default=3,
            min_value=1,
        )

        self.timeout = self._coerce_int_config(
            "timeout",
            provider_config.get("timeout", 300),
            default=300,
            min_value=1,
        )
        self.recursion_limit = self._coerce_int_config(
            "deerflow_recursion_limit",
            provider_config.get("deerflow_recursion_limit", 1000),
            default=1000,
            min_value=1,
        )

        new_client_signature = (self.api_base, self.api_key, self.auth_header)
        old_client = getattr(self, "api_client", None)
        old_signature = getattr(self, "_api_client_signature", None)
        if (
            isinstance(old_client, DeerFlowAPIClient)
            and old_signature == new_client_signature
            and not old_client.is_closed
        ):
            self.api_client = old_client
            return

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
        self._api_client_signature = new_client_signature

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

    @override
    async def step_until_done(
        self, max_step: int = 30
    ) -> T.AsyncGenerator[AgentResponse, None]:
        if max_step <= 0:
            raise ValueError("max_step must be greater than 0")

        step_count = 0
        while not self.done() and step_count < max_step:
            step_count += 1
            async for resp in self.step():
                yield resp

        if not self.done():
            raise RuntimeError(
                f"DeerFlow agent reached max_step ({max_step}) without completion."
            )

    def _extract_new_messages_from_values(
        self,
        values_messages: list[T.Any],
        state: _StreamState,
    ) -> list[dict[str, T.Any]]:
        new_messages: list[dict[str, T.Any]] = []
        for msg in values_messages:
            if not isinstance(msg, dict):
                continue
            msg_id = get_message_id(msg)
            if not msg_id or msg_id in state.seen_message_ids:
                continue
            self._remember_seen_message_id(state, msg_id)
            new_messages.append(msg)
        return new_messages

    def _remember_seen_message_id(self, state: _StreamState, msg_id: str) -> None:
        if not msg_id or msg_id in state.seen_message_ids:
            return

        state.seen_message_ids.add(msg_id)
        state.seen_message_order.append(msg_id)
        while len(state.seen_message_order) > self._MAX_VALUES_HISTORY:
            dropped = state.seen_message_order.popleft()
            state.seen_message_ids.discard(dropped)

    def _is_likely_base64_image(self, value: str) -> bool:
        if " " in value:
            return False

        compact = value.replace("\n", "").replace("\r", "")
        if not compact or len(compact) % 4 != 0:
            return False

        base64_chars = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
        )
        return all(ch in base64_chars for ch in compact)

    def _build_user_content(self, prompt: str, image_urls: list[str]) -> T.Any:
        if not image_urls:
            return prompt

        content: list[dict[str, T.Any]] = []
        skipped_invalid_images = 0
        if prompt:
            content.append({"type": "text", "text": prompt})

        for image_url in image_urls:
            url = image_url
            if not isinstance(url, str):
                continue
            url = url.strip()
            if not url:
                continue
            if url.startswith(("http://", "https://", "data:")):
                content.append({"type": "image_url", "image_url": {"url": url}})
                continue
            if not self._is_likely_base64_image(url):
                skipped_invalid_images += 1
                continue
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{url}"},
                },
            )
        if skipped_invalid_images:
            logger.debug(
                "Skipped %d DeerFlow image inputs that were neither URL/data URI nor valid base64.",
                skipped_invalid_images,
            )
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
        values_messages = extract_messages_from_values_data(data)
        if not values_messages:
            return responses

        if not state.baseline_initialized:
            state.baseline_initialized = True
            for msg in values_messages:
                msg_id = get_message_id(msg)
                self._remember_seen_message_id(state, msg_id)
            return responses

        new_messages = self._extract_new_messages_from_values(
            values_messages,
            state,
        )
        if new_messages:
            state.run_values_messages.extend(new_messages)
            if len(state.run_values_messages) > self._MAX_VALUES_HISTORY:
                state.run_values_messages = state.run_values_messages[
                    -self._MAX_VALUES_HISTORY :
                ]
            latest_text = extract_latest_ai_text(state.run_values_messages)
            latest_clarification = extract_latest_clarification_text(
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
        delta = extract_ai_delta_from_event_data(data)
        if delta:
            state.fallback_stream_text += delta

        response: AgentResponse | None = None
        if self.streaming and delta and not state.streamed_text:
            response = AgentResponse(
                type="streaming_delta",
                data=AgentResponseData(chain=MessageChain().message(delta)),
            )

        maybe_clarification = extract_clarification_from_event_data(data)
        if maybe_clarification:
            state.clarification_text = maybe_clarification
        return response

    def _resolve_final_text(self, state: _StreamState) -> str:
        # Clarification tool output should take precedence over partial AI/tool-call text.
        if state.clarification_text:
            final_text = state.clarification_text
        else:
            final_text = extract_latest_ai_text(state.run_values_messages)
            if not final_text:
                final_text = state.streamed_text or state.fallback_stream_text
            if not final_text:
                final_text = build_task_failure_summary(state.task_failures)

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
        session_id = self.req.session_id or f"deerflow-ephemeral-{uuid4()}"
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
                        extract_task_failures_from_custom_event(data),
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
