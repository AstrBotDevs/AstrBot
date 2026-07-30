import copy
import json
from collections.abc import AsyncGenerator
from typing import Any

from openai.types.chat.chat_completion import ChatCompletion

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core.agent.tool import ToolSet
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.request_retry import retry_provider_request

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    # 保留原有适配器 ID，避免现有用户配置失效。
    "xai_chat_completion",
    "xAI Responses Provider Adapter",
)
class ProviderXAI(ProviderOpenAIOfficial):
    """xAI Responses API provider.

    AstrBot 内部仍然使用 Chat Completions 格式维护上下文，
    本适配器负责：

    1. 将 Chat 格式请求转换成 Responses 格式；
    2. 调用 /v1/responses；
    3. 将 Responses 输出转换回 AstrBot 已支持的 ChatCompletion；
    4. 在启用 xai_native_search 时添加 xAI Web Search。
    """

    # 这些是典型的 Chat Completions 参数，但 xAI Responses 不提供
    # 等价语义。遇到这些参数时明确报错，避免静默忽略。
    _UNSUPPORTED_CHAT_PARAMS = {
        "frequency_penalty",
        "logit_bias",
        "logprobs",
        "n",
        "presence_penalty",
        "response_format",
        "stop",
        "stream_options",
    }

    @staticmethod
    def _get_value(obj: Any, key: str, default: Any = None) -> Any:
        """同时支持读取字典和 OpenAI SDK 的 Pydantic 响应对象。"""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _to_json_string(value: Any) -> str:
        """将函数参数或工具返回值转换成 Responses 要求的字符串。"""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)

    def _convert_message_content(self, content: Any, role: str) -> Any:
        """将 Chat message content 转换成 Responses input content。

        转换规则：

        - text -> input_text
        - image_url -> input_image
        - think -> 不发送给上游
        - 普通字符串保持不变
        """
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if not isinstance(content, list):
            return str(content)

        converted_parts: list[dict[str, Any]] = []

        for part in content:
            if not isinstance(part, dict):
                converted_parts.append(
                    {
                        "type": "input_text",
                        "text": str(part),
                    },
                )
                continue

            part_type = part.get("type")

            if part_type == "text":
                converted_parts.append(
                    {
                        "type": "input_text",
                        "text": str(part.get("text", "")),
                    },
                )
                continue

            if part_type == "image_url":
                image_data = part.get("image_url", {})

                if isinstance(image_data, str):
                    image_url = image_data
                    detail = None
                elif isinstance(image_data, dict):
                    image_url = image_data.get("url")
                    detail = image_data.get("detail")
                else:
                    image_url = None
                    detail = None

                if not image_url:
                    raise ValueError(
                        "xAI Responses image input is missing image_url.",
                    )

                image_part: dict[str, Any] = {
                    "type": "input_image",
                    "image_url": image_url,
                }
                if detail:
                    image_part["detail"] = detail

                converted_parts.append(image_part)
                continue

            if part_type in {"audio_url", "input_audio"}:
                # 当前 xAI 文本 Responses 接口正式支持文本和图片输入。
                # 与其发送无效请求，不如在适配器层提供明确错误。
                raise ValueError(
                    "xAI Responses text models do not support AstrBot audio input.",
                )

            if part_type == "think":
                # AstrBot 历史消息中的推理内容不作为普通输入回传。
                continue

            if part_type in {"input_text", "input_image", "input_file"}:
                # 已经是 Responses 格式时直接保留。
                converted_parts.append(copy.deepcopy(part))
                continue

            raise ValueError(
                f"Unsupported xAI Responses content part: {part_type!r}",
            )

        # 官方多轮示例允许 assistant 使用普通字符串。
        # 如果 assistant 只有文本，折叠成字符串可获得更好的兼容性。
        if role == "assistant" and all(
            part.get("type") == "input_text" for part in converted_parts
        ):
            return "".join(str(part.get("text", "")) for part in converted_parts)

        return converted_parts

    def _convert_messages_to_input(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """把完整 Chat 消息历史转换成 Responses input。

        AstrBot 的本地函数调用需要特殊处理：

        assistant.tool_calls -> function_call
        role=tool             -> function_call_output
        """
        response_input: list[dict[str, Any]] = []

        for message in messages:
            role = message.get("role")
            content = message.get("content")
            tool_calls = message.get("tool_calls") or []

            if role == "tool":
                call_id = message.get("tool_call_id")
                if not call_id:
                    raise ValueError(
                        "Tool result is missing tool_call_id.",
                    )

                response_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": self._to_json_string(content),
                    },
                )
                continue

            if role == "assistant" and tool_calls:
                converted_content = self._convert_message_content(content, role)

                # 模型可能同时返回文本和函数调用。
                if converted_content not in ("", None):             
                    response_input.append(
                        {
                            "role": "assistant",
                            "content": converted_content,
                        },
                    )

                for tool_call in tool_calls:
                    function = self._get_value(tool_call, "function", {})
                    call_id = self._get_value(tool_call, "id")
                    name = self._get_value(function, "name")
                    arguments = self._get_value(function, "arguments", "{}")

                    if not call_id or not name:
                        raise ValueError(
                            "Assistant tool call is missing id or function name.",
                        )

                    response_input.append(
                        {
                            "type": "function_call",
                            "call_id": call_id,
                            "name": name,
                            "arguments": self._to_json_string(arguments),
                        },
                    )
                continue

            if role not in {"system", "user", "assistant"}:
                raise ValueError(
                    f"Unsupported xAI Responses message role: {role!r}",
                )

            response_input.append(
                {
                    "role": role,
                    "content": self._convert_message_content(content, role),
                },
            )

        return response_input

    def _normalize_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        """把 Chat Completions 函数定义转换成 Responses 函数定义。

        Chat 格式：

        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {...}
            }
        }

        Responses 格式：

        {
            "type": "function",
            "name": "...",
            "description": "...",
            "parameters": {...}
        }
        """
        if tool.get("type") != "function":
            # web_search、x_search 等内置工具不需要转换。
            return copy.deepcopy(tool)

        nested_function = tool.get("function")
        if not isinstance(nested_function, dict):
            # 已经是 Responses 的扁平格式。
            return copy.deepcopy(tool)

        normalized: dict[str, Any] = {
            "type": "function",
            "name": nested_function["name"],
            "parameters": nested_function.get(
                "parameters",
                {
                    "type": "object",
                    "properties": {},
                },
            ),
        }

        if description := nested_function.get("description"):
            normalized["description"] = description

        if "strict" in nested_function:
            normalized["strict"] = nested_function["strict"]

        return normalized

    def _merge_tools(
        self,
        astrbot_tools: ToolSet | None,
        custom_tools: Any,
    ) -> list[dict[str, Any]]:
        """合并 AstrBot 本地工具、自定义工具和 xAI Web Search。"""
        merged_tools: list[dict[str, Any]] = []

        if astrbot_tools:
            openai_tools = astrbot_tools.get_func_desc_openai_style()
            merged_tools.extend(
                self._normalize_tool(tool) for tool in openai_tools
            )

        if custom_tools is not None:
            if not isinstance(custom_tools, list):
                raise ValueError(
                    "custom_extra_body.tools must be a list.",
                )

            merged_tools.extend(
                self._normalize_tool(tool) for tool in custom_tools
            )

        if self.provider_config.get("xai_native_search", False):
            has_web_search = any(
                tool.get("type") == "web_search" for tool in merged_tools
            )
            if not has_web_search:
                merged_tools.append({"type": "web_search"})

        # function 工具以名称去重，内置工具以类型去重。
        # AstrBot 本地函数排在前面，因此同名自定义函数不会覆盖本地函数。
        deduplicated: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for tool in merged_tools:
            tool_type = str(tool.get("type", ""))

            if tool_type == "function":
                identity = ("function", str(tool.get("name", "")))
            else:
                identity = ("builtin", tool_type)

            if identity in seen:
                continue

            seen.add(identity)
            deduplicated.append(tool)

        return deduplicated

    def _build_responses_request(
        self,
        payloads: dict[str, Any],
        tools: ToolSet | None,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        """构建最终传给 client.responses.create() 的参数。"""
        chat_payload = copy.deepcopy(payloads)

        # 沿用父类对空 assistant、孤立 tool message 等情况的清理逻辑。
        self._sanitize_assistant_messages(chat_payload)

        model = chat_payload.pop("model")
        messages = chat_payload.pop("messages")

        custom_extra_body = self.provider_config.get(
            "custom_extra_body",
            {},
        )
        if custom_extra_body is None:
            custom_extra_body = {}
        if not isinstance(custom_extra_body, dict):
            raise ValueError("custom_extra_body must be a dictionary.")

        extra_body = copy.deepcopy(custom_extra_body)

        # 如果未来父类给 payload 添加更多参数，也一并兼容。
        for key, value in chat_payload.items():
            extra_body.setdefault(key, value)

        custom_tools = extra_body.pop("tools", None)

        # Responses 原生参数优先于旧版 Chat 参数。
        if "max_output_tokens" not in extra_body:
            if "max_completion_tokens" in extra_body:
                extra_body["max_output_tokens"] = extra_body[
                    "max_completion_tokens"
                ]
            elif "max_tokens" in extra_body:
                extra_body["max_output_tokens"] = extra_body["max_tokens"]

        extra_body.pop("max_completion_tokens", None)
        extra_body.pop("max_tokens", None)

        # Chat 的 reasoning_effort 在 Responses 中位于 reasoning.effort。
        if "reasoning_effort" in extra_body and "reasoning" not in extra_body:
            extra_body["reasoning"] = {
                "effort": extra_body.pop("reasoning_effort"),
            }
        else:
            extra_body.pop("reasoning_effort", None)

        unsupported = sorted(
            self._UNSUPPORTED_CHAT_PARAMS.intersection(extra_body),
        )
        if unsupported:
            raise ValueError(
                "The following Chat Completions parameters are not supported "
                f"by xAI Responses: {', '.join(unsupported)}",
            )

        # 防止自定义请求体覆盖适配器生成的关键结构。
        protected_fields = {"input", "messages", "model", "stream"}
        overridden_fields = sorted(protected_fields.intersection(extra_body))
        if overridden_fields:
            raise ValueError(
                "custom_extra_body cannot override xAI Responses fields: "
                f"{', '.join(overridden_fields)}",
            )

        # AstrBot 自己维护完整对话上下文，不依赖服务端保存 Response。
        # 用户仍可在 custom_extra_body 中显式配置 store=true。
        extra_body.setdefault("store", False)

        merged_tools = self._merge_tools(tools, custom_tools)

        tool_choice = extra_body.pop(
            "tool_choice",
            chat_payload.get("tool_choice"),
        )
        if merged_tools and tool_choice is None:
            tool_choice = "auto"

        request: dict[str, Any] = {
            "model": model,
            "input": self._convert_messages_to_input(messages),
            "stream": stream,
        }

        if merged_tools:
            request["tools"] = merged_tools
            request["tool_choice"] = tool_choice

        if extra_body:
            # extra_body 允许较旧版本的 OpenAI SDK 向 xAI 传递
            # 新增的 Responses 专属字段。
            request["extra_body"] = extra_body

        return request

    def _response_to_chat_completion(self, response: Any) -> ChatCompletion:
        """把 xAI Response 标准化为 AstrBot 已支持的 ChatCompletion。

        这样无需修改 LLMResponse，也不会影响依赖 raw_completion
        为 ChatCompletion 的现有插件。
        """
        status = self._get_value(response, "status")
        error = self._get_value(response, "error")

        if status == "failed" or error:
            raise RuntimeError(
                f"xAI Responses request failed: {error!r}",
            )

        text_parts: list[str] = []
        refusal_parts: list[str] = []
        reasoning_parts: list[str] = []
        chat_tool_calls: list[dict[str, Any]] = []

        for item in self._get_value(response, "output", []) or []:
            item_type = self._get_value(item, "type")

            if item_type == "message":
                for content in self._get_value(item, "content", []) or []:
                    content_type = self._get_value(content, "type")
                    text = self._get_value(content, "text", "")

                    if content_type == "output_text" and text:
                        # xAI 默认的 Markdown 内联引用会保留在这里。
                        text_parts.append(str(text))
                    elif content_type == "refusal" and text:
                        refusal_parts.append(str(text))

            elif item_type == "reasoning":
                for summary in self._get_value(item, "summary", []) or []:
                    summary_text = self._get_value(summary, "text", "")
                    if summary_text:
                        reasoning_parts.append(str(summary_text))

            elif item_type == "function_call":
                call_id = self._get_value(item, "call_id")
                name = self._get_value(item, "name")
                arguments = self._get_value(item, "arguments", "{}")

                if call_id and name:
                    chat_tool_calls.append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": self._to_json_string(arguments),
                            },
                        },
                    )

            # web_search_call、x_search_call 等由 xAI 服务端完成，
            # 不能把它们交给 AstrBot 本地工具循环执行。

        # 某些 SDK 版本提供 output_text 快捷属性。
        if not text_parts:
            output_text = self._get_value(response, "output_text", "")
            if output_text:
                text_parts.append(str(output_text))

        message: dict[str, Any] = {
            "role": "assistant",
            "content": "".join(text_parts) or None,
        }

        if refusal_parts:
            message["refusal"] = "".join(refusal_parts)

        if reasoning_parts:
            # OpenAI 模型允许保留额外字段，父类解析器会读取该字段。
            message["reasoning_content"] = "\n".join(reasoning_parts)

        if chat_tool_calls:
            message["tool_calls"] = chat_tool_calls

        usage = self._get_value(response, "usage")
        usage_data = None

        if usage:
            input_tokens = (
                self._get_value(usage, "input_tokens")
                or self._get_value(usage, "prompt_tokens")
                or 0
            )
            output_tokens = (
                self._get_value(usage, "output_tokens")
                or self._get_value(usage, "completion_tokens")
                or 0
            )

            input_details = (
                self._get_value(usage, "input_tokens_details")
                or self._get_value(usage, "prompt_tokens_details")
            )
            cached_tokens = (
                self._get_value(input_details, "cached_tokens", 0)
                if input_details
                else 0
            )

            usage_data = {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "prompt_tokens_details": {
                    "cached_tokens": cached_tokens,
                },
            }

        has_usable_output = bool(
            text_parts
            or refusal_parts
            or reasoning_parts
            or chat_tool_calls
        )
        if not has_usable_output:
            response_id = self._get_value(response, "id")
            raise EmptyModelOutputError(
                "xAI Responses returned no usable output. "
                f"response_id={response_id}, status={status}",
            )

        if chat_tool_calls:
            finish_reason = "tool_calls"
        elif status == "incomplete":
            finish_reason = "length"
        else:
            finish_reason = "stop"

        completion_data: dict[str, Any] = {
            "id": self._get_value(response, "id", ""),
            "object": "chat.completion",
            "created": int(
                self._get_value(response, "created_at", 0) or 0,
            ),
            "model": self._get_value(
                response,
                "model",
                self.get_model(),
            ),
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason,
                },
            ],
        }

        if usage_data:
            completion_data["usage"] = usage_data

        return ChatCompletion.model_validate(completion_data)

    async def _query(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> LLMResponse:
        """执行非流式 xAI Responses 请求。"""
        request = self._build_responses_request(
            payloads,
            tools,
            stream=False,
        )

        response = await retry_provider_request(
            "xAI Responses",
            lambda: self.client.responses.create(**request),
            max_attempts=request_max_retries,
        )

        logger.debug("xAI Responses completion: %s", response)

        # 转成 ChatCompletion 后复用经过大量测试的父类解析器。
        completion = self._response_to_chat_completion(response)
        return await self._parse_openai_completion(completion, tools)

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> AsyncGenerator[LLMResponse, None]:
        """执行流式 xAI Responses 请求。"""
        request = self._build_responses_request(
            payloads,
            tools,
            stream=True,
        )

        stream = await retry_provider_request(
            "xAI Responses",
            lambda: self.client.responses.create(**request),
            max_attempts=request_max_retries,
        )

        final_response = None

        async for event in stream:
            event_type = self._get_value(event, "type")
            response_id = self._get_value(event, "response_id")

            if event_type == "response.output_text.delta":
                delta = self._get_value(event, "delta", "")
                if not delta:
                    continue

                yield LLMResponse(
                    role="assistant",
                    result_chain=MessageChain(
                        chain=[Comp.Plain(str(delta))],
                    ),
                    is_chunk=True,
                    id=response_id,
                )
                continue

            if event_type == "response.reasoning_summary_text.delta":
                delta = self._get_value(event, "delta", "")
                if not delta:
                    continue

                yield LLMResponse(
                    role="assistant",
                    reasoning_content=str(delta),
                    is_chunk=True,
                    id=response_id,
                )
                continue

            if event_type in {
                "response.completed",
                "response.incomplete",
            }:
                final_response = self._get_value(event, "response")
                continue

            if event_type in {"response.failed", "error"}:
                failed_response = self._get_value(event, "response")
                error = (
                    self._get_value(failed_response, "error")
                    if failed_response
                    else self._get_value(event, "error")
                )
                raise RuntimeError(
                    f"xAI Responses stream failed: {error!r}",
                )

        if final_response is None:
            raise EmptyModelOutputError(
                "xAI Responses stream ended without a final response.",
            )

        # 与现有 OpenAI 流式适配器一致：增量结束后再产生完整响应，
        # 其中包含最终工具调用和 usage。
        completion = self._response_to_chat_completion(final_response)
        yield await self._parse_openai_completion(completion, tools)
