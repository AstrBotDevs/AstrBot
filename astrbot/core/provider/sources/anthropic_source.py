import json
import anthropic
import base64
from typing import List
from mimetypes import guess_type

from anthropic import AsyncAnthropic
from anthropic.types import Message

from astrbot.core.utils.io import download_image_by_url
from astrbot.api.provider import Provider
from astrbot import logger
from astrbot.core.provider.func_tool_manager import FuncCall
from ..register import register_provider_adapter
from astrbot.core.provider.entities import LLMResponse
from typing import AsyncGenerator


@register_provider_adapter(
    "anthropic_chat_completion", "Anthropic Claude API 提供商适配器"
)
class ProviderAnthropic(Provider):
    def __init__(
        self,
        provider_config,
        provider_settings,
        default_persona=None,
    ) -> None:
        super().__init__(
            provider_config,
            provider_settings,
            default_persona,
        )

        self.chosen_api_key: str = ""
        self.api_keys: List = provider_config.get("key", [])
        self.chosen_api_key = self.api_keys[0] if len(self.api_keys) > 0 else ""
        self.base_url = provider_config.get("api_base", "https://api.anthropic.com")
        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)

        self.client = AsyncAnthropic(
            api_key=self.chosen_api_key, timeout=self.timeout, base_url=self.base_url
        )

        self.set_model(provider_config["model_config"]["model"])

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
                system_prompt = message["content"]
            elif message["role"] == "assistant":
                blocks = []
                if isinstance(message["content"], str):
                    blocks.append({"type": "text", "text": message["content"]})
                if "tool_calls" in message:
                    for tool_call in message["tool_calls"]:
                        blocks.append(  # noqa: PERF401
                            {
                                "type": "tool_use",
                                "name": tool_call["function"]["name"],
                                "input": json.loads(tool_call["function"]["arguments"])
                                if isinstance(tool_call["function"]["arguments"], str)
                                else tool_call["function"]["arguments"],
                                "id": tool_call["id"],
                            }
                        )
                new_messages.append(
                    {
                        "role": "assistant",
                        "content": blocks,
                    }
                )
            elif message["role"] == "tool":
                new_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message["tool_call_id"],
                                "content": message["content"],
                            }
                        ],
                    }
                )
            else:
                new_messages.append(message)

        return system_prompt, new_messages

    async def _query(self, payloads: dict, tools: FuncCall) -> LLMResponse:
        if tools:
            if tool_list := tools.get_func_desc_anthropic_style():
                payloads["tools"] = tool_list

        completion = await self.client.messages.create(**payloads, stream=False)

        assert isinstance(completion, Message)
        logger.debug(f"completion: {completion}")

        if len(completion.content) == 0:
            raise Exception("API 返回的 completion 为空。")

        llm_response = LLMResponse(role="assistant")

        for content_block in completion.content:
            if content_block.type == "text":
                completion_text = str(content_block.text).strip()
                llm_response.completion_text = completion_text

            if content_block.type == "tool_use":
                llm_response.tools_call_args.append(content_block.input)
                llm_response.tools_call_name.append(content_block.name)
                llm_response.tools_call_ids.append(content_block.id)
        # TODO(Soulter): 处理 end_turn 情况
        if not llm_response.completion_text and not llm_response.tools_call_args:
            raise Exception(f"Anthropic API 返回的 completion 无法解析：{completion}。")

        return llm_response

    async def _query_stream(
        self, payloads: dict, tools: FuncCall
    ) -> AsyncGenerator[LLMResponse, None]:
        if tools:
            if tool_list := tools.get_func_desc_anthropic_style():
                payloads["tools"] = tool_list

        # 用于累积工具调用信息
        tool_use_buffer = {}
        # 用于累积最终结果
        final_text = ""
        final_tool_calls = []

        async with self.client.messages.stream(**payloads) as stream:
            assert isinstance(stream, anthropic.AsyncMessageStream)
            async for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "text":
                        # 文本块开始
                        yield LLMResponse(
                            role="assistant", completion_text="", is_chunk=True
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
                        )
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
                                }
                            )

                            yield LLMResponse(
                                role="tool",
                                completion_text="",
                                tools_call_args=[tool_info["input"]],
                                tools_call_name=[tool_info["name"]],
                                tools_call_ids=[tool_info["id"]],
                                is_chunk=True,
                            )
                        except json.JSONDecodeError:
                            # JSON 解析失败，跳过这个工具调用
                            logger.warning(f"工具调用参数 JSON 解析失败: {tool_info}")

                        # 清理缓冲区
                        del tool_use_buffer[event.index]

        # 返回最终的完整结果
        final_response = LLMResponse(
            role="assistant", completion_text=final_text, is_chunk=False
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
        prompt,
        session_id=None,
        image_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        **kwargs,
    ) -> LLMResponse:
        if contexts is None:
            contexts = []
        new_record = await self.assemble_context(prompt, image_urls)
        context_query = [*contexts, new_record]
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

        model_config = self.provider_config.get("model_config", {})
        model_config["model"] = self.get_model()

        payloads = {"messages": new_messages, **model_config}

        # Anthropic has a different way of handling system prompts
        if system_prompt:
            payloads["system"] = system_prompt

        llm_response = None
        try:
            llm_response = await self._query(payloads, func_tool)
        except Exception as e:
            logger.error(f"发生了错误。Provider 配置如下: {model_config}")
            raise e

        return llm_response

    async def text_chat_stream(
        self,
        prompt,
        session_id=None,
        image_urls=...,
        func_tool=None,
        contexts=...,
        system_prompt=None,
        tool_calls_result=None,
        **kwargs,
    ):
        if contexts is None:
            contexts = []
        new_record = await self.assemble_context(prompt, image_urls)
        context_query = [*contexts, new_record]
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

        model_config = self.provider_config.get("model_config", {})
        model_config["model"] = self.get_model()

        payloads = {"messages": new_messages, **model_config}

        # Anthropic has a different way of handling system prompts
        if system_prompt:
            payloads["system"] = system_prompt

        async for llm_response in self._query_stream(payloads, func_tool):
            yield llm_response

    async def assemble_context(self, text: str, image_urls: List[str] = None):
        """组装上下文，支持文本和图片"""
        if not image_urls:
            return {"role": "user", "content": text}

        content = []
        content.append({"type": "text", "text": text})

        for image_url in image_urls:
            if image_url.startswith("http"):
                image_path = await download_image_by_url(image_url)
                image_data = await self.encode_image_bs64(image_path)
            elif image_url.startswith("file:///"):
                image_path = image_url.replace("file:///", "")
                image_data = await self.encode_image_bs64(image_path)
            else:
                image_data = await self.encode_image_bs64(image_url)

            if not image_data:
                logger.warning(f"图片 {image_url} 得到的结果为空，将忽略。")
                continue

            # Get mime type for the image
            mime_type, _ = guess_type(image_url)
            if not mime_type:
                mime_type = "image/jpeg"  # Default to JPEG if can't determine

            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": image_data.split("base64,")[1]
                        if "base64," in image_data
                        else image_data,
                    },
                }
            )

        return {"role": "user", "content": content}

    async def encode_image_bs64(self, image_url: str) -> str:
        """
        将图片转换为 base64
        """
        if image_url.startswith("base64://"):
            return image_url.replace("base64://", "data:image/jpeg;base64,")
        with open(image_url, "rb") as f:
            image_bs64 = base64.b64encode(f.read()).decode("utf-8")
            return "data:image/jpeg;base64," + image_bs64
        return ""

    def get_current_key(self) -> str:
        return self.chosen_api_key

    async def get_models(self) -> List[str]:
        models_str = []
        models = await self.client.models.list()
        models = sorted(models.data, key=lambda x: x.id)
        for model in models:
            models_str.append(model.id)
        return models_str

    def set_key(self, key: str):
        self.chosen_api_key = key
