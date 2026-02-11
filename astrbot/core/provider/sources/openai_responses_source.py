import inspect
import json
from collections.abc import AsyncGenerator
from typing import Any

from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_usage import ResponseUsage

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core.agent.message import ImageURLPart, Message, TextPart
from astrbot.core.agent.tool import ToolSet
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot.core.utils.network_utils import is_connection_error, log_connection_failure

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "openai_responses",
    "OpenAI API Responses Provider Adapter",
    default_config_tmpl={
        "id": "openai_responses",
        "provider": "openai",
        "type": "openai_responses",
        "provider_type": "chat_completion",
        "enable": True,
        "key": [],
        "api_base": "https://api.openai.com/v1",
        "timeout": 120,
        "proxy": "",
        "custom_headers": {},
        "custom_extra_body": {},
    },
    provider_display_name="OpenAI Responses",
)
class ProviderOpenAIResponses(ProviderOpenAIOfficial):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.default_params = inspect.signature(
            self.client.responses.create,
        ).parameters.keys()
        self.reasoning_key = "reasoning"

    def supports_native_compact(self) -> bool:
        return True

    async def compact_context(self, messages: list[Message]) -> list[Message]:
        if not messages:
            return messages

        message_dicts = self._ensure_message_to_dicts(messages)
        request_payload = {
            "model": self.get_model(),
            "input": self._messages_to_response_input(message_dicts),
        }

        request_options: dict[str, Any] = {}
        extra_headers = self._build_extra_headers()
        if extra_headers:
            request_options["extra_headers"] = extra_headers

        try:
            compact_response = await self.client.responses.compact(
                **request_payload,
                **request_options,
            )
        except Exception as e:
            if is_connection_error(e):
                proxy = self.provider_config.get("proxy", "")
                log_connection_failure("OpenAI", e, proxy)
            raise

        if hasattr(compact_response, "model_dump"):
            compact_data = compact_response.model_dump(mode="json")
        elif isinstance(compact_response, dict):
            compact_data = compact_response
        else:
            compact_data = {
                "output": getattr(compact_response, "output", []),
            }

        compact_input = self._extract_compact_input(compact_data)
        compact_messages = self._response_input_to_messages(compact_input)
        if not compact_messages:
            raise ValueError("Responses compact returned empty context.")
        return compact_messages

    def _extract_compact_input(self, compact_data: Any) -> list[dict[str, Any]]:
        if not isinstance(compact_data, dict):
            raise ValueError("Invalid compact response payload.")

        candidate_keys = (
            "input",
            "items",
            "input_items",
            "compacted_items",
            "compacted_input",
        )
        for key in candidate_keys:
            value = compact_data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        response_obj = compact_data.get("response")
        if isinstance(response_obj, dict):
            for key in candidate_keys:
                value = response_obj.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

        output = compact_data.get("output")
        if isinstance(output, list):
            return self._response_output_to_input_items(output)

        raise ValueError("Responses compact payload does not contain compacted items.")

    def _response_output_to_input_items(
        self, output: list[Any]
    ) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "message":
                role = item.get("role", "assistant")
                if role not in {"system", "developer", "user", "assistant"}:
                    role = "assistant"
                content = item.get("content", [])
                converted_content = self._output_content_to_input_content(content)
                converted.append(
                    {
                        "type": "message",
                        "role": role,
                        "content": converted_content,
                    }
                )
            elif item_type == "function_call":
                converted.append(
                    {
                        "type": "function_call",
                        "call_id": item.get("call_id", item.get("id", "")),
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", "{}"),
                    }
                )
        return converted

    def _output_content_to_input_content(self, content: Any) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        if not isinstance(content, list):
            return converted
        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = part.get("type")
            if part_type == "output_text":
                text = part.get("text")
                if text:
                    converted.append({"type": "input_text", "text": str(text)})
            elif part_type == "input_text":
                text = part.get("text")
                if text:
                    converted.append({"type": "input_text", "text": str(text)})
        return converted

    def _response_input_to_messages(
        self, input_items: list[dict[str, Any]]
    ) -> list[Message]:
        messages: list[Message] = []
        for item in input_items:
            item_type = item.get("type")
            if item_type == "message":
                role = item.get("role")
                if role not in {"system", "developer", "user", "assistant"}:
                    continue
                content = self._response_content_to_message_content(item.get("content"))
                if content is None:
                    content = ""
                messages.append(Message(role=role, content=content))
            elif item_type == "function_call":
                call_id = item.get("call_id") or item.get("id")
                name = item.get("name")
                arguments = item.get("arguments", "{}")
                if not call_id or not name:
                    continue
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments, ensure_ascii=False)
                messages.append(
                    Message(
                        role="assistant",
                        content="",
                        tool_calls=[
                            {
                                "type": "function",
                                "id": str(call_id),
                                "function": {
                                    "name": str(name),
                                    "arguments": arguments,
                                },
                            }
                        ],
                    )
                )
            elif item_type == "function_call_output":
                call_id = item.get("call_id")
                output = item.get("output", "")
                if not call_id:
                    continue
                messages.append(
                    Message(
                        role="tool",
                        tool_call_id=str(call_id),
                        content=str(output),
                    )
                )

        return messages

    def _response_content_to_message_content(self, content: Any) -> str | list:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""

        parts: list[Any] = []
        plain_text: list[str] = []
        has_non_text = False

        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = part.get("type")
            if part_type in {"input_text", "output_text", "text"}:
                text = part.get("text")
                if text is not None:
                    plain_text.append(str(text))
                    parts.append(TextPart(text=str(text)))
            elif part_type in {"input_image", "image_url"}:
                image_url = None
                if part_type == "input_image":
                    image_url = part.get("image_url") or part.get("file_url")
                else:
                    image_data = part.get("image_url")
                    if isinstance(image_data, dict):
                        image_url = image_data.get("url")
                    elif isinstance(image_data, str):
                        image_url = image_data
                if image_url:
                    has_non_text = True
                    parts.append(
                        ImageURLPart(
                            image_url=ImageURLPart.ImageURL(url=str(image_url))
                        )
                    )

        if has_non_text:
            return parts
        return "\n".join(plain_text).strip()

    def _messages_to_response_input(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        response_input: list[dict[str, Any]] = []

        for message in messages:
            role = message.get("role")
            content = message.get("content")
            tool_calls = message.get("tool_calls")

            if role in {"system", "developer", "user", "assistant"}:
                converted_content = self._message_content_to_response_content(content)
                message_item: dict[str, Any] = {
                    "type": "message",
                    "role": role,
                }
                if isinstance(converted_content, str):
                    message_item["content"] = converted_content
                else:
                    message_item["content"] = converted_content
                response_input.append(message_item)

            if role == "assistant" and isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    normalized = self._normalize_tool_call(tool_call)
                    if not normalized:
                        continue
                    response_input.append(
                        {
                            "type": "function_call",
                            "call_id": normalized["id"],
                            "name": normalized["name"],
                            "arguments": normalized["arguments"],
                        }
                    )

            if role == "tool":
                call_id = message.get("tool_call_id")
                if call_id:
                    response_input.append(
                        {
                            "type": "function_call_output",
                            "call_id": str(call_id),
                            "output": self._extract_text_from_content(content),
                        }
                    )

        return response_input

    def _normalize_tool_call(self, tool_call: Any) -> dict[str, str] | None:
        if isinstance(tool_call, str):
            try:
                tool_call = json.loads(tool_call)
            except Exception:
                return None
        if not isinstance(tool_call, dict):
            return None

        tool_type = tool_call.get("type")
        if tool_type != "function":
            return None

        function_data = tool_call.get("function", {})
        if not isinstance(function_data, dict):
            return None

        name = function_data.get("name")
        call_id = tool_call.get("id")
        arguments = function_data.get("arguments", "{}")
        if not name or not call_id:
            return None

        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, ensure_ascii=False)

        return {
            "id": str(call_id),
            "name": str(name),
            "arguments": arguments,
        }

    def _message_content_to_response_content(
        self, content: Any
    ) -> str | list[dict[str, Any]]:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""

        converted: list[dict[str, Any]] = []
        for part in content:
            if not isinstance(part, dict):
                continue

            part_type = part.get("type")
            if part_type in {"text", "input_text", "output_text"}:
                text = part.get("text")
                if text is not None:
                    converted.append({"type": "input_text", "text": str(text)})
            elif part_type in {"image_url", "input_image"}:
                image_part = self._normalize_image_part(part)
                if image_part:
                    converted.append(image_part)
            elif part_type == "input_file":
                file_id = part.get("file_id")
                file_url = part.get("file_url")
                file_data = part.get("file_data")
                input_file: dict[str, Any] = {"type": "input_file"}
                if file_id:
                    input_file["file_id"] = file_id
                elif file_url:
                    input_file["file_url"] = file_url
                elif file_data:
                    input_file["file_data"] = file_data
                filename = part.get("filename")
                if filename:
                    input_file["filename"] = filename
                if len(input_file) > 1:
                    converted.append(input_file)

        if not converted:
            return ""
        if len(converted) == 1 and converted[0].get("type") == "input_text":
            return str(converted[0].get("text", ""))
        return converted

    def _normalize_image_part(self, part: dict[str, Any]) -> dict[str, Any] | None:
        if part.get("type") == "input_image":
            image_url = part.get("image_url")
            if image_url:
                normalized = {"type": "input_image", "image_url": str(image_url)}
                detail = part.get("detail")
                if detail:
                    normalized["detail"] = detail
                return normalized
            file_id = part.get("file_id")
            if file_id:
                normalized = {"type": "input_image", "file_id": str(file_id)}
                detail = part.get("detail")
                if detail:
                    normalized["detail"] = detail
                return normalized
            return None

        image_data = part.get("image_url")
        image_url = None
        if isinstance(image_data, dict):
            image_url = image_data.get("url")
        elif isinstance(image_data, str):
            image_url = image_data

        if not image_url:
            return None

        normalized = {"type": "input_image", "image_url": str(image_url)}
        detail = part.get("detail")
        if detail:
            normalized["detail"] = detail
        return normalized

    def _extract_text_from_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if text is not None:
                        texts.append(str(text))
            return "\n".join(texts)
        return str(content) if content is not None else ""

    def _build_responses_input_and_instructions(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str | None]:
        response_input = self._messages_to_response_input(messages)
        filtered_input: list[dict[str, Any]] = []
        instruction_chunks: list[str] = []

        for item in response_input:
            if item.get("type") == "message" and item.get("role") in {
                "system",
                "developer",
            }:
                instruction_text = self._extract_text_from_content(item.get("content"))
                if instruction_text:
                    instruction_chunks.append(instruction_text)
                continue
            filtered_input.append(item)

        instructions = "\n\n".join(instruction_chunks).strip()
        return filtered_input, instructions or None

    def _build_extra_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if isinstance(self.custom_headers, dict):
            for key, value in self.custom_headers.items():
                if str(key).lower() == "authorization":
                    continue
                headers[str(key)] = str(value)
        return headers

    def _resolve_tool_strict(
        self,
        tool: dict[str, Any],
        function_body: dict[str, Any] | None,
    ) -> bool | None:
        if isinstance(function_body, dict) and isinstance(
            function_body.get("strict"), bool
        ):
            return function_body["strict"]
        if isinstance(tool.get("strict"), bool):
            return tool["strict"]
        default_strict = self.provider_config.get("responses_tool_strict")
        if isinstance(default_strict, bool):
            return default_strict
        return None

    def _convert_tools_to_responses(
        self, tool_list: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        response_tools: list[dict[str, Any]] = []
        for tool in tool_list:
            if not isinstance(tool, dict):
                continue
            if tool.get("type") != "function":
                continue

            function_body = tool.get("function")
            if isinstance(function_body, dict):
                name = function_body.get("name")
                if not name:
                    continue
                response_tool = {
                    "type": "function",
                    "name": name,
                    "description": function_body.get("description", ""),
                    "parameters": function_body.get("parameters", {}),
                }
                strict = self._resolve_tool_strict(tool, function_body)
                if strict is not None:
                    response_tool["strict"] = strict
                response_tools.append(response_tool)
                continue

            name = tool.get("name")
            if not name:
                continue
            response_tool = {
                "type": "function",
                "name": name,
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {}),
            }
            strict = self._resolve_tool_strict(tool, None)
            if strict is not None:
                response_tool["strict"] = strict
            response_tools.append(response_tool)

        return response_tools

    def _extract_response_usage(self, usage: ResponseUsage | None) -> TokenUsage | None:
        if usage is None:
            return None
        cached = 0
        if usage.input_tokens_details:
            cached = usage.input_tokens_details.cached_tokens or 0
        input_other = max(0, (usage.input_tokens or 0) - cached)
        output = usage.output_tokens or 0
        return TokenUsage(input_other=input_other, input_cached=cached, output=output)

    async def _parse_openai_response(
        self,
        response: OpenAIResponse,
        tools: ToolSet | None,
    ) -> LLMResponse:
        llm_response = LLMResponse("assistant")

        if response.error:
            raise Exception(f"Responses API error: {response.error.message}")

        completion_text = response.output_text.strip()
        if completion_text:
            llm_response.result_chain = MessageChain().message(completion_text)

        reasoning_segments: list[str] = []
        for output_item in response.output:
            output_type = getattr(output_item, "type", "")
            if output_type == "reasoning":
                summary = getattr(output_item, "summary", [])
                for summary_part in summary:
                    text = getattr(summary_part, "text", "")
                    if text:
                        reasoning_segments.append(str(text))
            if output_type == "function_call" and tools is not None:
                arguments = getattr(output_item, "arguments", "{}")
                function_name = getattr(output_item, "name", "")
                call_id = getattr(output_item, "call_id", "")
                parsed_arguments: dict[str, Any]
                try:
                    parsed_arguments = json.loads(arguments) if arguments else {}
                except Exception:
                    parsed_arguments = {}
                llm_response.tools_call_args.append(parsed_arguments)
                llm_response.tools_call_name.append(str(function_name))
                llm_response.tools_call_ids.append(str(call_id))

        if reasoning_segments:
            llm_response.reasoning_content = "\n".join(reasoning_segments)

        if not llm_response.completion_text and not llm_response.tools_call_args:
            raise Exception(f"Responses API returned empty output: {response}")

        llm_response.raw_completion = response
        llm_response.id = response.id
        llm_response.usage = self._extract_response_usage(response.usage)
        return llm_response

    async def _query(self, payloads: dict, tools: ToolSet | None) -> LLMResponse:
        request_payload = dict(payloads)
        response_input, instructions = self._build_responses_input_and_instructions(
            request_payload.pop("messages", [])
        )
        request_payload["input"] = response_input
        if instructions and not request_payload.get("instructions"):
            request_payload["instructions"] = instructions

        if tools:
            model = request_payload.get("model", "").lower()
            omit_empty_param_field = "gemini" in model
            tool_list = tools.get_func_desc_openai_style(
                omit_empty_parameter_field=omit_empty_param_field,
            )
            response_tools = self._convert_tools_to_responses(tool_list)
            if response_tools:
                request_payload["tools"] = response_tools

        extra_body: dict[str, Any] = {}
        for key in list(request_payload.keys()):
            if key not in self.default_params:
                extra_body[key] = request_payload.pop(key)

        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        if isinstance(custom_extra_body, dict):
            extra_body.update(custom_extra_body)

        extra_headers = self._build_extra_headers()
        completion = await self.client.responses.create(
            **request_payload,
            stream=False,
            extra_body=extra_body,
            extra_headers=extra_headers,
        )

        if not isinstance(completion, OpenAIResponse):
            raise TypeError(f"Unexpected response object: {type(completion)}")

        logger.debug(f"response: {completion}")
        return await self._parse_openai_response(completion, tools)

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
    ) -> AsyncGenerator[LLMResponse, None]:
        request_payload = dict(payloads)
        response_input, instructions = self._build_responses_input_and_instructions(
            request_payload.pop("messages", [])
        )
        request_payload["input"] = response_input
        if instructions and not request_payload.get("instructions"):
            request_payload["instructions"] = instructions

        if tools:
            model = request_payload.get("model", "").lower()
            omit_empty_param_field = "gemini" in model
            tool_list = tools.get_func_desc_openai_style(
                omit_empty_parameter_field=omit_empty_param_field,
            )
            response_tools = self._convert_tools_to_responses(tool_list)
            if response_tools:
                request_payload["tools"] = response_tools

        extra_body: dict[str, Any] = {}
        for key in list(request_payload.keys()):
            if key not in self.default_params:
                extra_body[key] = request_payload.pop(key)

        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        if isinstance(custom_extra_body, dict):
            extra_body.update(custom_extra_body)

        response_id: str | None = None
        extra_headers = self._build_extra_headers()
        try:
            async with self.client.responses.stream(
                **request_payload,
                extra_body=extra_body,
                extra_headers=extra_headers,
            ) as stream:
                async for event in stream:
                    event_type = getattr(event, "type", "")
                    if event_type == "response.created":
                        response_obj = getattr(event, "response", None)
                        if response_obj:
                            response_id = getattr(response_obj, "id", None)
                        continue

                    if event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            yield LLMResponse(
                                role="assistant",
                                result_chain=MessageChain(
                                    chain=[Comp.Plain(str(delta))]
                                ),
                                is_chunk=True,
                                id=response_id,
                            )
                        continue

                    if event_type == "response.reasoning_summary_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            yield LLMResponse(
                                role="assistant",
                                reasoning_content=str(delta),
                                is_chunk=True,
                                id=response_id,
                            )
                        continue

                    if event_type == "error":
                        raise Exception(
                            f"Responses stream error: {getattr(event, 'code', 'unknown')} {getattr(event, 'message', '')}"
                        )

                    if event_type == "response.failed":
                        response_obj = getattr(event, "response", None)
                        error_obj = (
                            getattr(response_obj, "error", None)
                            if response_obj
                            else None
                        )
                        if error_obj is not None:
                            raise Exception(
                                f"Responses stream failed: {getattr(error_obj, 'code', 'unknown')} {getattr(error_obj, 'message', '')}"
                            )
                        raise Exception("Responses stream failed.")

                final_response = await stream.get_final_response()
        except Exception as e:
            if self._is_retryable_upstream_error(e) or is_connection_error(e):
                logger.warning(
                    "Responses stream failed, fallback to non-stream create: %s",
                    e,
                )
                yield await self._query(payloads, tools)
                return
            raise

        yield await self._parse_openai_response(final_response, tools)

    def _is_retryable_upstream_error(self, e: Exception) -> bool:
        status_code = getattr(e, "status_code", None)
        if status_code in {500, 502, 503, 504}:
            return True

        message = str(e).lower()
        if "upstream request failed" in message:
            return True

        body = getattr(e, "body", None)
        if isinstance(body, dict):
            error_obj = body.get("error", {})
            if isinstance(error_obj, dict):
                if str(error_obj.get("type", "")).lower() == "upstream_error":
                    return True

        return False

    async def _handle_api_error(
        self,
        e: Exception,
        payloads: dict,
        context_query: list,
        func_tool: ToolSet | None,
        chosen_key: str,
        available_api_keys: list[str],
        retry_cnt: int,
        max_retries: int,
    ) -> tuple:
        if is_connection_error(e):
            proxy = self.provider_config.get("proxy", "")
            log_connection_failure("OpenAI", e, proxy)
        return await super()._handle_api_error(
            e,
            payloads,
            context_query,
            func_tool,
            chosen_key,
            available_api_keys,
            retry_cnt,
            max_retries,
        )
