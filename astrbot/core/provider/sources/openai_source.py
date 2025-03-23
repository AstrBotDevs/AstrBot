import base64
import json
import os
import inspect

from openai import AsyncOpenAI, AsyncAzureOpenAI
from openai.types.chat.chat_completion import ChatCompletion
from openai._exceptions import NotFoundError, UnprocessableEntityError
from astrbot.core.utils.io import download_image_by_url

from astrbot.core.db import BaseDatabase
from astrbot.api.provider import Provider, Personality
from astrbot import logger
from astrbot.core.provider.func_tool_manager import FuncCall
from typing import List
from ..register import register_provider_adapter
from astrbot.core.provider.entites import LLMResponse


@register_provider_adapter(
    "openai_chat_completion", "OpenAI API Chat Completion 提供商适配器"
)
class ProviderOpenAIOfficial(Provider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
        db_helper: BaseDatabase,
        persistant_history=True,
        default_persona: Personality = None,
    ) -> None:
        super().__init__(
            provider_config,
            provider_settings,
            persistant_history,
            db_helper,
            default_persona,
        )
        self.chosen_api_key = None
        self.api_keys: List = provider_config.get("key", [])
        self.chosen_api_key = self.api_keys[0] if len(self.api_keys) > 0 else None
        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)
        # 适配 azure openai #332
        if "api_version" in provider_config:
            # 使用 azure api
            self.client = AsyncAzureOpenAI(
                api_key=self.chosen_api_key,
                api_version=provider_config.get("api_version", None),
                base_url=provider_config.get("api_base", None),
                timeout=self.timeout,
            )
        else:
            # 使用 openai api
            self.client = AsyncOpenAI(
                api_key=self.chosen_api_key,
                base_url=provider_config.get("api_base", None),
                timeout=self.timeout,
            )

        self.default_params = inspect.signature(
            self.client.chat.completions.create
        ).parameters.keys()

        model_config = provider_config.get("model_config", {})
        model = model_config.get("model", "unknown")
        self.set_model(model)

    async def get_models(self):
        try:
            models_str = []
            models = await self.client.models.list()
            models = sorted(models.data, key=lambda x: x.id)
            for model in models:
                models_str.append(model.id)
            return models_str
        except NotFoundError as e:
            raise Exception(f"获取模型列表失败：{e}")

    async def _query(self, payloads: dict, tools: FuncCall) -> LLMResponse:
        if tools:
            tool_list = tools.get_func_desc_openai_style()
            if tool_list:
                payloads["tools"] = tool_list

        # 不在默认参数中的参数放在 extra_body 中
        extra_body = {}
        to_del = []
        for key in payloads.keys():
            if key not in self.default_params:
                extra_body[key] = payloads[key]
                to_del.append(key)
        for key in to_del:
            del payloads[key]

        completion = await self.client.chat.completions.create(
            **payloads, stream=False, extra_body=extra_body
        )

        if not isinstance(completion, ChatCompletion):
            raise Exception(
                f"API 返回的 completion 类型错误：{type(completion)}: {completion}。"
            )

        logger.debug(f"completion: {completion}")

        if len(completion.choices) == 0:
            raise Exception("API 返回的 completion 为空。")
        choice = completion.choices[0]

        llm_response = LLMResponse("assistant")

        if choice.message.content:
            # text completion
            completion_text = str(choice.message.content).strip()
            llm_response.completion_text = completion_text

        if choice.message.tool_calls:
            # tools call (function calling)
            args_ls = []
            func_name_ls = []
            for tool_call in choice.message.tool_calls:
                for tool in tools.func_list:
                    if tool.name == tool_call.function.name:
                        args = json.loads(tool_call.function.arguments)
                        args_ls.append(args)
                        func_name_ls.append(tool_call.function.name)
            llm_response.role = "tool"
            llm_response.tools_call_args = args_ls
            llm_response.tools_call_name = func_name_ls

        if choice.finish_reason == "content_filter":
            raise Exception(
                "API 返回的 completion 由于内容安全过滤被拒绝(非 AstrBot)。"
            )

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
        **kwargs,
    ) -> LLMResponse:
        new_record = await self.assemble_context(prompt, image_urls)
        context_query = [*contexts, new_record]
        if system_prompt:
            context_query.insert(0, {"role": "system", "content": system_prompt})

        for part in context_query:
            if "_no_save" in part:
                del part["_no_save"]

        model_config = self.provider_config.get("model_config", {})
        model_config["model"] = self.get_model()

        payloads = {"messages": context_query, **model_config}
        llm_response = None
        try:
            llm_response = await self._query(payloads, func_tool)
        except UnprocessableEntityError as e:
            logger.warning(f"不可处理的实体错误：{e}，尝试删除图片。")
            # 尝试删除所有 image
            new_contexts = await self._remove_image_from_context(context_query)
            payloads["messages"] = new_contexts
            context_query = new_contexts
            llm_response = await self._query(payloads, func_tool)
        except Exception as e:
            if "maximum context length" in str(e):
                # 重试 10 次
                retry_cnt = 20
                while retry_cnt > 0:
                    logger.warning(
                        f"上下文长度超过限制。尝试弹出最早的记录然后重试。当前记录条数: {len(context_query)}"
                    )
                    try:
                        await self.pop_record(context_query)
                        llm_response = await self._query(payloads, func_tool)
                        break
                    except Exception as e:
                        if "maximum context length" in str(e):
                            retry_cnt -= 1
                        else:
                            raise e
                if retry_cnt == 0:
                    llm_response = LLMResponse(
                        "err", "err: 请尝试 /reset 清除会话记录。"
                    )
            elif "The model is not a VLM" in str(e):  # siliconcloud
                # 尝试删除所有 image
                new_contexts = await self._remove_image_from_context(context_query)
                payloads["messages"] = new_contexts
                llm_response = await self._query(payloads, func_tool)

            # openai, ollama, gemini openai, siliconcloud 的错误提示与 code 不统一，只能通过字符串匹配
            elif (
                "does not support Function Calling" in str(e)
                or "does not support tools" in str(e)
                or "Function call is not supported" in str(e)
                or "Function calling is not enabled" in str(e)
                or "Tool calling is not supported" in str(e)
                or "No endpoints found that support tool use" in str(e)
                or "model does not support function calling" in str(e)
                or ("tool" in str(e) and "support" in str(e).lower())
                or ("function" in str(e) and "support" in str(e).lower())
            ):
                logger.info(
                    f"{self.get_model()} 不支持函数工具调用，已自动去除，不影响使用。"
                )
                if "tools" in payloads:
                    del payloads["tools"]
                llm_response = await self._query(payloads, None)
            else:
                logger.error(f"发生了错误。Provider 配置如下: {self.provider_config}")

                if "tool" in str(e).lower() and "support" in str(e).lower():
                    logger.error(
                        "疑似该模型不支持函数调用工具调用。请输入 /tool off_all"
                    )

                if "Connection error." in str(e):
                    proxy = os.environ.get("http_proxy", None)
                    if proxy:
                        logger.error(
                            f"可能为代理原因，请检查代理是否正常。当前代理: {proxy}"
                        )

                raise e

        return llm_response

    async def _remove_image_from_context(self, contexts: List):
        """
        从上下文中删除所有带有 image 的记录
        """
        new_contexts = []

        flag = False
        for context in contexts:
            if flag:
                flag = False  # 删除 image 后，下一条（LLM 响应）也要删除
                continue
            if isinstance(context["content"], list):
                flag = True
                # continue
                new_content = []
                for item in context["content"]:
                    if isinstance(item, dict) and "image_url" in item:
                        continue
                    new_content.append(item)
                if not new_content:
                    # 用户只发了图片
                    new_content = [{"type": "text", "text": "[图片]"}]
                context["content"] = new_content
            new_contexts.append(context)
        return new_contexts

    def get_current_key(self) -> str:
        return self.client.api_key

    def get_keys(self) -> List[str]:
        return self.api_keys

    def set_key(self, key):
        self.client.api_key = key

    async def assemble_context(self, text: str, image_urls: List[str] = None):
        """
        组装上下文。
        """
        if image_urls:
            user_content = {"role": "user", "content": [{"type": "text", "text": text}]}
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
                user_content["content"].append(
                    {"type": "image_url", "image_url": {"url": image_data}}
                )
            return user_content
        else:
            return {"role": "user", "content": text}

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
