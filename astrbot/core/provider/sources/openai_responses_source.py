"""OpenAI Responses API provider.

The Responses and Chat Completions protocols deliberately remain separate in
this module.  In particular, Responses uses input/output items rather than
Chat Completions messages and has a distinct streaming event protocol.
"""

import asyncio
import copy
import hashlib
import json
import random
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from openai import AsyncAzureOpenAI, AsyncOpenAI
from openai.types.responses.response import Response

from astrbot import logger
from astrbot.core.agent.history_sanitizer import IMAGE_HISTORY_PLACEHOLDER
from astrbot.core.agent.llm_types import (
    LLMCitation,
    LLMResponse,
    LLMSource,
    TokenUsage,
    ToolCallsResult,
)
from astrbot.core.agent.message import ContentPart, Message, ProviderMessageState
from astrbot.core.agent.tool import ToolSet
from astrbot.core.exceptions import MalformedToolCallError, ProviderResponseError
from astrbot.core.provider.provider import Provider
from astrbot.core.utils.media_utils import resolve_media_ref_to_base64_data
from astrbot.core.utils.network_utils import create_proxy_client

from ..register import register_provider_adapter
from .request_retry import retry_provider_request


def _value(item: Any, name: str, default: Any = None) -> Any:
    return (
        item.get(name, default)
        if isinstance(item, dict)
        else getattr(item, name, default)
    )


@dataclass(slots=True)
class _ResponsesStreamState:
    """Mutable state accumulated while consuming a Responses stream."""

    final: Response | None = None
    response_id: str | None = None
    last_sequence_number: int | None = None
    function_deltas: dict[str, dict[str, str]] = field(default_factory=dict)
    function_item_ids: dict[str, str] = field(default_factory=dict)


def _merge_responses_stream_event(
    state: _ResponsesStreamState,
    event: Any,
) -> list[LLMResponse]:
    """Merge one Responses event and return its visible streaming deltas."""
    sequence_number = _value(event, "sequence_number")
    if isinstance(sequence_number, int):
        state.last_sequence_number = sequence_number
    event_type = _value(event, "type", "")
    event_response = _value(event, "response")
    if event_response is not None:
        state.response_id = _value(event_response, "id", state.response_id)
    if event_response_id := _value(event, "response_id"):
        if isinstance(event_response_id, str):
            state.response_id = event_response_id

    if event_type == "response.output_item.added":
        item = _value(event, "item", {})
        if _value(item, "type") == "function_call":
            item_id = _value(item, "id")
            call_id = _value(item, "call_id") or item_id
            if isinstance(call_id, str):
                state.function_deltas.setdefault(
                    call_id,
                    {"name": _value(item, "name", ""), "arguments": ""},
                )
                if isinstance(item_id, str):
                    state.function_item_ids[item_id] = call_id
        return []
    if event_type == "response.output_text.delta":
        return [
            LLMResponse(
                "assistant",
                completion_text=_value(event, "delta", ""),
                is_chunk=True,
            )
        ]
    if event_type == "response.refusal.delta":
        delta = _value(event, "delta", "")
        return [
            LLMResponse(
                "assistant", completion_text=delta, is_chunk=True, refusal=delta
            )
        ]
    if event_type == "response.function_call_arguments.delta":
        item_id = _value(event, "item_id")
        call_id = (
            state.function_item_ids.get(item_id) if isinstance(item_id, str) else None
        ) or _value(event, "call_id")
        if not isinstance(call_id, str):
            call_id = str(_value(event, "output_index", "0"))
        delta = _value(event, "delta", "")
        state.function_deltas.setdefault(call_id, {"name": "", "arguments": ""})[
            "arguments"
        ] += delta
        return [
            LLMResponse(
                "tool",
                is_chunk=True,
                tools_call_ids=[call_id],
                tools_call_name=[state.function_deltas[call_id]["name"]],
                tools_call_extra_content={call_id: {"arguments_delta": delta}},
            )
        ]
    if event_type == "response.function_call_arguments.done":
        item_id = _value(event, "item_id")
        call_id = (
            state.function_item_ids.get(item_id) if isinstance(item_id, str) else None
        )
        if not isinstance(call_id, str):
            call_id = str(_value(event, "output_index", "0"))
        state.function_deltas[call_id] = {
            "name": _value(event, "name", ""),
            "arguments": _value(event, "arguments", ""),
        }
        return []
    if event_type == "response.output_item.done":
        item = _value(event, "item", {})
        if _value(item, "type") == "function_call":
            item_id = _value(item, "id")
            call_id = _value(item, "call_id") or item_id
            if isinstance(call_id, str):
                if isinstance(item_id, str):
                    state.function_item_ids[item_id] = call_id
                state.function_deltas[call_id] = {
                    "name": _value(item, "name", ""),
                    "arguments": _value(item, "arguments", ""),
                }
        return []
    if "reasoning" in event_type and event_type.endswith(".delta"):
        return [
            LLMResponse(
                "assistant",
                reasoning_content=_value(event, "delta", ""),
                is_chunk=True,
            )
        ]
    if event_type == "response.completed":
        state.final = event_response
        return []
    if event_type in {"response.failed", "response.incomplete", "error"}:
        raise ProviderResponseError(
            f"OpenAI Responses stream event {event_type}: "
            f"{_value(event, 'error') or _value(event, 'response')}"
        )
    return []


