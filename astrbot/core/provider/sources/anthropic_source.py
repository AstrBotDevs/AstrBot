import base64
import json
from collections.abc import AsyncGenerator

import anthropic
from anthropic import AsyncAnthropic
from anthropic.types import Message
from anthropic.types.message_delta_usage import MessageDeltaUsage
from anthropic.types.usage import Usage

from astrbot import logger
from astrbot.api.provider import Provider
from astrbot.core.agent.message import ContentPart, ImageURLPart, TextPart
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot.core.provider.func_tool_manager import ToolSet
from astrbot.core.utils.io import download_image_by_url

from ..register import register_provider_adapter


@register_provider_adapter(
    "anthropic_chat_completion",
    "Anthropic Claude API 提供商适配器",
)
class ProviderAnthropic(Provider):
    def __init__(
        self,
        provider_config,
        provider_settings,
    ) -> None:
        super().__init__(
            provider_config,
            provider_settings,
        )

        self.chosen_api_key: str = ""
        self.api_keys: list = super().get_keys()
        self.chosen_api_key = self.api_keys[0] if len(self.api_keys) > 0 else ""
        self.base_url = provider_config.get("api_base", "https://api.anthropic.com")
        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)

        self.client = AsyncAnthropic(
            api_key=self.chosen_api_key,
            timeout=self.timeout,
            base_url=self.base_url,
        )

        self.thinking_config = provider_config.get("anth_thinking_config", {})

        self.set_model(provider_config.get("model", "unknown"))

    def _prepare_payload(self, messages: list[dict]):
        """准备 Anthropic API 的请求 payload

        Args:
            messages: OpenAI 格式的消息列表，包含用户输入和系统提示等信息
        Returns:
            system_prompt: 系统提示内容
            new_messages: 处理后的消息列表，去除系统提示

        """
        system_prompt = ""
        new_messages = []
        for message in messages:
            if message["role"] == "system":
                system_prompt = message["content"] or "<empty system prompt>"
            elif message["role"] == "assistant":
                blocks = []
                reasoning_content = ""
                thinking_signature = ""
                if isinstance(message["content"], str) and message["content"].strip():
                    blocks.append({"type": "text", "text": message["content"]})
                elif isinstance(message["content"], list):
                    for part in message["content"]:
                        if part.get("type") == "think":
                            # only pick the last think part for now
                            reasoning_content = part.get("think")
                            thinking_signature = part.get("encrypted")
                        else:
                            blocks.append(part)

                if reasoning_content and thinking_signature:
                    blocks.insert(
                        0,
                        {
                            "type": "thinking",
                            "thinking": reasoning_content,
                            "signature": thinking_signature,
                        },
                    )

                if "tool_calls" in message and isinstance(message["tool_calls"], list):
                    for tool_call in message["tool_calls"]:
                        blocks.append(  # noqa: PERF401
                            {
                                "type": "tool_use",
                                "name": tool_call["function"]["name"],
                                "input": (
                                    json.loads(tool_call["function"]["arguments"])
                                    if isinstance(
                                        tool_call["function"]["arguments"],
                                        str,
                                    )
                                    else tool_call["function"]["arguments"]
                                ),
                                "id": tool_call["id"],
                            },
                        )
                new_messages.append(
                    {
                        "role": "assistant",
                        "content": blocks,
                    },
                )
            elif message["role"] == "tool":
                new_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message["tool_call_id"],
                                "content": message["content"] or "<empty response>",
                            },
                        ],
                    },
                )
            elif message["role"] == "user":
                if isinstance(message.get("content"), list):
                    converted_content = []
                    for part in message["content"]:
                        if part.get("type") == "image_url":
                            # Convert OpenAI image_url format to Anthropic image format
                            image_url_data = part.get("image_url", {})
                            url = image_url_data.get("url", "")
                            if url.startswith("data:"):
                                try:
                                    _, base64_data = url.split(",", 1)
                                    # Detect actual image format from binary data
                                    image_bytes = base64.b64decode(base64_data)
                                    media_type = self._detect_image_mime_type(
                                        image_bytes
                                    )
                                    converted_content.append(
                                        {
                                            "type": "image",
                                            "source": {
                                                "type": "base64",
                                                "media_type": media_type,
                                                "data": base64_data,
                                            },
                                        }
                                    )
                                except ValueError:
                                    logger.warning(
                                        f"Failed to parse image data URI: {url[:50]}..."
                                    )
                            else:
                                logger.warning(
                                    f"Unsupported image URL format for Anthropic: {url[:50]}..."
                                )
                        else:
                            converted_content.append(part)
                    new_messages.append(
                        {
                            "role": "user",
                            "content": converted_content,
                        }
                    )
                else:
                    new_messages.append(message)
            else:
                new_messages.append(message)

        return system_prompt, new_messages

    def _extract_usage(self, usage: Usage) -> TokenUsage:
        # https://docs.claude.com/en/docs/build-with-claude/prompt-caching#tracking-cache-performance
        return TokenUsage(
            input_other=usage.input_tokens or 0,
            input_cached=usage.cache_read_input_tokens or 0,
            output=usage.output_tokens,
        )

    def _update_usage(self, token_usage: TokenUsage, usage: MessageDeltaUsage) -> None:
        if usage.input_tokens is not None:
            token_usage.input_other = usage.input_tokens
        if usage.cache_read_input_tokens is not None:
            token_usage.input_cached = usage.cache_read_input_tokens
        if usage.output_tokens is not None:
            token_usage.output = usage.output_tokens

    async def _query(self, payloads: dict, tools: ToolSet | None) -> LLMResponse:
        if tools:
            if tool_list := tools.get_func_desc_anthropic_style():
                payloads["tools"] = tool_list

        extra_body = self.provider_config.get("custom_extra_body", {})

        if "max_tokens" not in payloads:
            payloads["max_tokens"] = 1024
        if self.thinking_config.get("budget"):
            payloads["thinking"] = {
                "budget_tokens": self.thinking_config.get("budget"),
                "type": "enabled",
            }

        completion = await self.client.messages.create(
            **payloads, stream=False, extra_body=extra_body
        )

        assert isinstance(completion, Message)
        logger.debug(f"completion: {completion}")

        if len(completion.content) == 0:
            raise Exception("API 返回的 completion 为空。")

        llm_response = LLMResponse(role="assistant")

        for content_block in completion.content:
            if content_block.type == "text":
                completion_text = str(content_block.text).strip()
                llm_response.completion_text = completion_text

            if content_block.type == "thinking":
                reasoning_content = str(content_block.thinking).strip()
                llm_response.reasoning_content = reasoning_content
                llm_response.reasoning_signature = content_block.signature

            if content_block.type == "tool_use":
                llm_response.tools_call_args.append(content_block.input)
                llm_response.tools_call_name.append(content_block.name)
                llm_response.tools_call_ids.append(content_block.id)

        llm_response.id = completion.id
        llm_response.usage = self._extract_usage(completion.usage)

        # TODO(Soulter): 处理 end_turn 情况
        if not llm_response.completion_text and not llm_response.tools_call_args:
            raise Exception(f"Anthropic API 返回的 completion 无法解析：{completion}。")

        return llm_response

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
    ) -> AsyncGenerator[LLMResponse, None]:
        if tools:
            if tool_list := tools.get_func_desc_anthropic_style():
                payloads["tools"] = tool_list

        # 用于累积工具调用信息
        tool_use_buffer = {}
        # 用于累积最终结果
        final_text = ""
        final_tool_calls = []
        id = None
        usage = TokenUsage()
        extra_body = self.provider_config.get("custom_extra_body", {})
        reasoning_content = ""
        reasoning_signature = ""

        if "max_tokens" not in payloads:
            payloads["max_tokens"] = 1024
        if self.thinking_config.get("budget"):
            payloads["thinking"] = {
                "budget_tokens": self.thinking_config.get("budget"),
                "type": "enabled",
            }

        async with self.client.messages.stream(
            **payloads, extra_body=extra_body
        ) as stream:
            assert isinstance(stream, anthropic.AsyncMessageStream)
            async for event in stream:
                if event.type == "message_start":
                    # the usage contains input token usage
                    id = event.message.id
                    usage = self._extract_usage(event.message.usage)
                if event.type == "content_block_start":
                    if event.content_block.type == "text":
                        # 文本块开始
                        yield LLMResponse(
                            role="assistant",
                            completion_text="",
                            is_chunk=True,
                            usage=usage,
                            id=id,
                        )
                    elif event.content_block.type == "tool_use":
                        # 工具使用块开始，初始化缓冲区
                        tool_use_buffer[event.index] = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "input": {},
                        }

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        # 文本增量
                        final_text += event.delta.text
                        yield LLMResponse(
                            role="assistant",
                            completion_text=event.delta.text,
                            is_chunk=True,
                            usage=usage,
                            id=id,
                        )
                    elif event.delta.type == "thinking_delta":
                        # 思考增量
                        reasoning = event.delta.thinking
                        if reasoning:
                            yield LLMResponse(
                                role="assistant",
                                reasoning_content=reasoning,
                                is_chunk=True,
                                usage=usage,
                                id=id,
                                reasoning_signature=reasoning_signature or None,
                            )
                            reasoning_content += reasoning
                    elif event.delta.type == "signature_delta":
                        reasoning_signature = event.delta.signature
                    elif event.delta.type == "input_json_delta":
                        # 工具调用参数增量
                        if event.index in tool_use_buffer:
                            # 累积 JSON 输入
                            if "input_json" not in tool_use_buffer[event.index]:
                                tool_use_buffer[event.index]["input_json"] = ""
                            tool_use_buffer[event.index]["input_json"] += (
                                event.delta.partial_json
                            )

                elif event.type == "content_block_stop":
                    # 内容块结束
                    if event.index in tool_use_buffer:
                        # 解析完整的工具调用
                        tool_info = tool_use_buffer[event.index]
                        try:
                            if "input_json" in tool_info:
                                tool_info["input"] = json.loads(tool_info["input_json"])

                            # 添加到最终结果
                            final_tool_calls.append(
                                {
                                    "id": tool_info["id"],
                                    "name": tool_info["name"],
                                    "input": tool_info["input"],
                                },
                            )

                            yield LLMResponse(
                                role="tool",
                                completion_text="",
                                tools_call_args=[tool_info["input"]],
                                tools_call_name=[tool_info["name"]],
                                tools_call_ids=[tool_info["id"]],
                                is_chunk=True,
                                usage=usage,
                                id=id,
                            )
                        except json.JSONDecodeError:
                            # JSON 解析失败，跳过这个工具调用
                            logger.warning(f"工具调用参数 JSON 解析失败: {tool_info}")

                        # 清理缓冲区
                        del tool_use_buffer[event.index]

                elif event.type == "message_delta":
                    if event.usage:
                        self._update_usage(usage, event.usage)

        # 返回最终的完整结果
        final_response = LLMResponse(
            role="assistant",
            completion_text=final_text,
            is_chunk=False,
            usage=usage,
            id=id,
            reasoning_content=reasoning_content,
            reasoning_signature=reasoning_signature or None,
        )

        if final_tool_calls:
            final_response.tools_call_args = [
                call["input"] for call in final_tool_calls
            ]
            final_response.tools_call_name = [call["name"] for call in final_tool_calls]
            final_response.tools_call_ids = [call["id"] for call in final_tool_calls]

        yield final_response

    async def text_chat(
        self,
        prompt=None,
        session_id=None,
        image_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        extra_user_content_parts=None,
        **kwargs,
    ) -> LLMResponse:
        if contexts is None:
            contexts = []
        new_record = None
        if prompt is not None:
            new_record = await self.assemble_context(
                prompt, image_urls, extra_user_content_parts
            )
        context_query = self._ensure_message_to_dicts(contexts)
        if new_record:
            context_query.append(new_record)

        if system_prompt:
            context_query.insert(0, {"role": "system", "content": system_prompt})

        for part in context_query:
            if "_no_save" in part:
                del part["_no_save"]

        # tool calls result
        if tool_calls_result:
            if not isinstance(tool_calls_result, list):
                context_query.extend(tool_calls_result.to_openai_messages())
            else:
                for tcr in tool_calls_result:
                    context_query.extend(tcr.to_openai_messages())

        system_prompt, new_messages = self._prepare_payload(context_query)

        model = model or self.get_model()

        payloads = {"messages": new_messages, "model": model}

        # Anthropic has a different way of handling system prompts
        if system_prompt:
            payloads["system"] = system_prompt

        llm_response = None
        try:
            llm_response = await self._query(payloads, func_tool)
        except Exception as e:
            raise e

        return llm_response

    async def text_chat_stream(
        self,
        prompt=None,
        session_id=None,
        image_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        extra_user_content_parts=None,
        **kwargs,
    ):
        if contexts is None:
            contexts = []
        new_record = None
        if prompt is not None:
            new_record = await self.assemble_context(
                prompt, image_urls, extra_user_content_parts
            )
        context_query = self._ensure_message_to_dicts(contexts)
        if new_record:
            context_query.append(new_record)
        if system_prompt:
            context_query.insert(0, {"role": "system", "content": system_prompt})

        for part in context_query:
            if "_no_save" in part:
                del part["_no_save"]

        # tool calls result
        if tool_calls_result:
            if not isinstance(tool_calls_result, list):
                context_query.extend(tool_calls_result.to_openai_messages())
            else:
                for tcr in tool_calls_result:
                    context_query.extend(tcr.to_openai_messages())

        system_prompt, new_messages = self._prepare_payload(context_query)

        model = model or self.get_model()

        payloads = {"messages": new_messages, "model": model}

        # Anthropic has a different way of handling system prompts
        if system_prompt:
            payloads["system"] = system_prompt

        async for llm_response in self._query_stream(payloads, func_tool):
            yield llm_response

    def _detect_image_mime_type(self, data: bytes) -> str:
        """根据图片二进制数据的 magic bytes 检测 MIME 类型"""
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:2] == b"\xff\xd8":
            return "image/jpeg"
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"

    async def assemble_context(
        self,
        text: str,
        image_urls: list[str] | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
    ):
        """组装上下文，支持文本和图片"""

        async def resolve_image_url(image_url: str) -> dict | None:
            if image_url.startswith("http"):
                image_path = await download_image_by_url(image_url)
                image_data, mime_type = await self.encode_image_bs64(image_path)
            elif image_url.startswith("file:///"):
                image_path = image_url.replace("file:///", "")
                image_data, mime_type = await self.encode_image_bs64(image_path)
            else:
                image_data, mime_type = await self.encode_image_bs64(image_url)

            if not image_data:
                logger.warning(f"图片 {image_url} 得到的结果为空，将忽略。")
                return None

            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": (
                        image_data.split("base64,")[1]
                        if "base64," in image_data
                        else image_data
                    ),
                },
            }

        content = []

        # 1. 用户原始发言（OpenAI 建议：用户发言在前）
        if text:
            content.append({"type": "text", "text": text})
        elif image_urls:
            # 如果没有文本但有图片，添加占位文本
            content.append({"type": "text", "text": "[图片]"})
        elif extra_user_content_parts:
            # 如果只有额外内容块，也需要添加占位文本
            content.append({"type": "text", "text": " "})

        # 2. 额外的内容块（系统提醒、指令等）
        if extra_user_content_parts:
            for block in extra_user_content_parts:
                if isinstance(block, TextPart):
                    content.append({"type": "text", "text": block.text})
                elif isinstance(block, ImageURLPart):
                    image_dict = await resolve_image_url(block.image_url.url)
                    if image_dict:
                        content.append(image_dict)
                else:
                    raise ValueError(f"不支持的额外内容块类型: {type(block)}")

        # 3. 图片内容
        if image_urls:
            for image_url in image_urls:
                image_dict = await resolve_image_url(image_url)
                if image_dict:
                    content.append(image_dict)

        # 如果只有主文本且没有额外内容块和图片，返回简单格式以保持向后兼容
        if (
            text
            and not extra_user_content_parts
            and not image_urls
            and len(content) == 1
            and content[0]["type"] == "text"
        ):
            return {"role": "user", "content": content[0]["text"]}

        # 否则返回多模态格式
        return {"role": "user", "content": content}

    async def encode_image_bs64(self, image_url: str) -> tuple[str, str]:
        """将图片转换为 base64，同时检测实际 MIME 类型"""
        if image_url.startswith("base64://"):
            raw_base64 = image_url.replace("base64://", "")
            try:
                image_bytes = base64.b64decode(raw_base64)
                mime_type = self._detect_image_mime_type(image_bytes)
            except Exception:
                mime_type = "image/jpeg"
            return f"data:{mime_type};base64,{raw_base64}", mime_type
        with open(image_url, "rb") as f:
            image_bytes = f.read()
            mime_type = self._detect_image_mime_type(image_bytes)
            image_bs64 = base64.b64encode(image_bytes).decode("utf-8")
            return f"data:{mime_type};base64,{image_bs64}", mime_type
        return "", "image/jpeg"

    def get_current_key(self) -> str:
        return self.chosen_api_key

    async def get_models(self) -> list[str]:
        models_str = []
        models = await self.client.models.list()
        models = sorted(models.data, key=lambda x: x.id)
        for model in models:
            models_str.append(model.id)
        return models_str

    def set_key(self, key: str):
        self.chosen_api_key = key
