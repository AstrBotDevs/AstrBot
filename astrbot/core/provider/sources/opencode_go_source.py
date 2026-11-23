from __future__ import annotations

import asyncio
import copy
import random
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from openai.lib.streaming.chat._completions import ChatCompletionStreamState
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

import astrbot.core.message.components as Comp
from astrbot import __version__, logger
from astrbot.core.agent.tool import ToolSet
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.utils.network_utils import is_connection_error, log_connection_failure

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial
from .request_retry import retry_provider_request

OPENCODE_GO_API_BASE = "https://opencode.ai/inference/go/v1"
OPENCODE_GO_USER_AGENT = f"astrbot/{__version__}"
OPENCODE_SESSION_HEADER = "x-opencode-session"
OPENCODE_REQUEST_HEADER = "x-opencode-request"
OPENCODE_CLIENT_HEADER = "x-opencode-client"
OPENCODE_PROJECT_HEADER = "x-opencode-project"


@register_provider_adapter(
    "opencode_go_chat_completion",
    "OpenCode Go Chat Completion Provider Adapter",
)
class ProviderOpenCodeGo(ProviderOpenAIOfficial):
    """OpenCode Go-compatible Chat Completions provider adapter."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Initialize OpenCode Go request defaults.

        Args:
            provider_config: OpenCode Go endpoint, API key, and model configuration.
            provider_settings: Global provider settings.
        """
        merged_provider_config = dict(provider_config)
        merged_provider_config.setdefault("api_base", OPENCODE_GO_API_BASE)
        configured_headers = merged_provider_config.get("custom_headers")
        custom_headers = (
            dict(configured_headers) if isinstance(configured_headers, dict) else {}
        )
        if not any(name.lower() == "user-agent" for name in custom_headers):
            custom_headers["User-Agent"] = OPENCODE_GO_USER_AGENT
        merged_provider_config["custom_headers"] = custom_headers
        super().__init__(merged_provider_config, provider_settings)
        # Requests that are not bound to an AstrBot conversation (for example the
        # WebUI model test or model listing) still need a stable routing identity.
        # Keep one per provider instance so OpenCode can cache prompts for it.
        self._fallback_session_id = uuid.uuid4().hex
        # Per-session request counter used for the x-opencode-request header.
        self._session_request_counts: dict[str, int] = {}

    async def _prepare_opencode_request(
        self, payloads: dict, tools: ToolSet | None
    ) -> dict[str, Any]:
        """Prepare request body fields using the OpenAI-compatible provider rules."""
        if tools:
            model = payloads.get("model", "").lower()
            tool_list = tools.get_func_desc_openai_style(
                omit_empty_parameter_field="gemini" in model,
            )
            if tool_list:
                payloads["tools"] = tool_list
                payloads["tool_choice"] = payloads.get("tool_choice", "auto")

        extra_body: dict[str, Any] = {}
        to_del = []
        for key in payloads:
            if key not in self.default_params:
                extra_body[key] = payloads[key]
                to_del.append(key)
        for key in to_del:
            del payloads[key]

        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        if isinstance(custom_extra_body, dict):
            extra_body.update(custom_extra_body)
        self._apply_provider_specific_request_overrides(payloads, extra_body)
        self._sanitize_assistant_messages(payloads)
        return extra_body

    async def _send_opencode_request(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        stream: bool,
        request_max_retries: int | None,
        conversation_id: str | None,
    ) -> Any:
        """Send one OpenCode Go request with routing and retry metadata."""
        extra_body = await self._prepare_opencode_request(payloads, tools)
        return await retry_provider_request(
            "OpenCode Go",
            lambda: self.client.chat.completions.create(
                **payloads,
                stream=stream,
                extra_body=extra_body,
                extra_headers=self._opencode_session_headers(conversation_id),
                **({"stream_options": {"include_usage": True}} if stream else {}),
            ),
            max_attempts=request_max_retries,
        )

    async def _request_with_key_fallback(
        self,
        payloads: dict,
        contexts: list,
        tools: ToolSet | None,
        *,
        stream: bool,
        request_max_retries: int | None,
        conversation_id: str | None,
    ) -> Any:
        """Rotate API keys on rate limits while preserving provider fallback rules."""
        available_api_keys = self.api_keys.copy()
        if not available_api_keys:
            available_api_keys = [self.client.api_key or ""]
        chosen_key = random.choice(available_api_keys)
        max_retries = 10
        current_payloads = copy.deepcopy(payloads)
        for retry_count in range(max_retries):
            try:
                self.client.api_key = chosen_key
                return await self._send_opencode_request(
                    current_payloads,
                    tools,
                    stream=stream,
                    request_max_retries=request_max_retries,
                    conversation_id=conversation_id,
                )
            except Exception as exc:
                if "429" in str(exc) and len(available_api_keys) > 1:
                    if chosen_key in available_api_keys:
                        available_api_keys.remove(chosen_key)
                    chosen_key = random.choice(available_api_keys)
                    if retry_count < max_retries - 1:
                        await asyncio.sleep(1)
                    continue
                if is_connection_error(exc):
                    log_connection_failure(
                        "OpenCode Go", exc, self.provider_config.get("proxy", "")
                    )
                (
                    recovered,
                    chosen_key,
                    available_api_keys,
                    current_payloads,
                    contexts,
                    tools,
                    _image_fallback_used,
                ) = await self._handle_api_error(
                    exc,
                    current_payloads,
                    contexts,
                    tools,
                    chosen_key,
                    available_api_keys,
                    retry_count,
                    max_retries,
                )
                if recovered:
                    continue
        raise RuntimeError("OpenCode Go request failed after all retries.")

    def _opencode_session_headers(self, conversation_id: str | None) -> dict[str, str]:
        """Build the OpenCode Go routing headers for one request.

        OpenCode rejects inference requests without ``x-opencode-session``. AstrBot
        conversations supply the value when one is bound; otherwise the stable
        per-provider fallback keeps one-off calls routable and cache-friendly.
        The remaining headers mirror the OpenCode client so the gateway can treat
        AstrBot as a first-class CLI client.

        Args:
            conversation_id: Bound AstrBot conversation ID, or None for one-off calls.

        Returns:
            A header mapping that always contains the OpenCode session identity.
        """
        session_id = (
            str(conversation_id) if conversation_id else self._fallback_session_id
        )
        request_number = self._session_request_counts.get(session_id, 0) + 1
        self._session_request_counts[session_id] = request_number
        return {
            OPENCODE_SESSION_HEADER: session_id,
            OPENCODE_REQUEST_HEADER: f"msg_{request_number}",
            OPENCODE_CLIENT_HEADER: "cli",
            OPENCODE_PROJECT_HEADER: "global",
        }

    async def get_models(self) -> list[str]:
        """List models exposed by OpenCode Go with the routing header attached.

        Returns:
            Sorted model identifiers.

        Raises:
            Exception: If the model list request fails.
        """
        models = await retry_provider_request(
            "OpenCode Go",
            lambda: self.client.models.list(
                extra_headers=self._opencode_session_headers(None),
            ),
        )
        return sorted(model.id for model in models.data)

    async def _query(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
        conversation_id: str | None = None,
    ) -> LLMResponse:
        """Send a non-streaming completion with the OpenCode session header.

        Args:
            payloads: OpenAI Chat Completions request payload.
            tools: Available function tools.
            request_max_retries: Maximum transport attempts.
            conversation_id: Stable ID for the AstrBot conversation.

        Returns:
            The normalized provider response.

        Raises:
            TypeError: If the SDK returns an unexpected response object.
        """
        completion = await self._request_with_key_fallback(
            payloads,
            payloads["messages"],
            tools,
            stream=False,
            request_max_retries=request_max_retries,
            conversation_id=conversation_id,
        )
        if not isinstance(completion, ChatCompletion):
            raise TypeError(
                f"OpenCode Go returned an unexpected completion type: {type(completion)}."
            )
        logger.debug("OpenCode Go completion: %s", completion)
        return await self._parse_openai_completion(completion, tools)

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
        conversation_id: str | None = None,
    ) -> AsyncGenerator[LLMResponse, None]:
        """Stream a completion with the OpenCode session header.

        Args:
            payloads: OpenAI Chat Completions request payload.
            tools: Available function tools.
            request_max_retries: Maximum transport attempts.
            conversation_id: Stable ID for the AstrBot conversation.

        Yields:
            Completion chunks and the final normalized response.

        Raises:
            EmptyModelOutputError: If the stream ends without usable model output.
        """
        stream = await self._request_with_key_fallback(
            payloads,
            payloads["messages"],
            tools,
            stream=True,
            request_max_retries=request_max_retries,
            conversation_id=conversation_id,
        )

        llm_response = LLMResponse("assistant", is_chunk=True)
        state = ChatCompletionStreamState()
        usage = None
        async for chunk in stream:
            if not isinstance(chunk, ChatCompletionChunk):
                raise TypeError(
                    f"OpenCode Go returned an unexpected stream chunk: {type(chunk)}."
                )
            choice = chunk.choices[0] if chunk.choices else None
            delta = choice.delta if choice else None
            if delta is not None or chunk.usage:
                try:
                    state.handle_chunk(chunk)
                except Exception as exc:
                    logger.error("OpenCode Go stream state error: %s", exc)
            if delta and (tool_calls := delta.tool_calls):
                for index, tool_call in enumerate(tool_calls):
                    if not hasattr(tool_call, "index") or tool_call.index is None:
                        tool_call.index = index
                    if tool_call.function and tool_call.function.arguments:
                        tool_call.type = "function"
            reasoning = self._extract_reasoning_content(chunk)
            llm_response.id = chunk.id
            llm_response.reasoning_content = reasoning
            should_yield = reasoning is not None
            if delta and delta.content:
                chunk_text = self._normalize_content(delta.content, strip=False)
                llm_response.result_chain = MessageChain(
                    chain=[Comp.Plain(chunk_text)],
                )
                should_yield = True
            if chunk.usage:
                usage = chunk.usage
            elif choice and (choice_usage := getattr(choice, "usage", None)):
                usage = choice_usage
            if should_yield:
                yield copy.deepcopy(llm_response)

        try:
            final_completion = state.get_final_completion()
            final_response = await self._parse_openai_completion(
                final_completion, tools
            )
        except Exception as exc:
            logger.error("OpenCode Go stream completion error: %s", exc)
            if llm_response.result_chain or llm_response.reasoning_content:
                return
            raise EmptyModelOutputError(
                "OpenCode Go stream has no usable output."
            ) from exc
        if usage:
            final_response.usage = self._extract_usage(usage)
        yield final_response
