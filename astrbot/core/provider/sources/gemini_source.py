import asyncio
import base64
import json
import random
from typing import Dict, List

from google import genai
from google.genai import errors, types

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.api.provider import Personality, Provider
from astrbot.core.db import BaseDatabase
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.func_tool_manager import FuncCall
from astrbot.core.utils.io import download_image_by_url

from ..register import register_provider_adapter


@register_provider_adapter(
    "googlegenai_chat_completion", "Google Gemini Chat Completion 提供商适配器"
)
class ProviderGoogleGenAI(Provider):
    CATEGORY_MAPPING = {
        "harassment": types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        "hate_speech": types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        "sexually_explicit": types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        "dangerous_content": types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    }

    THRESHOLD_MAPPING = {
        "BLOCK_NONE": types.HarmBlockThreshold.BLOCK_NONE,
        "BLOCK_ONLY_HIGH": types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        "BLOCK_MEDIUM_AND_ABOVE": types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        "BLOCK_LOW_AND_ABOVE": types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    }

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
        self.api_keys: List = provider_config.get("key", [])
        self.chosen_api_key: str = self.api_keys[0] if len(self.api_keys) > 0 else None
        self.timeout: int = provider_config.get("timeout", 180)
        self.api_base: str = provider_config.get("api_base", None)
        if self.api_base.endswith("/"):
            self.api_base = self.api_base[:-1]
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)
        self.client = genai.Client(
            api_key=self.chosen_api_key,
            http_options=types.HttpOptions(
                base_url=self.api_base,
                timeout=self.timeout * 1000,  # 毫秒
            ),
        ).aio
        self.set_model(provider_config["model_config"]["model"])

        user_safety_config = self.provider_config.get("gm_safety_settings", {})
        self.safety_settings = [
            types.SafetySetting(
                category=harm_category, threshold=self.THRESHOLD_MAPPING[threshold_str]
            )
            for config_key, harm_category in self.CATEGORY_MAPPING.items()
            if (threshold_str := user_safety_config.get(config_key))
            and threshold_str in self.THRESHOLD_MAPPING
        ]

    async def get_models(self):
        try:
            models = await self.client.models.list()
            return [
                m.name.replace("models/", "")
                for m in models
                if "generateContent" in m.supported_actions
            ]
        except errors.APIError as e:
            raise Exception(f"获取模型列表失败: {e}")

    def _prepare_conversation(
        self,
        payloads: Dict,
    ) -> List[types.Content]:
        """准备 Gemini SDK 的 Content 列表"""
        gemini_contents = []
        for message in payloads["messages"]:
            role = message["role"]
            content = message.get("content")

            if role == "user":
                if isinstance(content, str):
                    if content:
                        gemini_contents.append(
                            types.UserContent(
                                parts=[types.Part.from_text(text=content)]
                            )
                        )
                    else:
                        logger.warning("文本内容为空，已添加空格占位")
                        gemini_contents.append(
                            types.UserContent(parts=[types.Part.from_text(text=" ")])
                        )

                elif isinstance(content, list):
                    parts = []
                    for item in content:
                        if item.get("type") == "text":
                            text_content = item.get("text")
                            if text_content:
                                parts.append(types.Part.from_text(text=text_content))
                            else:
                                logger.warning("文本内容为空，已添加空格占位")
                                parts.append(types.Part.from_text(text=" "))
                        elif item.get("type") == "image_url":
                            image_url_dict = item["image_url"]
                            url = image_url_dict["url"]
                            mime_part, base64_data = url.split(",", 1)
                            mime_type = mime_part.split(":")[1].split(";")[0]
                            image_bytes = base64.b64decode(base64_data)
                            parts.append(
                                types.Part.from_bytes(
                                    data=image_bytes, mime_type=mime_type
                                )
                            )
                    gemini_contents.append(types.UserContent(parts=parts))

            elif role == "assistant":
                if content:
                    gemini_contents.append(
                        types.ModelContent(
                            parts=[types.Part.from_text(text=message["content"])]
                        )
                    )
                elif "tool_calls" in message:
                    parts = [
                        {
                            "name": tool_call["function"]["name"],
                            "args": json.loads(tool_call["function"]["arguments"]),
                        }
                        for tool_call in message["tool_calls"]
                    ]
                    gemini_contents.append(
                        types.ModelContent(parts=[types.Part.from_function_call(parts)])
                    )
                else:
                    logger.warning("assistant 角色的消息内容为空，已添加空格占位")
                    gemini_contents.append(
                        types.ModelContent(parts=[types.Part.from_text(text=" ")])
                    )

            elif role == "tool":
                gemini_contents.append(
                    types.UserContent(
                        parts=[
                            types.Part.from_function_response(
                                {
                                    "name": message["tool_call_id"],
                                    "response": {
                                        "name": message["tool_call_id"],
                                        "content": message["content"],
                                    },
                                }
                            )
                        ]
                    )
                )

        # logger.debug(f"gemini_contents: {gemini_contents}")

        return gemini_contents

    async def _query(
        self, payloads: dict, tools: FuncCall, temperature: float = 0.7
    ) -> LLMResponse:
        """非流式请求 Gemini API"""
        if tools:
            t = tools.get_func_desc_google_genai_style()
            tool = (
                types.Tool(function_declarations=t["function_declarations"])
                if t
                else None
            )

        system_instruction = ""
        for message in payloads["messages"]:
            if message["role"] == "system":
                system_instruction = message["content"]
                break

        conversation = self._prepare_conversation(payloads)

        modalites = ["Text"]
        if self.provider_config.get("gm_resp_image_modal", False):
            modalites.append("Image")

        loop = True
        while loop:
            loop = False
            result = await self.client.models.generate_content(
                model=self.get_model(),
                contents=conversation,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    tools=[tool] if tool else None,
                    safety_settings=self.safety_settings
                    if self.safety_settings
                    else None,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                ),
            )

            result_str = str(result)
            finish_reason = result.candidates[0].finish_reason
            if "Developer instruction is not enabled" in result_str:
                logger.warning(f"{self.get_model()} 不支持 system prompt，已自动去除。")
                system_instruction = ""
                loop = True
                continue
            elif "Function calling is not enabled" in result_str:
                logger.warning(f"{self.get_model()} 不支持函数调用，已自动去除。")
                tool = None
                loop = True
                continue
            elif "Multi-modal output is not supported" in result_str:
                logger.warning(f"{self.get_model()} 不支持多模态输出，降级为文本模态。")
                modalites = ["Text"]
                loop = True
                continue
            elif finish_reason == types.FinishReason.RECITATION:
                logger.warning("发生了recitation，正在尝试加温重试...")
                temperature += 0.2
                logger.info(f"当前温度: {temperature}")
                if temperature < 2:
                    loop = True
                else:
                    raise Exception("温度已到达(或超过)2")
                continue

        llm_response = LLMResponse("assistant")

        if finish_reason == types.FinishReason.SAFETY:
            raise Exception("模型生成内容未通过用户定义的内容安全检查")

        if finish_reason in {
            types.FinishReason.PROHIBITED_CONTENT,
            types.FinishReason.SPII,
            types.FinishReason.BLOCKLIST,
            types.FinishReason.IMAGE_SAFETY,
        }:
            raise Exception("模型生成内容违反Gemini平台政策")

        if not result.candidates[0].content.parts:
            logger.debug(result.candidates)
            raise Exception("API 返回的内容为空。")

        llm_response.result_chain = self._process_content_parts(
            result.candidates[0].content.parts, llm_response
        )

        return llm_response

    def _process_content_parts(
        self, parts: types.Part, llm_response: LLMResponse
    ) -> MessageChain:
        """处理内容部分并构建消息链"""
        chain = []
        part: types.Part
        for part in parts:
            if part.text:
                chain.append(Comp.Plain(part.text))
            elif part.function_call:
                llm_response.role = "tool"
                llm_response.tools_call_name.append(part.function_call.name)
                llm_response.tools_call_args.append(part.function_call.args)
                llm_response.tools_call_ids.append(part.function_call.id)
            elif part.inline_data and part.inline_data.mime_type.startswith("image/"):
                chain.append(Comp.Image.fromBytes(part.inline_data.data))
        return MessageChain(chain=chain)

    async def text_chat(
        self,
        prompt: str,
        session_id: str = None,
        image_urls: List[str] = None,
        func_tool: FuncCall = None,
        contexts=[],
        system_prompt=None,
        tool_calls_result=None,
        **kwargs,
    ) -> LLMResponse:
        new_record = await self.assemble_context(prompt, image_urls)
        context_query = [*contexts, new_record]
        if system_prompt:
            context_query.insert(0, {"role": "system", "content": system_prompt})

        for part in context_query:
            if "_no_save" in part:
                del part["_no_save"]

        # tool calls result
        if tool_calls_result:
            context_query.extend(tool_calls_result.to_openai_messages())

        model_config = self.provider_config.get("model_config", {})
        model_config["model"] = self.get_model()

        payloads = {"messages": context_query, **model_config}
        llm_response = None

        retry = 10
        keys = self.api_keys.copy()
        chosen_key = random.choice(keys)
        temp = kwargs.get("temperature", 0.7)  # 暂定默认温度为0.7

        for _ in range(retry):
            try:
                self.chosen_api_key = chosen_key
                llm_response = await self._query(payloads, func_tool, temp)
                break
            except Exception as e:
                if "429" in str(e) or "API key not valid" in str(e):
                    keys.remove(chosen_key)
                    if len(keys) > 0:
                        chosen_key = random.choice(keys)
                        logger.info(
                            f"检测到 Key 异常({str(e)})，正在尝试更换 API Key 重试... 当前 Key: {chosen_key[:12]}..."
                        )
                        await asyncio.sleep(1)
                        continue
                    else:
                        logger.error(
                            f"检测到 Key 异常({str(e)})，且已没有可用的 Key。 当前 Key: {chosen_key[:12]}..."
                        )
                        raise Exception("达到了 Gemini 速率限制, 请稍后再试...")
                else:
                    logger.error(
                        f"发生了错误(gemini_source)。Provider 配置如下: {self.provider_config}"
                    )
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

    def get_current_key(self) -> str:
        return self.chosen_api_key

    def get_keys(self) -> List[str]:
        return self.api_keys

    def set_key(self, key):
        self.chosen_api_key = key

    async def assemble_context(self, text: str, image_urls: List[str] = None):
        """
        组装上下文。
        """
        if image_urls:
            user_content = {
                "role": "user",
                "content": [{"type": "text", "text": text if text else "[图片]"}],
            }
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

    async def terminate(self):
        logger.info("Google GenAI 适配器已终止。")
