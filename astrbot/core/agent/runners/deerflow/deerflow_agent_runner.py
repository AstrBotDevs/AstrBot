import asyncio
import base64
import hashlib
import json
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
from astrbot.core.utils.config_number import coerce_int_config

from ...hooks import BaseAgentRunHooks
from ...response import AgentResponseData
from ...run_context import ContextWrapper, TContext
from ..base import AgentResponse, AgentState, BaseAgentRunner
from .deerflow_api_client import DeerFlowAPIClient
from .deerflow_stream_utils import (
    build_task_failure_summary,
    extract_ai_delta_from_event_data,
    extract_clarification_from_event_data,
    extract_latest_ai_message,
    extract_latest_ai_text,
    extract_latest_clarification_text,
    extract_messages_from_values_data,
    extract_task_failures_from_custom_event,
    extract_text,
    get_message_id,
)

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class DeerFlowAgentRunner(BaseAgentRunner[TContext]):
    """DeerFlow Agent Runner via LangGraph HTTP API."""

    _MAX_VALUES_HISTORY = 200

    @dataclass(frozen=True)
    class _RunnerConfig:
        api_base: str
        api_key: str
        auth_header: str
        proxy: str
        assistant_id: str
        model_name: str
        thinking_enabled: bool
        plan_mode: bool
        subagent_enabled: bool
        max_concurrent_subagents: int
        timeout: int
        recursion_limit: int

    @dataclass
    class _StreamState:
        latest_text: str = ""
        prev_text_for_streaming: str = ""
        clarification_text: str = ""
        task_failures: list[str] = field(default_factory=list)
        seen_message_ids: set[str] = field(default_factory=set)
        seen_message_order: deque[str] = field(default_factory=deque)
        # Fallback tracking for backends that omit message ids in values events.
        no_id_message_fingerprints: dict[int, str] = field(default_factory=dict)
        baseline_initialized: bool = False
        has_values_text: bool = False
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

    async def close(self) -> None:
        """Explicit cleanup hook for long-lived workers."""
        api_client = getattr(self, "api_client", None)
        if isinstance(api_client, DeerFlowAPIClient) and not api_client.is_closed:
            await api_client.close()

    async def _notify_agent_done_hook(self) -> None:
        if not self.final_llm_resp:
            return
        try:
            await self.agent_hooks.on_agent_done(self.run_context, self.final_llm_resp)
        except Exception as e:
            logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)

    def _parse_runner_config(self, provider_config: dict) -> _RunnerConfig:
        api_base = provider_config.get("deerflow_api_base", "http://127.0.0.1:2026")
        if not isinstance(api_base, str) or not api_base.startswith(
            ("http://", "https://"),
        ):
            raise ValueError(
                "DeerFlow API Base URL format is invalid. It must start with http:// or https://.",
            )

        proxy = provider_config.get("proxy", "")
        normalized_proxy = proxy.strip() if isinstance(proxy, str) else ""

        return self._RunnerConfig(
            api_base=api_base,
            api_key=provider_config.get("deerflow_api_key", ""),
            auth_header=provider_config.get("deerflow_auth_header", ""),
            proxy=normalized_proxy,
            assistant_id=provider_config.get("deerflow_assistant_id", "lead_agent"),
            model_name=provider_config.get("deerflow_model_name", ""),
            thinking_enabled=bool(
                provider_config.get("deerflow_thinking_enabled", False),
            ),
            plan_mode=bool(provider_config.get("deerflow_plan_mode", False)),
            subagent_enabled=bool(
                provider_config.get("deerflow_subagent_enabled", False),
            ),
            max_concurrent_subagents=coerce_int_config(
                provider_config.get("deerflow_max_concurrent_subagents", 3),
                default=3,
                min_value=1,
                field_name="deerflow_max_concurrent_subagents",
                source="DeerFlow config",
            ),
            timeout=coerce_int_config(
                provider_config.get("timeout", 300),
                default=300,
                min_value=1,
                field_name="timeout",
                source="DeerFlow config",
            ),
            recursion_limit=coerce_int_config(
                provider_config.get("deerflow_recursion_limit", 1000),
                default=1000,
                min_value=1,
                field_name="deerflow_recursion_limit",
                source="DeerFlow config",
            ),
        )

    def _apply_runner_config(self, config: _RunnerConfig) -> None:
        self.api_base = config.api_base
        self.api_key = config.api_key
        self.auth_header = config.auth_header
        self.proxy = config.proxy
        self.assistant_id = config.assistant_id
        self.model_name = config.model_name
        self.thinking_enabled = config.thinking_enabled
        self.plan_mode = config.plan_mode
        self.subagent_enabled = config.subagent_enabled
        self.max_concurrent_subagents = config.max_concurrent_subagents
        self.timeout = config.timeout
        self.recursion_limit = config.recursion_limit

    @staticmethod
    def _build_client_signature(config: _RunnerConfig) -> tuple[str, str, str, str]:
        return (
            config.api_base,
            config.api_key,
            config.auth_header,
            config.proxy,
        )

    async def _refresh_api_client(self, config: _RunnerConfig) -> None:
        new_client_signature = self._build_client_signature(config)
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
            api_base=config.api_base,
            api_key=config.api_key,
            auth_header=config.auth_header,
            proxy=config.proxy,
        )
        self._api_client_signature = new_client_signature

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

        config = self._parse_runner_config(provider_config)
        self._apply_runner_config(config)
        await self._refresh_api_client(config)

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
        except asyncio.CancelledError:
            # Let caller manage cancellation semantics.
            raise
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
            await self._notify_agent_done_hook()
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
        no_id_indexes_seen: set[int] = set()
        for idx, msg in enumerate(values_messages):
            if not isinstance(msg, dict):
                continue
            msg_id = get_message_id(msg)
            if msg_id:
                if msg_id in state.seen_message_ids:
                    continue
                self._remember_seen_message_id(state, msg_id)
                new_messages.append(msg)
                continue

            no_id_indexes_seen.add(idx)
            msg_fingerprint = self._fingerprint_message(msg)
            if state.no_id_message_fingerprints.get(idx) == msg_fingerprint:
                continue
            state.no_id_message_fingerprints[idx] = msg_fingerprint
            new_messages.append(msg)

        # Keep no-id index state aligned with latest values payload shape.
        for idx in list(state.no_id_message_fingerprints.keys()):
            if idx not in no_id_indexes_seen:
                state.no_id_message_fingerprints.pop(idx, None)
        return new_messages

    def _fingerprint_message(self, message: dict[str, T.Any]) -> str:
        try:
            raw = json.dumps(message, sort_keys=True, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            raw = repr(message)
        return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()

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
        if not compact or len(compact) < 32 or len(compact) % 4 != 0:
            return False

        base64_chars = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
        )
        if any(ch not in base64_chars for ch in compact):
            return False
        try:
            base64.b64decode(compact, validate=True)
        except Exception:
            return False
        return True

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
            compact_base64 = url.replace("\n", "").replace("\r", "")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{compact_base64}"},
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

    def _image_component_from_url(self, url: T.Any) -> Comp.Image | None:
        if not isinstance(url, str):
            return None

        normalized = url.strip()
        if not normalized:
            return None

        if normalized.startswith(("http://", "https://")):
            try:
                return Comp.Image.fromURL(normalized)
            except Exception:
                return None

        if not normalized.startswith("data:"):
            return None

        header, sep, payload = normalized.partition(",")
        if not sep:
            return None
        if ";base64" not in header.lower():
            return None

        compact_payload = payload.replace("\n", "").replace("\r", "").strip()
        if not compact_payload:
            return None
        try:
            base64.b64decode(compact_payload, validate=True)
        except Exception:
            return None
        return Comp.Image.fromBase64(compact_payload)

    def _append_components_from_content(
        self,
        content: T.Any,
        components: list[Comp.BaseMessageComponent],
    ) -> None:
        if isinstance(content, str):
            if content:
                components.append(Comp.Plain(content))
            return

        if isinstance(content, list):
            for item in content:
                self._append_components_from_content(item, components)
            return

        if not isinstance(content, dict):
            return

        item_type = str(content.get("type", "")).lower()
        if item_type == "text" and isinstance(content.get("text"), str):
            text = content["text"]
            if text:
                components.append(Comp.Plain(text))
            return

        if item_type == "image_url":
            image_payload = content.get("image_url")
            image_url: T.Any = image_payload
            if isinstance(image_payload, dict):
                image_url = image_payload.get("url")
            image_comp = self._image_component_from_url(image_url)
            if image_comp is not None:
                components.append(image_comp)
            return

        if "content" in content:
            self._append_components_from_content(content.get("content"), components)
            return

        kwargs = content.get("kwargs")
        if isinstance(kwargs, dict) and "content" in kwargs:
            self._append_components_from_content(kwargs.get("content"), components)

    def _build_chain_from_ai_content(self, content: T.Any) -> MessageChain:
        components: list[Comp.BaseMessageComponent] = []
        self._append_components_from_content(content, components)
        if components:
            return MessageChain(chain=components)

        fallback_text = extract_text(content)
        if fallback_text:
            return MessageChain(chain=[Comp.Plain(fallback_text)])
        return MessageChain()

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

        new_messages: list[dict[str, T.Any]] = []
        if not state.baseline_initialized:
            state.baseline_initialized = True
            for idx, msg in enumerate(values_messages):
                if not isinstance(msg, dict):
                    continue
                new_messages.append(msg)
                msg_id = get_message_id(msg)
                if msg_id:
                    self._remember_seen_message_id(state, msg_id)
                    continue
                state.no_id_message_fingerprints[idx] = self._fingerprint_message(msg)
        else:
            new_messages = self._extract_new_messages_from_values(
                values_messages,
                state,
            )
        latest_text = ""
        if new_messages:
            state.run_values_messages.extend(new_messages)
            if len(state.run_values_messages) > self._MAX_VALUES_HISTORY:
                state.run_values_messages = state.run_values_messages[
                    -self._MAX_VALUES_HISTORY :
                ]
            latest_text = extract_latest_ai_text(state.run_values_messages)
            if latest_text:
                state.latest_text = latest_text
                state.has_values_text = True
            latest_clarification = extract_latest_clarification_text(
                state.run_values_messages,
            )
            if latest_clarification:
                state.clarification_text = latest_clarification

        if self.streaming and latest_text:
            if latest_text.startswith(state.prev_text_for_streaming):
                delta = latest_text[len(state.prev_text_for_streaming) :]
            else:
                delta = latest_text

            if delta:
                state.prev_text_for_streaming = latest_text
                responses.append(
                    AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain().message(delta),
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

        response: AgentResponse | None = None
        if delta and not state.has_values_text:
            state.latest_text += delta
        if self.streaming and delta and not state.has_values_text:
            response = AgentResponse(
                type="streaming_delta",
                data=AgentResponseData(chain=MessageChain().message(delta)),
            )

        maybe_clarification = extract_clarification_from_event_data(data)
        if maybe_clarification:
            state.clarification_text = maybe_clarification
        return response

    def _select_final_chain(self, state: _StreamState) -> tuple[MessageChain, bool]:
        if state.clarification_text:
            return MessageChain(chain=[Comp.Plain(state.clarification_text)]), False

        latest_ai_message = extract_latest_ai_message(state.run_values_messages)
        if latest_ai_message:
            chain_from_values = self._build_chain_from_ai_content(
                latest_ai_message.get("content"),
            )
            if chain_from_values.chain:
                return chain_from_values, False

        if state.latest_text:
            return MessageChain(chain=[Comp.Plain(state.latest_text)]), False

        failure_text = build_task_failure_summary(state.task_failures)
        if failure_text:
            return MessageChain(chain=[Comp.Plain(failure_text)]), True

        return MessageChain(), False

    def _resolve_final_output(self, state: _StreamState) -> tuple[MessageChain, bool]:
        # Clarification and values/message-derived output share a single selection path.
        final_chain, failures_only = self._select_final_chain(state)

        if not final_chain.chain:
            logger.warning("DeerFlow returned no text content in stream events.")
            final_chain = MessageChain(
                chain=[Comp.Plain("DeerFlow returned an empty response.")],
            )
        return final_chain, failures_only

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

        final_chain, failures_only = self._resolve_final_output(state)
        if state.timed_out:
            timeout_note = (
                f"DeerFlow stream timed out after {self.timeout}s. "
                "Returning partial result."
            )
            if final_chain.chain and isinstance(final_chain.chain[-1], Comp.Plain):
                last_text = final_chain.chain[-1].text
                final_chain.chain[-1].text = (
                    f"{last_text}\n\n{timeout_note}" if last_text else timeout_note
                )
            else:
                final_chain.chain.append(Comp.Plain(timeout_note))

        if self.streaming:
            non_plain_components = [
                component
                for component in final_chain.chain
                if not isinstance(component, Comp.Plain)
            ]
            if non_plain_components:
                yield AgentResponse(
                    type="streaming_delta",
                    data=AgentResponseData(
                        chain=MessageChain(chain=non_plain_components),
                    ),
                )

        is_error = state.timed_out or failures_only
        role = "err" if is_error else "assistant"

        self.final_llm_resp = LLMResponse(role=role, result_chain=final_chain)
        self._transition_state(AgentState.DONE)
        await self._notify_agent_done_hook()

        yield AgentResponse(
            type="llm_result",
            data=AgentResponseData(chain=final_chain),
        )

    @override
    def done(self) -> bool:
        """Check whether the agent has finished or failed."""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    @override
    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
