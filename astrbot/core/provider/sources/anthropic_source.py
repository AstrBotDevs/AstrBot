from typing import List
from mimetypes import guess_type

from anthropic import AsyncAnthropic
from anthropic.types import Message

from astrbot.core.utils.io import download_image_by_url
from astrbot.core.db import BaseDatabase
from astrbot.api.provider import Provider, Personality
from astrbot import logger
from astrbot.core.provider.func_tool_manager import FuncCall
from ..register import register_provider_adapter
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, ToolCallsResult
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "anthropic_chat_completion", "Anthropic Claude API 提供商适配器"
)
class ProviderAnthropic(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
        db_helper: BaseDatabase,
        persistant_history=True,
        default_persona: Personality = None,
    ) -> None:
        # Skip OpenAI's __init__ and call Provider's __init__ directly
        Provider.__init__(
            self,
            provider_config,
            provider_settings,
            persistant_history,
            db_helper,
            default_persona,
        )

        self.chosen_api_key = None
        self.api_keys: List = provider_config.get("key", [])
        self.chosen_api_key = self.api_keys[0] if len(self.api_keys) > 0 else None
        self.base_url = provider_config.get("api_base", "https://api.anthropic.com")
        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)

        self.client = AsyncAnthropic(
            api_key=self.chosen_api_key, timeout=self.timeout, base_url=self.base_url
        )

        self.set_model(provider_config["model_config"]["model"])

    async def _query(self, payloads: dict, tools: FuncCall) -> LLMResponse:
        if tools:
            tool_list = tools.get_func_desc_anthropic_style()
            if tool_list:
                payloads["tools"] = tool_list

        completion = await self.client.messages.create(**payloads, stream=False)

        assert isinstance(completion, Message)
        logger.debug(f"completion: {completion}")

        if len(completion.content) == 0:
            raise Exception("API 返回的 completion 为空。")
        # TODO: 如果进行函数调用，思维链被截断，用户可能需要思维链的内容
        # 选最后一条消息，如果要进行函数调用，anthropic会先返回文本消息的思维链，然后再返回函数调用请求
        content = completion.content[-1]

        llm_response = LLMResponse("assistant")

        if content.type == "text":
            # text completion
            completion_text = str(content.text).strip()
            # llm_response.completion_text = completion_text
            llm_response.result_chain = MessageChain().message(completion_text)

        # Anthropic每次只返回一个函数调用
        if completion.stop_reason == "tool_use":
            # tools call (function calling)
            args_ls = []
            func_name_ls = []
            tool_use_ids = []
            func_name_ls.append(content.name)
            args_ls.append(content.input)
            tool_use_ids.append(content.id)
            llm_response.role = "tool"
            llm_response.tools_call_args = args_ls
            llm_response.tools_call_name = func_name_ls
            llm_response.tools_call_ids = tool_use_ids

        if not llm_response.completion_text and not llm_response.tools_call_args:
            logger.error(f"API 返回的 completion 无法解析：{completion}。")
            raise Exception(f"API 返回的 completion 无法解析：{completion}。")

        llm_response.raw_completion = completion

        return llm_response

    async def text_chat(
        self,
        prompt: str,
        session_id: str = None,
        image_urls: List[str] = [],
        func_tool: FuncCall = None,
        contexts=[],
        system_prompt=None,
        tool_calls_result: ToolCallsResult = None,
        **kwargs,
    ) -> LLMResponse:
        if not prompt:
            prompt = "<image>"

        new_record = await self.assemble_context(prompt, image_urls)
        context_query = [*contexts, new_record]

        for part in context_query:
            if "_no_save" in part:
                del part["_no_save"]

        if tool_calls_result:
            # 暂时这样写。
            prompt += f"Here are the related results via using tools: {str(tool_calls_result.tool_calls_result)}"

        model_config = self.provider_config.get("model_config", {})

        payloads = {"messages": context_query, **model_config}
        # Anthropic has a different way of handling system prompts
        if system_prompt:
            payloads["system"] = system_prompt

        llm_response = None
        try:
            llm_response = await self._query(payloads, func_tool)

        except Exception as e:
            if "maximum context length" in str(e):
                retry_cnt = 20
                while retry_cnt > 0:
                    logger.warning(
                        f"上下文长度超过限制。尝试弹出最早的记录然后重试。当前记录条数: {len(context_query)}"
                    )
                    try:
                        await self.pop_record(context_query)
                        response = await self.client.messages.create(
                            messages=context_query, **model_config
                        )
                        llm_response = LLMResponse("assistant")
                        llm_response.result_chain = MessageChain().message(response.content[0].text)
                        llm_response.raw_completion = response
                        return llm_response
                    except Exception as e:
                        if "maximum context length" in str(e):
                            retry_cnt -= 1
                        else:
                            raise e
                return LLMResponse("err", "err: 请尝试 /reset 清除会话记录。")
            else:
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
        # raise NotImplementedError("This method is not implemented yet.")
        # 调用 text_chat 模拟流式
        llm_response = await self.text_chat(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls,
            func_tool=func_tool,
            contexts=contexts,
            system_prompt=system_prompt,
            tool_calls_result=tool_calls_result,
        )
        llm_response.is_chunk = True
        yield llm_response
        llm_response.is_chunk = False
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
