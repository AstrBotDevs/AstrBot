import base64
import aiohttp
import random
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.db import BaseDatabase
from astrbot.api.provider import Provider, Personality
from astrbot import logger
from astrbot.core.provider.func_tool_manager import FuncCall
from typing import List
from ..register import register_provider_adapter
from astrbot.core.provider.entites import LLMResponse


class SimpleGoogleGenAIClient:
    def __init__(self, api_key: str, api_base: str, timeout: int = 120) -> None:
        self.api_key = api_key
        if api_base.endswith("/"):
            self.api_base = api_base[:-1]
        else:
            self.api_base = api_base
        self.client = aiohttp.ClientSession(trust_env=True)
        self.timeout = timeout

    async def models_list(self) -> List[str]:
        request_url = f"{self.api_base}/v1beta/models?key={self.api_key}"
        async with self.client.get(request_url, timeout=self.timeout) as resp:
            response = await resp.json()

            models = []
            for model in response["models"]:
                if "generateContent" in model["supportedGenerationMethods"]:
                    models.append(model["name"].replace("models/", ""))
            return models

    async def generate_content(
        self,
        contents: List[dict],
        model: str = "gemini-1.5-flash",
        system_instruction: str = "",
        tools: dict = None,
    ):
        payload = {}
        if system_instruction:
            payload["system_instruction"] = {"parts": {"text": system_instruction}}
        if tools:
            payload["tools"] = [tools]
        payload["contents"] = contents
        logger.debug(f"payload: {payload}")
        request_url = (
            f"{self.api_base}/v1beta/models/{model}:generateContent?key={self.api_key}"
        )
        async with self.client.post(
            request_url, json=payload, timeout=self.timeout
        ) as resp:
            if "application/json" in resp.headers.get("Content-Type"):
                try:
                    response = await resp.json()
                except Exception as e:
                    text = await resp.text()
                    logger.error(f"Gemini 返回了非 json 数据: {text}")
                    raise e
                return response
            else:
                text = await resp.text()
                logger.error(f"Gemini 返回了非 json 数据: {text}")
                raise Exception("Gemini 返回了非 json 数据： ")


@register_provider_adapter(
    "googlegenai_chat_completion", "Google Gemini Chat Completion 提供商适配器"
)
class ProviderGoogleGenAI(Provider):
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
        self.timeout = provider_config.get("timeout", 180)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)
        self.client = SimpleGoogleGenAIClient(
            api_key=self.chosen_api_key,
            api_base=provider_config.get("api_base", None),
            timeout=self.timeout,
        )
        self.set_model(provider_config["model_config"]["model"])

    async def get_models(self):
        return await self.client.models_list()

    async def _query(self, payloads: dict, tools: FuncCall) -> LLMResponse:
        tool = None
        if tools:
            tool = tools.get_func_desc_google_genai_style()
            if not tool:
                tool = None

        system_instruction = ""
        for message in payloads["messages"]:
            if message["role"] == "system":
                system_instruction = message["content"]
                break

        google_genai_conversation = []
        for message in payloads["messages"]:
            if message["role"] == "user":
                if isinstance(message["content"], str):
                    if not message["content"]:
                        message["content"] = "<empty_content>"

                    google_genai_conversation.append(
                        {"role": "user", "parts": [{"text": message["content"]}]}
                    )
                elif isinstance(message["content"], list):
                    # images
                    parts = []
                    for part in message["content"]:
                        if part["type"] == "text":
                            if not part["text"]:
                                part["text"] = "<empty_content>"
                            parts.append({"text": part["text"]})
                        elif part["type"] == "image_url":
                            parts.append(
                                {
                                    "inline_data": {
                                        "mime_type": "image/jpeg",
                                        "data": part["image_url"]["url"].replace(
                                            "data:image/jpeg;base64,", ""
                                        ),  # base64
                                    }
                                }
                            )
                    google_genai_conversation.append({"role": "user", "parts": parts})

            elif message["role"] == "assistant":
                if not message["content"]:
                    message["content"] = "<empty_content>"
                google_genai_conversation.append(
                    {"role": "model", "parts": [{"text": message["content"]}]}
                )

        logger.debug(f"google_genai_conversation: {google_genai_conversation}")

        result = await self.client.generate_content(
            contents=google_genai_conversation,
            model=self.get_model(),
            system_instruction=system_instruction,
            tools=tool,
        )
        logger.debug(f"result: {result}")

        if "candidates" not in result:
            raise Exception("Gemini 返回异常结果: " + str(result))

        candidates = result["candidates"][0]["content"]["parts"]
        llm_response = LLMResponse("assistant")
        for candidate in candidates:
            if "text" in candidate:
                llm_response.completion_text += candidate["text"]
            elif "functionCall" in candidate:
                llm_response.role = "tool"
                llm_response.tools_call_args.append(candidate["functionCall"]["args"])
                llm_response.tools_call_name.append(candidate["functionCall"]["name"])

        llm_response.completion_text = llm_response.completion_text.strip()
        return llm_response

    async def text_chat(
        self,
        prompt: str,
        session_id: str = None,
        image_urls: List[str] = None,
        func_tool: FuncCall = None,
        contexts=[],
        system_prompt=None,
        **kwargs,
    ) -> LLMResponse:
        new_record = await self.assemble_context(prompt, image_urls)
        context_query = []
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

        retry = 10
        keys = self.api_keys.copy()
        chosen_key = random.choice(keys)

        for i in range(retry):
            try:
                self.client.api_key = chosen_key
                llm_response = await self._query(payloads, func_tool)
                break
            except Exception as e:
                if "maximum context length" in str(e):
                    retry_cnt = 20
                    while retry_cnt > 0:
                        logger.warning(
                            f"请求失败：{e}。上下文长度超过限制。尝试弹出最早的记录然后重试。当前记录条数: {len(context_query)}"
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
                            "err", "err: 请尝试  /reset 重置会话"
                        )
                elif "Function calling is not enabled" in str(e):
                    logger.info(
                        f"{self.get_model()} 不支持函数工具调用，已自动去除，不影响使用。"
                    )
                    if "tools" in payloads:
                        del payloads["tools"]
                    llm_response = await self._query(payloads, None)
                    break
                elif "429" in str(e) or "API key not valid" in str(e):
                    keys.remove(chosen_key)
                    if len(keys) > 0:
                        chosen_key = random.choice(keys)
                        logger.info(
                            f"检测到 Key 异常({str(e)})，正在尝试更换 API Key 重试... 当前 Key: {chosen_key[:12]}..."
                        )
                        continue
                    else:
                        logger.error(
                            f"检测到 Key 异常({str(e)})，且已没有可用的 Key。 当前 Key: {chosen_key[:12]}..."
                        )
                        raise Exception("API 资源已耗尽，且没有可用的 Key 重试...")
                else:
                    logger.error(
                        f"发生了错误(gemini_source)。Provider 配置如下: {self.provider_config}"
                    )
                    raise e

        return llm_response

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

    async def terminate(self):
        await self.client.client.close()
        logger.info("Google GenAI 适配器已终止。")