@register_provider_adapter("openai_responses", "OpenAI Responses API Provider Adapter")
class ProviderOpenAIResponses(Provider):
    """Provider for the public OpenAI Responses API."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_keys = list(self.get_keys())
        self.chosen_api_key = self.api_keys[0] if self.api_keys else ""
        self.timeout = int(provider_config.get("timeout", 120))
        headers = provider_config.get("custom_headers")
        self.custom_headers = (
            {str(key): str(value) for key, value in headers.items()}
            if isinstance(headers, dict)
            else None
        )
        client_options = {
            "api_key": self.chosen_api_key,
            "default_headers": self.custom_headers,
            "timeout": self.timeout,
            "http_client": create_proxy_client(
                "OpenAI Responses",
                provider_config,
            ),
        }
        api_base = provider_config.get("api_base")
        if provider_config.get("api_version"):
            if isinstance(api_base, str) and api_base:
                self.client = AsyncAzureOpenAI(
                    api_version=provider_config["api_version"],
                    base_url=api_base,
                    **client_options,
                )
            else:
                self.client = AsyncAzureOpenAI(
                    api_version=provider_config["api_version"],
                    **client_options,
                )
        else:
            self.client = AsyncOpenAI(
                base_url=api_base if isinstance(api_base, str) and api_base else None,
                **client_options,
            )
        self.set_model(provider_config.get("model", "unknown"))
        self._validate_config()

    def _validate_config(self) -> None:
        mode = self.provider_config.get("responses_state_mode", "stateless")
        if mode not in {"stateless", "previous_response_id", "conversation"}:
            raise ValueError(
                "responses_state_mode must be stateless, previous_response_id, or conversation"
            )
        if mode != "stateless" and not self.provider_config.get("store", False):
            raise ValueError("Stored Responses state modes require store=true")
        if self.provider_config.get("responses_background") and mode == "stateless":
            raise ValueError("Responses background mode requires a stored state mode")
        if self.provider_config.get(
            "responses_background"
        ) and not self.provider_config.get("store", False):
            raise ValueError("Responses background mode requires store=true")
        for name, default in (
            ("responses_background_poll_interval", 1),
            ("responses_background_timeout", 600),
        ):
            try:
                value = float(self.provider_config.get(name, default))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a positive number") from exc
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")
        web = self.provider_config.get("web_search", {})
        if isinstance(web, dict):
            allowed = web.get("allowed_domains", []) or []
            if not isinstance(allowed, list):
                raise ValueError("web search allowed_domains must be a list")
            if len(allowed) > 100:
                raise ValueError("web search supports at most 100 allowed domains")
            for domain in allowed:
                if not isinstance(domain, str) or "://" in domain or "/" in domain:
                    raise ValueError("web search domains must be bare domains")
            if web.get("search_context_size") not in {None, "low", "medium", "high"}:
                raise ValueError(
                    "web_search.search_context_size must be low, medium, or high"
                )

    def _client_for(self, key: str):
        return self.client.with_options(api_key=key)

    def get_current_key(self) -> str:
        return self.chosen_api_key

    def set_key(self, key: str) -> None:
        self.chosen_api_key = str(key)

    async def get_models(self) -> list[str]:
        models = await retry_provider_request(
            "OpenAI Responses",
            lambda: self._client_for(self.chosen_api_key).models.list(),
        )
        return sorted(model.id for model in models.data)

    async def terminate(self) -> None:
        await self.client.close()

    def _matching_state(self, message: dict, model: str) -> ProviderMessageState | None:
        state = message.get("provider_state")
        if isinstance(state, dict):
            state = ProviderMessageState.model_validate(state)
        if not isinstance(state, ProviderMessageState):
            return None
        if (
            state.provider_type != "openai_responses"
            or state.provider_id != str(self.provider_config.get("id", ""))
            or state.model != model
        ):
            return None
        return state

    @staticmethod
    def _fingerprint(messages: list[dict]) -> str:
        public_messages = [
            {key: value for key, value in message.items() if key != "provider_state"}
            for message in messages
        ]
        return hashlib.sha256(
            json.dumps(public_messages, sort_keys=True, default=str).encode()
        ).hexdigest()

    @staticmethod
    def _output_item_for_input(item: Any) -> dict[str, Any]:
        """Convert a returned Responses item into an item safe to send as input."""

        def to_plain_value(value: Any) -> Any:
            if hasattr(value, "model_dump"):
                value = value.model_dump(exclude_none=True)
            elif not isinstance(value, (dict, list, tuple)) and hasattr(
                value, "__dict__"
            ):
                value = vars(value)
            if isinstance(value, dict):
                return {key: to_plain_value(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [to_plain_value(item) for item in value]
            return copy.deepcopy(value)

        item = to_plain_value(item)
        if not isinstance(item, dict):
            raise ProviderResponseError(
                "OpenAI Responses returned a non-object output item"
            )
        # `status` is populated by the API on output items. It is not part of
        # the portable input contract and several OpenAI-compatible endpoints
        # reject it when manual context is replayed.
        item.pop("status", None)
        return item

    async def _content(self, content: Any, role: str) -> list[dict]:
        text_type = "output_text" if role == "assistant" else "input_text"
        if isinstance(content, str):
            return [{"type": text_type, "text": content}]
        parts: list[dict] = []
        for part in content or []:
            if not isinstance(part, dict):
                part = part.model_dump_for_context()
            kind = part.get("type")
            if kind == "text":
                parts.append({"type": text_type, "text": part.get("text", "")})
            elif kind == "image_url":
                url = _value(part.get("image_url"), "url")
                if not isinstance(url, str):
                    raise ProviderResponseError("Responses image part is missing a URL")
                if url == IMAGE_HISTORY_PLACEHOLDER:
                    parts.append({"type": text_type, "text": url})
                    continue
                if not url.startswith(("http://", "https://", "data:")):
                    data = await resolve_media_ref_to_base64_data(
                        url, media_type="image", strict=True
                    )
                    if data is None:
                        raise ProviderResponseError(
                            "Unable to resolve image for Responses API"
                        )
                    url = data.to_data_url()
                image = {"type": "input_image", "image_url": url}
                detail = _value(part.get("image_url"), "detail")
                if detail:
                    image["detail"] = detail
                parts.append(image)
            elif kind == "audio_url":
                raise ProviderResponseError(
                    "OpenAI Responses audio input is not supported by this provider"
                )
            elif kind == "think":
                continue
            else:
                raise ProviderResponseError(
                    f"Unsupported Responses input content type: {kind}"
                )
        return parts

    def _build_history(
        self,
        contexts: list[Message] | list[dict] | None,
        prompt: str | None,
        image_urls: list[str] | None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None,
        extra_user_content_parts: list[ContentPart] | None = None,
    ) -> list[dict]:
        messages = [
            message.model_dump()
            if isinstance(message, Message)
            else copy.deepcopy(message)
            for message in contexts or []
        ]
        if (
            prompt is not None
            or image_urls
            or (extra_user_content_parts and not messages)
        ):
            content: list[dict] = [{"type": "text", "text": prompt or "[Image]"}]
            if not prompt and not image_urls:
                content[0]["text"] = " "
            for part in extra_user_content_parts or []:
                if isinstance(part, dict):
                    content.append(copy.deepcopy(part))
                else:
                    content.append(part.model_dump_for_context())
            content.extend(
                {"type": "image_url", "image_url": {"url": url}}
                for url in image_urls or []
            )
            messages.append({"role": "user", "content": content})
        if tool_calls_result:
            results = (
                [tool_calls_result]
                if isinstance(tool_calls_result, ToolCallsResult)
                else tool_calls_result
            )
            for result in results:
                messages.extend(result.to_messages())

        return messages

    async def _input_items(
        self,
        contexts: list[Message] | list[dict] | None,
        prompt: str | None,
        image_urls: list[str] | None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None,
        model: str,
        extra_user_content_parts: list[ContentPart] | None = None,
    ) -> tuple[list[dict], str]:
        return await self._input_items_from_history(
            self._build_history(
                contexts,
                prompt,
                image_urls,
                tool_calls_result,
                extra_user_content_parts,
            ),
            model,
        )

    async def _input_items_from_history(
        self,
        messages: list[dict],
        model: str,
    ) -> tuple[list[dict], str]:
        instructions: list[str] = []
        items: list[dict] = []
        for message in messages:
            if message.get("_no_save") or message.get("role") == "_checkpoint":
                continue
            role = message.get("role")
            if role in {"system", "developer"}:
                content = message.get("content")
                if isinstance(content, str):
                    instructions.append(content)
                continue
            state = self._matching_state(message, model)
            if (
                state
                and self.provider_config.get("responses_state_mode", "stateless")
                == "stateless"
            ):
                output = state.data.get("output_items")
                if isinstance(output, list):
                    items.extend(self._output_item_for_input(item) for item in output)
                    continue
            if role == "tool":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.get("tool_call_id"),
                        "output": message.get("content", ""),
                    }
                )
            elif role == "assistant" and message.get("tool_calls"):
                for call in message["tool_calls"]:
                    call = call.model_dump() if hasattr(call, "model_dump") else call
                    function = call.get("function", {})
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": call.get("id"),
                            "name": function.get("name"),
                            "arguments": function.get("arguments", "{}"),
                        }
                    )
            elif role in {"user", "assistant"}:
                items.append(
                    {
                        "role": role,
                        "content": await self._content(message.get("content"), role),
                    }
                )
        return items, "\n\n".join(instructions)

    def _tools(self, func_tool: ToolSet | None) -> list[dict]:
        tools = (
            func_tool.openai_responses_schema()
            if func_tool and not func_tool.empty()
            else []
        )
        web = self.provider_config.get("web_search", {})
        if isinstance(web, dict) and web.get("enable"):
            tool: dict[str, Any] = {"type": "web_search"}
            for key in ("search_context_size",):
                if key in web:
                    tool[key] = copy.deepcopy(web[key])
            filters = {
                key: copy.deepcopy(web[key])
                for key in ("allowed_domains",)
                if web.get(key)
            }
            if filters:
                tool["filters"] = filters
            for key in ("user_location",):
                if key in web:
                    tool[key] = copy.deepcopy(web[key])
            tools.append(tool)
        return tools

    def _request_options(
        self,
        *,
        model: str,
        items: list[dict],
        instructions: str,
        func_tool: ToolSet | None,
        tool_choice: Any,
        extra: dict,
    ) -> dict:
        mode = self.provider_config.get("responses_state_mode", "stateless")
        config = self.provider_config
        options: dict[str, Any] = {
            "model": model,
            "input": items,
            "store": bool(config.get("store", mode != "stateless")),
        }
        if instructions:
            options["instructions"] = instructions
        tools = self._tools(func_tool)
        if tools:
            options["tools"] = tools
            if tool_choice == "none":
                options["tool_choice"] = "none"
            elif isinstance(tool_choice, str) and tool_choice in {"auto", "required"}:
                options["tool_choice"] = tool_choice
            elif isinstance(tool_choice, dict):
                if tool_choice.get("type") == "function" and isinstance(
                    tool_choice.get("function"), dict
                ):
                    options["tool_choice"] = {
                        "type": "function",
                        "name": tool_choice["function"].get("name"),
                    }
                else:
                    options["tool_choice"] = copy.deepcopy(tool_choice)
        for key in (
            "parallel_tool_calls",
            "max_output_tokens",
            "reasoning",
            "temperature",
            "top_p",
            "truncation",
            "include",
            "metadata",
            "safety_identifier",
            "service_tier",
            "prompt_cache_key",
            "prompt_cache_retention",
            "prompt_cache_options",
            "text",
        ):
            if key == "reasoning" and not isinstance(config.get(key), dict):
                continue
            if key in config:
                options[key] = copy.deepcopy(config[key])
        request_fields = {
            "background",
            "include",
            "max_output_tokens",
            "metadata",
            "parallel_tool_calls",
            "reasoning",
            "safety_identifier",
            "service_tier",
            "temperature",
            "text",
            "top_p",
            "truncation",
        }
        reserved = {
            "abort_signal",
            "audio_urls",
            "contexts",
            "extra_user_content_parts",
            "func_tool",
            "image_urls",
            "input",
            "instructions",
            "messages",
            "model",
            "prompt",
            "request_max_retries",
            "session_id",
            "stream",
            "system_prompt",
            "tool_calls_result",
            "tool_choice",
            "tools",
        }
        extra_body = copy.deepcopy(config.get("custom_extra_body", {}))
        if not isinstance(extra_body, dict):
            extra_body = {}
        for key, value in extra.items():
            if key in reserved:
                continue
            if key in request_fields:
                options[key] = copy.deepcopy(value)
            else:
                extra_body[key] = copy.deepcopy(value)
        if extra_body:
            options["extra_body"] = extra_body
        if config.get("responses_background"):
            options["background"] = True
        if mode == "stateless":
            options["store"] = False
            includes = list(options.get("include", []))
            if "reasoning.encrypted_content" not in includes:
                includes.append("reasoning.encrypted_content")
            options["include"] = includes
        elif options.get("store") is not True:
            raise ValueError("Stored Responses state modes require store=true")
        web = self.provider_config.get("web_search", {})
        if isinstance(web, dict):
            includes = list(options.get("include", []))
            if (
                web.get("include_sources")
                and "web_search_call.action.sources" not in includes
            ):
                includes.append("web_search_call.action.sources")
            if (
                web.get("include_raw_results")
                and "web_search_call.results" not in includes
            ):
                includes.append("web_search_call.results")
            if includes:
                options["include"] = includes
        return options

    def _parse(
        self,
        response: Response,
        *,
        requested_model: str | None = None,
    ) -> LLMResponse:
        text: list[str] = []
        reasoning: list[str] = []
        refusal: list[str] = []
        args: list[dict] = []
        names: list[str] = []
        ids: list[str] = []
        citations: list[LLMCitation] = []
        sources: list[LLMSource] = []
        output = _value(response, "output", []) or []
        for item in output:
            kind = _value(item, "type")
            if kind == "function_call":
                raw_args = _value(item, "arguments", "{}")
                try:
                    parsed = (
                        json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    )
                except json.JSONDecodeError as exc:
                    raise MalformedToolCallError(
                        "Responses returned malformed function arguments"
                    ) from exc
                if parsed is None:
                    parsed = {}
                if not isinstance(parsed, dict):
                    raise MalformedToolCallError(
                        "Responses function arguments must be a JSON object"
                    )
                args.append(parsed)
                names.append(_value(item, "name", ""))
                ids.append(_value(item, "call_id", ""))
            if kind == "reasoning":
                for summary in _value(item, "summary", []) or []:
                    reasoning.append(_value(summary, "text", ""))
            if kind == "web_search_call":
                for source in _value(_value(item, "action", {}), "sources", []) or []:
                    url = _value(source, "url")
                    if url:
                        sources.append(
                            LLMSource(
                                url=url,
                                title=_value(source, "title"),
                                snippet=_value(source, "snippet"),
                                source_type="web_search",
                            )
                        )
                for source in _value(item, "results", []) or []:
                    url = _value(source, "url")
                    if url:
                        sources.append(
                            LLMSource(
                                url=url,
                                title=_value(source, "title"),
                                snippet=_value(source, "snippet"),
                                source_type="web_search_result",
                            )
                        )
            for part in _value(item, "content", []) or []:
                part_type = _value(part, "type")
                if part_type in {"output_text", "text"}:
                    text.append(_value(part, "text", ""))
                elif part_type == "refusal":
                    refusal.append(_value(part, "refusal", ""))
                for annotation in _value(part, "annotations", []) or []:
                    if _value(annotation, "type") == "url_citation" and (
                        url := _value(annotation, "url")
                    ):
                        citations.append(
                            LLMCitation(
                                url=url,
                                title=_value(annotation, "title"),
                                start_index=_value(annotation, "start_index"),
                                end_index=_value(annotation, "end_index"),
                            )
                        )
        status = _value(response, "status")
        if status in {"failed", "cancelled"}:
            error = _value(response, "error")
            raise ProviderResponseError(
                f"OpenAI Responses ended with status={status}: {error or 'unknown error'}"
            )
        usage = _value(response, "usage")
        input_tokens = _value(usage, "input_tokens", 0) or 0
        cached = (
            _value(_value(usage, "input_tokens_details", {}), "cached_tokens", 0) or 0
        )
        state_data: dict[str, Any] = {
            "response_id": _value(response, "id"),
            "context_fingerprint": "",
        }
        if self.provider_config.get("responses_state_mode", "stateless") == "stateless":
            state_data["output_items"] = [
                self._output_item_for_input(item) for item in output
            ]

        result = LLMResponse(
            role="tool" if args else "assistant",
            completion_text="".join(text) or "".join(refusal),
            tools_call_args=args,
            tools_call_name=names,
            tools_call_ids=ids,
            reasoning_content="\n".join(reasoning) or None,
            raw_completion=response,
            id=_value(response, "id"),
            usage=TokenUsage(
                input_other=input_tokens - cached,
                input_cached=cached,
                output=_value(usage, "output_tokens", 0) or 0,
            ),
            finish_reason=status,
            incomplete_details=_value(response, "incomplete_details"),
            refusal="".join(refusal) or None,
            citations=self._dedupe(citations, lambda item: item.url),
            sources=self._dedupe(sources, lambda item: item.url),
            provider_state=ProviderMessageState(
                provider_type="openai_responses",
                provider_id=str(self.provider_config.get("id", "")),
                model=requested_model or _value(response, "model"),
                data=state_data,
            ),
        )
        if status == "incomplete":
            reason = _value(_value(response, "incomplete_details"), "reason")
            if reason == "content_filter":
                raise ProviderResponseError(
                    "OpenAI Responses was blocked by content filtering."
                )
            if not (
                result.completion_text
                or result.reasoning_content
                or result.tools_call_args
            ):
                raise ProviderResponseError(
                    "OpenAI Responses ended incomplete without visible output."
                )
        return result

    @staticmethod
    def _dedupe(items: list[Any], key: Any) -> list[Any]:
        seen: set[str] = set()
        result = []
        for item in items:
            value = key(item)
            if value and value not in seen:
                seen.add(value)
                result.append(item)
        return result

    async def _create(
        self,
        client: Any,
        options: dict,
        retries: int | None,
        abort_signal: asyncio.Event | None,
    ) -> Response:
        task = asyncio.create_task(
            retry_provider_request(
                "OpenAI Responses",
                lambda: client.responses.create(**options),
                max_attempts=retries,
            )
        )
        if abort_signal is None:
            return await task
        abort = asyncio.create_task(abort_signal.wait())
        done, _ = await asyncio.wait({task, abort}, return_when=asyncio.FIRST_COMPLETED)
        if abort in done:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise asyncio.CancelledError("OpenAI Responses request aborted")
        abort.cancel()
        await asyncio.gather(abort, return_exceptions=True)
        return await task

    async def _prepare_state_continuation(
        self,
        client: Any,
        history: list[dict],
        model: str,
        options: dict,
    ) -> None:
        """Attach valid stored Responses state and limit input to new history."""
        mode = self.provider_config.get("responses_state_mode", "stateless")
        use_incremental_input = False
        matching_index: int | None = None
        matching_state: ProviderMessageState | None = None
        for index in range(len(history) - 1, -1, -1):
            state = self._matching_state(history[index], model)
            if state is not None:
                matching_index = index
                matching_state = state
                break
        if matching_state is not None and matching_index is not None:
            if matching_state.data.get("context_fingerprint") != self._fingerprint(
                history[:matching_index]
            ):
                matching_state = None
                matching_index = None

        if mode == "previous_response_id" and matching_state is not None:
            response_id = matching_state.data.get("response_id")
            if isinstance(response_id, str) and response_id:
                options["previous_response_id"] = response_id
                options["store"] = True
                use_incremental_input = True
        elif mode == "conversation":
            conversation_id = (
                matching_state.data.get("conversation_id") if matching_state else None
            )
            if not isinstance(conversation_id, str) or not conversation_id:
                conversation = await client.conversations.create()
                conversation_id = _value(conversation, "id")
            options["conversation"] = conversation_id
            options["store"] = True
            use_incremental_input = matching_state is not None

        if use_incremental_input and matching_index is not None:
            options["input"], _ = await self._input_items_from_history(
                history[matching_index + 1 :],
                model,
            )

    @staticmethod
    def _remember_stream_response_id(state: _ResponsesStreamState, event: Any) -> None:
        """Remember a response ID from an event that will not be fully merged."""
        response_id = _value(event, "response_id")
        if isinstance(response_id, str):
            state.response_id = response_id
        response = _value(event, "response")
        if response is not None:
            response_id = _value(response, "id")
            if isinstance(response_id, str):
                state.response_id = response_id

    async def _close_stream(self, stream: AsyncIterator[Any]) -> None:
        """Close an SDK stream when it exposes an asynchronous close method."""
        aclose = getattr(stream, "aclose", None)
        if aclose is None:
            return
        try:
            await aclose()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Unable to close OpenAI Responses stream", exc_info=True)

    async def _next_abortable_stream_event(
        self,
        stream: AsyncIterator[Any],
        iterator: AsyncIterator[Any],
        state: _ResponsesStreamState,
        client: Any,
        abort_signal: asyncio.Event | None,
    ) -> Any:
        """Read one event while allowing an abort signal to stop pending I/O."""
        if abort_signal is None:
            return await anext(iterator)

        event_task = asyncio.ensure_future(anext(iterator))
        abort_task = asyncio.create_task(abort_signal.wait())
        try:
            done, _ = await asyncio.wait(
                {event_task, abort_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if abort_task in done:
                if event_task in done:
                    try:
                        self._remember_stream_response_id(state, event_task.result())
                    except StopAsyncIteration:
                        pass
                if state.response_id:
                    await self._cancel_background_response(client, state.response_id)
                await self._close_stream(stream)
                raise asyncio.CancelledError("OpenAI Responses stream aborted")
            return await event_task
        finally:
            for task in (event_task, abort_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(event_task, abort_task, return_exceptions=True)

    async def text_chat(
        self,
        prompt: str | None = None,
        session_id: str | None = None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        func_tool: ToolSet | None = None,
        contexts: list[Message] | list[dict] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None = None,
        model: str | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
        tool_choice: Literal["auto", "required"] = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        _ = session_id
        if audio_urls:
            raise ProviderResponseError(
                "OpenAI Responses audio input is not supported by this provider"
            )
        model = model or self.get_model()
        history = self._build_history(
            contexts,
            prompt,
            image_urls,
            tool_calls_result,
            extra_user_content_parts,
        )
        items, instructions = await self._input_items_from_history(history, model)
        if system_prompt:
            instructions = "\n\n".join(filter(None, [system_prompt, instructions]))
        options = self._request_options(
            model=model,
            items=items,
            instructions=instructions,
            func_tool=func_tool,
            tool_choice=tool_choice,
            extra=kwargs,
        )
        key = random.choice(self.api_keys or [self.chosen_api_key])
        client = self._client_for(key)
        mode = self.provider_config.get("responses_state_mode", "stateless")
        await self._prepare_state_continuation(client, history, model, options)
        response = await self._create(
            client,
            options,
            request_max_retries,
            kwargs.get("abort_signal"),
        )
        if self.provider_config.get("responses_background"):
            response = await self._poll_background(
                client,
                response,
                kwargs.get("abort_signal"),
                request_max_retries,
            )
        result = self._parse(response, requested_model=model)
        if result.provider_state:
            result.provider_state.data["context_fingerprint"] = self._fingerprint(
                history
            )
            if mode == "conversation":
                result.provider_state.data["conversation_id"] = options.get(
                    "conversation"
                )
        return result

    async def _cancel_background_response(self, client: Any, response_id: str) -> None:
        try:
            await retry_provider_request(
                "OpenAI Responses",
                lambda: client.responses.cancel(response_id),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "Unable to cancel OpenAI Responses background response %s",
                response_id,
                exc_info=True,
            )

    async def _poll_background(
        self,
        client: Any,
        response: Response,
        abort_signal: asyncio.Event | None,
        request_max_retries: int | None = None,
    ) -> Response:
        timeout = float(self.provider_config.get("responses_background_timeout", 600))
        interval = float(
            self.provider_config.get("responses_background_poll_interval", 1)
        )
        response_id = _value(response, "id")
        if not isinstance(response_id, str) or not response_id:
            raise ProviderResponseError(
                "OpenAI Responses background request did not return a response ID"
            )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while _value(response, "status") in {"queued", "in_progress"}:
            if abort_signal and abort_signal.is_set():
                await self._cancel_background_response(client, response_id)
                raise asyncio.CancelledError(
                    "OpenAI Responses background request aborted"
                )
            if loop.time() >= deadline:
                await self._cancel_background_response(client, response_id)
                raise ProviderResponseError(
                    "OpenAI Responses background request timed out"
                )
            wait_seconds = min(interval, max(0, deadline - loop.time()))
            if abort_signal is None:
                await asyncio.sleep(wait_seconds)
            else:
                abort = asyncio.create_task(abort_signal.wait())
                try:
                    done, _ = await asyncio.wait(
                        {abort}, timeout=wait_seconds, return_when=asyncio.ALL_COMPLETED
                    )
                    if abort in done:
                        await self._cancel_background_response(client, response_id)
                        raise asyncio.CancelledError(
                            "OpenAI Responses background request aborted"
                        )
                finally:
                    if not abort.done():
                        abort.cancel()
                    await asyncio.gather(abort, return_exceptions=True)
            if abort_signal and abort_signal.is_set():
                await self._cancel_background_response(client, response_id)
                raise asyncio.CancelledError(
                    "OpenAI Responses background request aborted"
                )
            response = await retry_provider_request(
                "OpenAI Responses",
                lambda: client.responses.retrieve(response_id),
                max_attempts=request_max_retries,
            )
        return response

    async def text_chat_stream(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[LLMResponse]:
        kwargs["stream"] = True
        # Build the request independently; a streamed response is not replayed after visible output.
        prompt = (
            kwargs.get("prompt") if "prompt" in kwargs else (args[0] if args else None)
        )
        if kwargs.get("audio_urls"):
            raise ProviderResponseError(
                "OpenAI Responses audio input is not supported by this provider"
            )
        model = kwargs.get("model") or self.get_model()
        contexts = kwargs.get("contexts")
        history = self._build_history(
            contexts,
            prompt,
            kwargs.get("image_urls"),
            kwargs.get("tool_calls_result"),
            kwargs.get("extra_user_content_parts"),
        )
        items, instructions = await self._input_items_from_history(history, model)
        if kwargs.get("system_prompt"):
            instructions = "\n\n".join(
                filter(None, [kwargs["system_prompt"], instructions])
            )
        options = self._request_options(
            model=model,
            items=items,
            instructions=instructions,
            func_tool=kwargs.get("func_tool"),
            tool_choice=kwargs.get("tool_choice", "auto"),
            extra=kwargs,
        )
        options["stream"] = True
        client = self._client_for(random.choice(self.api_keys or [self.chosen_api_key]))
        mode = self.provider_config.get("responses_state_mode", "stateless")
        await self._prepare_state_continuation(client, history, model, options)
        stream = cast(
            AsyncIterator[Any],
            await self._create(
                client,
                options,
                kwargs.get("request_max_retries"),
                kwargs.get("abort_signal"),
            ),
        )
        state = _ResponsesStreamState()
        iterator = stream.__aiter__()
        while True:
            try:
                while True:
                    event = await self._next_abortable_stream_event(
                        stream,
                        iterator,
                        state,
                        client,
                        kwargs.get("abort_signal"),
                    )
                    for delta in _merge_responses_stream_event(state, event):
                        yield delta
            except StopAsyncIteration:
                break
            except asyncio.CancelledError:
                raise
            except ProviderResponseError:
                raise
            except Exception as exc:
                if (
                    not options.get("background")
                    or not isinstance(state.response_id, str)
                    or not state.response_id
                ):
                    await self._close_stream(stream)
                    raise ProviderResponseError(
                        "OpenAI Responses stream interrupted after output; it was not replayed."
                    ) from exc
                replay_response_id = state.response_id
                await self._close_stream(stream)
                stream = cast(
                    AsyncIterator[Any],
                    await retry_provider_request(
                        "OpenAI Responses",
                        lambda: client.responses.retrieve(
                            replay_response_id,
                            stream=True,
                            starting_after=(
                                state.last_sequence_number
                                if state.last_sequence_number is not None
                                else 0
                            ),
                        ),
                        max_attempts=kwargs.get("request_max_retries"),
                    ),
                )
                iterator = stream.__aiter__()
        if state.final is None:
            raise ProviderResponseError(
                "OpenAI Responses stream ended without response.completed"
            )
        result = self._parse(state.final, requested_model=model)
        if result.provider_state:
            result.provider_state.data["sequence_number"] = state.last_sequence_number
            result.provider_state.data["context_fingerprint"] = self._fingerprint(
                history
            )
            if mode == "conversation":
                result.provider_state.data["conversation_id"] = options.get(
                    "conversation"
                )
        yield result
