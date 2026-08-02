import copy
import inspect
import json
from collections.abc import AsyncGenerator
from typing import Any

from openai.types.responses import Response

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core.agent.message import ContentPart, Message
from astrbot.core.agent.tool import ToolSet
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, TokenUsage, ToolCallsResult

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial
from .request_retry import retry_provider_request


@register_provider_adapter(
    "openai_responses",
    "OpenAI-compatible Responses API provider adapter",
)
class ProviderOpenAIResponses(ProviderOpenAIOfficial):
    """OpenAI-compatible stateless Responses API provider adapter."""

    _REASONING_STATE_TYPE = "openai_responses_reasoning"

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Initialize the Responses API client.

        Args:
            provider_config: Provider source and model configuration.
            provider_settings: Global provider settings.
        """
        super().__init__(provider_config, provider_settings)
        self.default_params = inspect.signature(
            self.client.responses.create,
        ).parameters.keys()

    @staticmethod
    def _field(value: Any, name: str, default: Any = None) -> Any:
        """Read a field from an SDK model or a plain dictionary.

        Args:
            value: SDK model or dictionary to inspect.
            name: Field name to read.
            default: Value returned when the field is absent.

        Returns:
            The field value or the provided default.
        """
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    def _convert_chat_messages_to_response_input(
        self,
        messages: list[dict],
    ) -> list[dict]:
        """Convert AstrBot's OpenAI chat history to Responses input items.

        The conversion preserves function call IDs and serialized reasoning output
        items so the complete history can be replayed without server-side state.

        Args:
            messages: AstrBot context in OpenAI Chat Completions format.

        Returns:
            A list of Responses API input items.
        """
        response_input: list[dict] = []
        host = (self.client.base_url.host or "").rstrip(".").lower()
        is_deepseek = (
            self.provider_config.get("provider") == "deepseek"
            or host == "api.deepseek.com"
        )

        for message in messages:
            if not isinstance(message, dict):
                continue

            role = message.get("role")
            if role == "tool":
                tool_call_id = message.get("tool_call_id")
                if not tool_call_id:
                    continue
                output = message.get("content", "")
                if not isinstance(output, str):
                    output = json.dumps(output, ensure_ascii=False, default=str)
                response_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call_id,
                        "output": output,
                    }
                )
                continue

            if role not in {"user", "assistant", "system", "developer"}:
                continue

            content = message.get("content")
            converted_content: str | list[dict] | None = None
            reasoning_items: list[dict] = []

            if isinstance(content, str):
                converted_content = content
            elif isinstance(content, list):
                content_parts: list[dict] = []
                assistant_text: list[str] = []
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    part_type = part.get("type")
                    if part_type == "think":
                        serialized_state = part.get("encrypted")
                        restored_items: list[dict] = []
                        if isinstance(serialized_state, str):
                            try:
                                state = json.loads(serialized_state)
                            except json.JSONDecodeError:
                                state = None
                            if (
                                isinstance(state, dict)
                                and state.get("type") == self._REASONING_STATE_TYPE
                                and isinstance(state.get("items"), list)
                            ):
                                restored_items = [
                                    item
                                    for item in state["items"]
                                    if isinstance(item, dict)
                                ]
                        if restored_items:
                            reasoning_items.extend(restored_items)
                        elif is_deepseek and part.get("think"):
                            reasoning_items.append(
                                {
                                    "type": "reasoning",
                                    "content": [
                                        {
                                            "type": "reasoning_text",
                                            "text": str(part["think"]),
                                        }
                                    ],
                                    "summary": [],
                                }
                            )
                        continue
                    if part_type == "text":
                        text = str(part.get("text", ""))
                        if role == "assistant":
                            assistant_text.append(text)
                        else:
                            content_parts.append({"type": "input_text", "text": text})
                        continue
                    if part_type == "image_url" and role != "assistant":
                        image_data = part.get("image_url")
                        if not isinstance(image_data, dict):
                            continue
                        image_url = image_data.get("url")
                        if not image_url:
                            continue
                        detail = image_data.get("detail", "auto")
                        if detail not in {"low", "high", "auto"}:
                            detail = "auto"
                        content_parts.append(
                            {
                                "type": "input_image",
                                "detail": detail,
                                "image_url": image_url,
                            }
                        )
                        continue
                    if part_type in {"audio_url", "input_audio"}:
                        if role == "assistant":
                            assistant_text.append("[Audio]")
                        else:
                            content_parts.append(
                                {"type": "input_text", "text": "[Audio]"}
                            )

                if role == "assistant":
                    converted_content = "".join(assistant_text)
                elif content_parts:
                    converted_content = content_parts
            elif content is not None:
                converted_content = str(content)

            response_input.extend(reasoning_items)
            if (
                converted_content is not None
                and converted_content != ""
                and converted_content != []
            ):
                response_input.append(
                    {
                        "type": "message",
                        "role": role,
                        "content": converted_content,
                    }
                )

            if role == "assistant":
                tool_calls = message.get("tool_calls")
                if isinstance(tool_calls, list):
                    for tool_call in tool_calls:
                        if not isinstance(tool_call, dict):
                            continue
                        function = tool_call.get("function")
                        call_id = tool_call.get("id")
                        if not isinstance(function, dict) or not call_id:
                            continue
                        arguments = function.get("arguments", "{}")
                        if not isinstance(arguments, str):
                            arguments = json.dumps(
                                arguments,
                                ensure_ascii=False,
                                default=str,
                            )
                        response_input.append(
                            {
                                "type": "function_call",
                                "call_id": call_id,
                                "name": function.get("name", ""),
                                "arguments": arguments,
                            }
                        )

        return response_input

    async def _prepare_chat_payload(
        self,
        prompt: str | None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        contexts: list[dict] | list[Message] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None = None,
        model: str | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
        **kwargs: Any,
    ) -> tuple[dict, list[dict]]:
        """Build a stateless Responses API payload and replayable context.

        Args:
            prompt: Current user prompt.
            image_urls: Image references attached to the prompt.
            audio_urls: Audio references attached to the prompt.
            contexts: Existing AstrBot conversation history.
            system_prompt: System-level instructions for this request.
            tool_calls_result: Function calls and their returned outputs.
            model: Optional per-request model override.
            extra_user_content_parts: Additional user content blocks.
            **kwargs: Reserved provider request arguments.

        Returns:
            The Responses payload and its chat-format source context.
        """
        context_query = copy.deepcopy(self._ensure_message_to_dicts(contexts))
        if prompt is not None:
            context_query.append(
                await self.assemble_context(
                    prompt or "",
                    image_urls,
                    audio_urls,
                    extra_user_content_parts,
                )
            )

        for message in context_query:
            if isinstance(message, dict):
                message.pop("_no_save", None)

        if tool_calls_result:
            if isinstance(tool_calls_result, ToolCallsResult):
                context_query.extend(tool_calls_result.to_openai_messages())
            else:
                for result in tool_calls_result:
                    context_query.extend(result.to_openai_messages())

        if self._context_contains_image(context_query):
            context_query = await self._materialize_context_image_parts(context_query)

        payloads: dict[str, Any] = {
            "input": self._convert_chat_messages_to_response_input(context_query),
            "model": model or self.get_model(),
            "store": False,
        }
        if system_prompt:
            payloads["instructions"] = system_prompt

        return payloads, context_query

    async def _query(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> LLMResponse:
        """Send a non-streaming Responses API request.

        Args:
            payloads: Prepared Responses API payload.
            tools: Functions available to the model.
            request_max_retries: Maximum transport-level request attempts.

        Returns:
            Normalized AstrBot LLM response.

        Raises:
            TypeError: If the SDK returns an unexpected response type.
        """
        if tools:
            response_tools = []
            for tool in tools.openai_schema():
                function = tool.get("function", {})
                response_tools.append({"type": "function", **function})
            if response_tools:
                payloads["tools"] = response_tools
                payloads["tool_choice"] = payloads.get("tool_choice", "auto")

        extra_body: dict[str, Any] = {}
        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        if isinstance(custom_extra_body, dict):
            extra_body.update(custom_extra_body)

        for key in list(payloads):
            if key not in self.default_params:
                extra_body[key] = payloads.pop(key)

        max_tokens = extra_body.pop("max_tokens", None)
        if max_tokens is not None and "max_output_tokens" not in extra_body:
            extra_body["max_output_tokens"] = max_tokens
        reasoning_effort = extra_body.pop("reasoning_effort", None)
        if reasoning_effort is not None and "reasoning" not in extra_body:
            extra_body["reasoning"] = {"effort": reasoning_effort}
        extra_body.pop("previous_response_id", None)
        extra_body.pop("conversation", None)
        extra_body.pop("store", None)
        payloads.pop("previous_response_id", None)
        payloads.pop("conversation", None)
        payloads["store"] = False

        response = await retry_provider_request(
            "OpenAI Responses",
            lambda: self.client.responses.create(
                **payloads,
                stream=False,
                extra_body=extra_body,
            ),
            max_attempts=request_max_retries,
        )
        if not isinstance(response, Response):
            raise TypeError(
                f"Responses API returned an unexpected type: {type(response)}: "
                f"{response}."
            )

        logger.debug("response: %s", response)
        return await self._parse_response(response, tools)

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> AsyncGenerator[LLMResponse, None]:
        """Send a streaming Responses API request.

        Args:
            payloads: Prepared Responses API payload.
            tools: Functions available to the model.
            request_max_retries: Maximum transport-level request attempts.

        Yields:
            Text/reasoning deltas followed by one complete normalized response.

        Raises:
            EmptyModelOutputError: If the stream ends without a terminal event.
        """
        if tools:
            response_tools = []
            for tool in tools.openai_schema():
                function = tool.get("function", {})
                response_tools.append({"type": "function", **function})
            if response_tools:
                payloads["tools"] = response_tools
                payloads["tool_choice"] = payloads.get("tool_choice", "auto")

        extra_body: dict[str, Any] = {}
        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        if isinstance(custom_extra_body, dict):
            extra_body.update(custom_extra_body)

        for key in list(payloads):
            if key not in self.default_params:
                extra_body[key] = payloads.pop(key)

        max_tokens = extra_body.pop("max_tokens", None)
        if max_tokens is not None and "max_output_tokens" not in extra_body:
            extra_body["max_output_tokens"] = max_tokens
        reasoning_effort = extra_body.pop("reasoning_effort", None)
        if reasoning_effort is not None and "reasoning" not in extra_body:
            extra_body["reasoning"] = {"effort": reasoning_effort}
        extra_body.pop("previous_response_id", None)
        extra_body.pop("conversation", None)
        extra_body.pop("store", None)
        payloads.pop("previous_response_id", None)
        payloads.pop("conversation", None)
        payloads["store"] = False

        stream = await retry_provider_request(
            "OpenAI Responses",
            lambda: self.client.responses.create(
                **payloads,
                stream=True,
                extra_body=extra_body,
            ),
            max_attempts=request_max_retries,
        )

        response_id: str | None = None
        async for event in stream:
            event_type = self._field(event, "type", "")
            event_response = self._field(event, "response")
            if event_response is not None:
                response_id = self._field(event_response, "id", response_id)

            if event_type == "error":
                code = self._field(event, "code", "stream_error")
                message = self._field(event, "message", "Responses stream failed")
                raise RuntimeError(
                    f"Responses API stream failed: {code}: {message}. "
                    f"response_id={response_id}"
                )

            if event_type in {
                "response.output_text.delta",
                "response.refusal.delta",
            }:
                delta = self._field(event, "delta", "")
                if delta:
                    yield LLMResponse(
                        "assistant",
                        result_chain=MessageChain(chain=[Comp.Plain(str(delta))]),
                        is_chunk=True,
                        id=response_id,
                    )
                continue

            if event_type in {
                "response.reasoning_text.delta",
                "response.reasoning_summary_text.delta",
            }:
                delta = self._field(event, "delta", "")
                if delta:
                    yield LLMResponse(
                        "assistant",
                        reasoning_content=str(delta),
                        is_chunk=True,
                        id=response_id,
                    )
                continue

            if event_type in {
                "response.completed",
                "response.incomplete",
                "response.failed",
            }:
                if event_response is None:
                    raise EmptyModelOutputError(
                        f"Responses stream terminal event has no response: {event_type}"
                    )
                yield await self._parse_response(event_response, tools)
                return

        raise EmptyModelOutputError(
            f"Responses stream ended without a terminal event. response_id={response_id}"
        )

    async def _parse_response(
        self,
        response: Response,
        tools: ToolSet | None,
    ) -> LLMResponse:
        """Normalize a Responses API response into AstrBot's LLM response.

        Args:
            response: SDK Responses API response object.
            tools: Functions available for resolving function call output items.

        Returns:
            Normalized AstrBot LLM response.

        Raises:
            EmptyModelOutputError: If the response contains no usable output.
            RuntimeError: If the provider reports a failed response.
        """
        response_id = self._field(response, "id")
        status = self._field(response, "status")
        if status == "failed":
            error = self._field(response, "error")
            code = self._field(error, "code", "unknown_error")
            message = self._field(error, "message", "Responses API request failed")
            raise RuntimeError(
                f"Responses API request failed: {code}: {message}. "
                f"response_id={response_id}"
            )

        incomplete_details = self._field(response, "incomplete_details")
        if self._field(incomplete_details, "reason") == "content_filter":
            raise RuntimeError(
                "Responses API output was rejected by the provider content filter. "
                f"response_id={response_id}"
            )

        llm_response = LLMResponse("assistant", id=response_id)
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        serialized_reasoning_items: list[dict] = []

        for item in self._field(response, "output", []) or []:
            item_type = self._field(item, "type")
            if item_type == "message":
                for content in self._field(item, "content", []) or []:
                    content_type = self._field(content, "type")
                    if content_type == "output_text":
                        text_parts.append(str(self._field(content, "text", "")))
                    elif content_type == "refusal":
                        text_parts.append(str(self._field(content, "refusal", "")))
                continue

            if item_type == "reasoning":
                if hasattr(item, "model_dump"):
                    serialized_item = item.model_dump(mode="json", exclude_none=True)
                elif isinstance(item, dict):
                    serialized_item = copy.deepcopy(item)
                else:
                    serialized_item = {}
                if serialized_item:
                    serialized_reasoning_items.append(serialized_item)

                item_reasoning: list[str] = []
                for content in self._field(item, "content", []) or []:
                    if self._field(content, "type") == "reasoning_text":
                        item_reasoning.append(str(self._field(content, "text", "")))
                if not item_reasoning:
                    for summary in self._field(item, "summary", []) or []:
                        summary_text = self._field(summary, "text", "")
                        if summary_text:
                            item_reasoning.append(str(summary_text))
                reasoning_parts.extend(item_reasoning)
                continue

            if item_type == "function_call" and tools is not None:
                arguments = self._field(item, "arguments", "{}")
                if isinstance(arguments, str):
                    try:
                        parsed_arguments = json.loads(arguments)
                    except json.JSONDecodeError as exc:
                        logger.error("Failed to parse function arguments: %s", exc)
                        parsed_arguments = {}
                else:
                    parsed_arguments = arguments
                if parsed_arguments is None:
                    parsed_arguments = {}
                llm_response.tools_call_args.append(parsed_arguments)
                llm_response.tools_call_name.append(str(self._field(item, "name", "")))
                llm_response.tools_call_ids.append(
                    str(self._field(item, "call_id", ""))
                )

        completion_text = "".join(text_parts)
        if completion_text:
            llm_response.result_chain = MessageChain().message(completion_text)
        if reasoning_parts:
            llm_response.reasoning_content = "\n".join(reasoning_parts)
        if serialized_reasoning_items:
            llm_response.reasoning_signature = json.dumps(
                {
                    "type": self._REASONING_STATE_TYPE,
                    "items": serialized_reasoning_items,
                },
                ensure_ascii=False,
            )
        if llm_response.tools_call_args:
            llm_response.role = "tool"

        usage = self._field(response, "usage")
        if usage is not None:
            input_details = self._field(usage, "input_tokens_details")
            cached_tokens = self._field(input_details, "cached_tokens", 0) or 0
            input_tokens = self._field(usage, "input_tokens", 0) or 0
            output_tokens = self._field(usage, "output_tokens", 0) or 0
            llm_response.usage = TokenUsage(
                input_other=input_tokens - cached_tokens,
                input_cached=cached_tokens,
                output=output_tokens,
            )
        else:
            llm_response.usage = TokenUsage()

        has_text = bool((llm_response.completion_text or "").strip())
        has_reasoning = bool((llm_response.reasoning_content or "").strip())
        if not has_text and not has_reasoning and not llm_response.tools_call_args:
            raise EmptyModelOutputError(
                "Responses API returned no usable output. "
                f"response_id={response_id}, status={status}"
            )

        llm_response.raw_completion = response
        return llm_response

    async def _handle_api_error(
        self,
        error: Exception,
        payloads: dict,
        context_query: list,
        func_tool: ToolSet | None,
        chosen_key: str,
        available_api_keys: list[str],
        retry_cnt: int,
        max_retries: int,
        image_fallback_used: bool = False,
    ) -> tuple:
        """Reuse common recovery behavior with chat-format source history.

        Args:
            error: Provider request error.
            payloads: Current Responses payload.
            context_query: Chat-format source history used to build ``input``.
            func_tool: Functions currently available to the model.
            chosen_key: API key used for the failed request.
            available_api_keys: Remaining API keys available for rotation.
            retry_cnt: Current retry index.
            max_retries: Maximum provider-level retries.
            image_fallback_used: Whether image fallback already ran.

        Returns:
            The common retry state tuple with a rebuilt Responses input payload.
        """
        compatibility_payloads = dict(payloads)
        compatibility_payloads["messages"] = context_query
        result = await super()._handle_api_error(
            error,
            compatibility_payloads,
            context_query,
            func_tool,
            chosen_key,
            available_api_keys,
            retry_cnt,
            max_retries,
            image_fallback_used=image_fallback_used,
        )

        (
            success,
            chosen_key,
            available_api_keys,
            retry_payloads,
            context_query,
            func_tool,
            image_fallback_used,
        ) = result
        retry_payloads.pop("messages", None)
        retry_payloads["input"] = self._convert_chat_messages_to_response_input(
            context_query
        )
        retry_payloads["store"] = False
        return (
            success,
            chosen_key,
            available_api_keys,
            retry_payloads,
            context_query,
            func_tool,
            image_fallback_used,
        )
