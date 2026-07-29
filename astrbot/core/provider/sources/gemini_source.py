import asyncio
import base64
import json
import logging
import random
from collections.abc import AsyncGenerator
from typing import Literal, cast

import httpx
from google import genai
from google.genai import types
from google.genai.errors import APIError

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.api.provider import Provider
from astrbot.core.agent.message import AudioURLPart, ContentPart, ImageURLPart, TextPart
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot.core.provider.func_tool_manager import ToolSet
from astrbot.core.utils.media_utils import (
    describe_media_ref,
    resolve_media_ref_to_base64_data,
)
from astrbot.core.utils.network_utils import is_connection_error, log_connection_failure

from ..register import register_provider_adapter
from .request_retry import retry_provider_request


class SuppressNonTextPartsWarning(logging.Filter):
    """过滤 Gemini SDK 中的非文本部分警告"""

    def filter(self, record):
        return "there are non-text parts in the response" not in record.getMessage()


logging.getLogger("google_genai.types").addFilter(SuppressNonTextPartsWarning())


@register_provider_adapter(
    "googlegenai_chat_completion",
    "Google Gemini Chat Completion 提供商适配器",
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
        provider_config,
        provider_settings,
    ) -> None:
        super().__init__(
            provider_config,
            provider_settings,
        )
        self.api_keys: list = super().get_keys()
        self.chosen_api_key: str = self.api_keys[0] if len(self.api_keys) > 0 else ""
        self.timeout: int = int(provider_config.get("timeout", 180))

        self.api_base: str | None = provider_config.get("api_base", None)
        if self.api_base and self.api_base.endswith("/"):
            self.api_base = self.api_base[:-1]

        self._http_client: httpx.AsyncClient | None = None
        self._stale_http_clients: list[httpx.AsyncClient] = []
        self._init_client()
        self.set_model(provider_config.get("model", "unknown"))
        self._init_safety_settings()

    def _init_client(self) -> None:
        """初始化Gemini客户端"""
        proxy = self.provider_config.get("proxy", "")
        http_options = types.HttpOptions(
            base_url=self.api_base,
            timeout=self.timeout * 1000,  # 毫秒
        )

        # 强制使用 httpx 作为异步 HTTP 后端，避免 aiohttp 响应类型兼容问题 (#7564)
        # httpx.AsyncClient 的 timeout 单位为秒（与 HttpOptions 的毫秒不同）
        async_client_kwargs: dict = {
            "base_url": self.api_base,
            "timeout": self.timeout,
        }
        if proxy:
            async_client_kwargs["proxy"] = proxy
            async_client_kwargs["trust_env"] = False
        else:
            async_client_kwargs["trust_env"] = True

        # Track the previous client so it can be closed in terminate() instead
        # of leaking when _init_client is called again (e.g. via set_key).
        # Only the most recent stale client is kept to avoid unbounded growth.
        if self._http_client is not None:
            self._stale_http_clients = [self._http_client]

        self._http_client = httpx.AsyncClient(**async_client_kwargs)
        http_options.httpx_async_client = self._http_client

        self.client = genai.Client(
            api_key=self.chosen_api_key,
            http_options=http_options,
        ).aio

    def _init_safety_settings(self) -> None:
        """初始化安全设置"""
        user_safety_config = self.provider_config.get("gm_safety_settings", {})
        self.safety_settings = [
            types.SafetySetting(
                category=harm_category,
                threshold=self.THRESHOLD_MAPPING[threshold_str],
            )
            for config_key, harm_category in self.CATEGORY_MAPPING.items()
            if (threshold_str := user_safety_config.get(config_key))
            and threshold_str in self.THRESHOLD_MAPPING
        ]

    async def _handle_api_error(self, e: APIError, keys: list[str]) -> bool:
        """处理API错误，返回是否需要重试"""
        if e.message is None:
            e.message = ""

        if e.code == 429 or "API key not valid" in e.message:
            keys.remove(self.chosen_api_key)
            if len(keys) > 0:
                self.set_key(random.choice(keys))
                logger.warning(
                    "Retrying with a different API key due to detected key issue: %s. Current key: %s...",
                    e.message,
                    self.chosen_api_key[:12],
                )
                await asyncio.sleep(1)
                return True
            logger.error(
                "No valid API keys remaining. Current key: %s...",
                self.chosen_api_key[:12],
            )
            raise Exception("Gemini API rate limit reached or API key issue detected.")

        # 连接错误处理
        if is_connection_error(e):
            proxy = self.provider_config.get("proxy", "")
            log_connection_failure("Gemini", e, proxy)

        raise e

    async def _prepare_query_config(
        self,
        payloads: dict,
        tools: ToolSet | None = None,
        tool_choice: Literal["auto", "required"] = "auto",
        system_instruction: str | None = None,
        modalities: list[str] | None = None,
        temperature: float = 0.7,
    ) -> types.GenerateContentConfig:
        """准备查询配置"""
        if not modalities:
            modalities = ["TEXT"]

        # 流式输出不支持图片模态
        if (
            self.provider_settings.get("streaming_response", False)
            and "IMAGE" in modalities
        ):
            logger.warning(
                "Streaming responses do not support IMAGE modality, falling back to TEXT modality."
            )
            modalities = ["TEXT"]

        tool_list: list[types.Tool] | None = []
        model_name = cast(str, payloads.get("model", self.get_model()))
        native_coderunner = self.provider_config.get("gm_native_coderunner", False)
        native_search = self.provider_config.get("gm_native_search", False)
        url_context = self.provider_config.get("gm_url_context", False)

        if "gemini-2.0-lite" in model_name:
            if native_coderunner or native_search or url_context:
                logger.warning(
                    "gemini-2.0-lite does not support native code execution, search, or URL context tools. These settings will be ignored.",
                )
        else:
            if native_coderunner:
                tool_list.append(types.Tool(code_execution=types.ToolCodeExecution()))
            if native_search:
                tool_list.append(types.Tool(google_search=types.GoogleSearch()))
            if url_context:
                tool_list.append(types.Tool(url_context=types.UrlContext()))

        if tools:
            func_desc = tools.get_func_desc_google_genai_style()
            tool_list.append(
                types.Tool(function_declarations=func_desc["function_declarations"]),
            )

        if not tool_list:
            tool_list = None

        tool_config = None
        has_func_decl = tool_list and any(t.function_declarations for t in tool_list)
        if has_func_decl:
            tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=(
                        types.FunctionCallingConfigMode.ANY
                        if tool_choice == "required"
                        else types.FunctionCallingConfigMode.AUTO
                    )
                )
            )

        # oper thinking config
        thinking_config = None
        if model_name in [
            "gemini-2.5-pro",
            "gemini-2.5-pro-preview",
            "gemini-2.5-flash",
            "gemini-2.5-flash-preview",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash-lite-preview",
            "gemini-robotics-er-1.5-preview",
            "gemini-live-2.5-flash-preview-native-audio-09-2025",
        ]:
            # The thinkingBudget parameter, introduced with the Gemini 2.5 series
            thinking_budget = self.provider_config.get("gm_thinking_config", {}).get(
                "budget", 0
            )
            if thinking_budget is not None:
                thinking_config = types.ThinkingConfig(
                    thinking_budget=thinking_budget,
                )
        elif any(model_name.startswith(p) for p in ("gemini-3-", "gemini-3.")):
            # The thinkingLevel parameter, recommended for Gemini 3 models and onwards.
            # Use prefix match so new variants (3.1, 3-flash-lite-preview, etc.) are
            # covered without needing to keep an exhaustive list up to date.
            # Gemini 2.5 series models don't support thinkingLevel; use thinkingBudget instead.
            thinking_level = self.provider_config.get("gm_thinking_config", {}).get(
                "level", "HIGH"
            )
            if thinking_level and isinstance(thinking_level, str):
                thinking_level = thinking_level.upper()
                if thinking_level not in ["MINIMAL", "LOW", "MEDIUM", "HIGH"]:
                    logger.warning(
                        f"Invalid thinking level: {thinking_level}, using HIGH"
                    )
                    thinking_level = "HIGH"
                level = types.ThinkingLevel(thinking_level)
                thinking_config = types.ThinkingConfig()
                if not hasattr(types.ThinkingConfig, "thinking_level"):
                    setattr(types.ThinkingConfig, "thinking_level", level)
                else:
                    thinking_config.thinking_level = level

        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=payloads.get("max_tokens")
            or payloads.get("maxOutputTokens"),
            top_p=payloads.get("top_p") or payloads.get("topP"),
            top_k=payloads.get("top_k") or payloads.get("topK"),
            frequency_penalty=payloads.get("frequency_penalty")
            or payloads.get("frequencyPenalty"),
            presence_penalty=payloads.get("presence_penalty")
            or payloads.get("presencePenalty"),
            stop_sequences=payloads.get("stop") or payloads.get("stopSequences"),
            response_logprobs=payloads.get("response_logprobs")
            or payloads.get("responseLogprobs"),
            logprobs=payloads.get("logprobs"),
            seed=payloads.get("seed"),
            response_modalities=modalities,
            tools=cast(types.ToolListUnion | None, tool_list),
            tool_config=tool_config,
            safety_settings=self.safety_settings if self.safety_settings else None,
            thinking_config=thinking_config,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True,
            ),
        )

    def _prepare_conversation(self, payloads: dict) -> list[types.Content]:
        """准备 Gemini SDK 的 Content 列表"""

        def create_text_part(text: str) -> types.Part:
            content_a = text if text else " "
            if not text:
                logger.warning("Text content is empty, added a space as placeholder.")
            return types.Part.from_text(text=content_a)

        def process_image_url(image_url_dict: dict) -> types.Part:
            url = image_url_dict["url"]
            mime_type = url.split(":")[1].split(";")[0]
            image_bytes = base64.b64decode(url.split(",", 1)[1])
            return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        def process_audio_url(audio_url_dict: dict) -> types.Part:
            url = audio_url_dict["url"]
            mime_type = url.split(":")[1].split(";")[0]
            audio_bytes = base64.b64decode(url.split(",", 1)[1])
            return types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

        def append_or_extend(
            contents: list[types.Content],
            part: list[types.Part],
            content_cls: type[types.Content],
        ) -> None:
            if contents and isinstance(contents[-1], content_cls):
                assert contents[-1].parts is not None
                contents[-1].parts.extend(part)
            else:
                contents.append(content_cls(parts=part))

        gemini_contents: list[types.Content] = []
        for message in payloads["messages"]:
            role, content = message["role"], message.get("content")

            if role == "user":
                if isinstance(content, list):
                    parts = [
                        (
                            types.Part.from_text(text=item["text"] or " ")
                            if item["type"] == "text"
                            else (
                                process_image_url(item["image_url"])
                                if item["type"] == "image_url"
                                else process_audio_url(item["audio_url"])
                            )
                        )
                        for item in content
                    ]
                else:
                    parts = [create_text_part(content)]
                append_or_extend(gemini_contents, parts, types.UserContent)

            elif role == "assistant":
                parts = []
                if isinstance(content, str):
                    parts.append(types.Part.from_text(text=content))
                elif isinstance(content, list):
                    thinking_signature = None
                    text = ""
                    for part in content:
                        # for most cases, assistant content only contains two parts: think and text
                        if part.get("type") == "think":
                            thinking_signature = part.get("encrypted") or None
                        else:
                            text += str(part.get("text"))

                    if thinking_signature and isinstance(thinking_signature, str):
                        try:
                            thinking_signature = base64.b64decode(thinking_signature)
                        except Exception as e:
                            logger.warning(
                                f"Failed to decode google gemini thinking signature: {e}",
                                exc_info=True,
                            )
                            thinking_signature = None

                    if (
                        not text
                        and thinking_signature
                        and "tool_calls" in message
                        and any(
                            isinstance(tool, dict)
                            and isinstance(tool.get("extra_content"), dict)
                            and isinstance(tool["extra_content"].get("google"), dict)
                            and tool["extra_content"]["google"].get("thought_signature")
                            for tool in message["tool_calls"]
                        )
                    ):
                        # If the main content is empty but tool calls have thought signatures,
                        # skip adding an empty text part to deduplicate the thinking signature in the main content and tool calls.
                        pass
                    else:
                        parts.append(
                            types.Part(
                                text=text,
                                thought_signature=thinking_signature,
                            )
                        )

                if "tool_calls" in message:
                    for tool in message["tool_calls"]:
                        part = types.Part.from_function_call(
                            name=tool["function"]["name"],
                            args=json.loads(tool["function"]["arguments"]),
                        )
                        # we should set thought_signature back to part if exists
                        # for more info about thought_signature, see:
                        # https://ai.google.dev/gemini-api/docs/thought-signatures
                        if "extra_content" in tool and tool["extra_content"]:
                            ts_bs64 = (
                                tool["extra_content"]
                                .get("google", {})
                                .get("thought_signature")
                            )
                            if ts_bs64:
                                part.thought_signature = base64.b64decode(ts_bs64)
                        parts.append(part)

                if not parts:
                    parts = [types.Part.from_text(text=" ")]

                append_or_extend(gemini_contents, parts, types.ModelContent)

            elif role == "tool":
                func_name = message.get("name", message["tool_call_id"])
                part = types.Part.from_function_response(
                    name=func_name,
                    response={
                        "name": func_name,
                        "content": message["content"],
                    },
                )

                parts = [part]
                append_or_extend(gemini_contents, parts, types.UserContent)

        if gemini_contents and isinstance(gemini_contents[0], types.ModelContent):
            gemini_contents.pop()

        return gemini_contents

    def _extract_reasoning_content(self, candidate: types.Candidate) -> str:
        """Extract reasoning content from candidate parts"""
        if not candidate.content or not candidate.content.parts:
            return ""

        thought_buf: list[str] = [
            (p.text or "") for p in candidate.content.parts if p.thought
        ]
        return "".join(thought_buf).strip()

    def _extract_usage(
        self, usage_metadata: types.GenerateContentResponseUsageMetadata
    ) -> TokenUsage:
        """Extract usage from candidate"""
        return TokenUsage(
            input_other=usage_metadata.prompt_token_count or 0,
            input_cached=usage_metadata.cached_content_token_count or 0,
            output=usage_metadata.candidates_token_count or 0,
        )

    @staticmethod
    def _ensure_usable_response(
        llm_response: LLMResponse,
        *,
        response_id: str | None = None,
        finish_reason: str | None = None,
    ) -> None:
        has_text_output = bool((llm_response.completion_text or "").strip())
        has_reasoning_output = bool((llm_response.reasoning_content or "").strip())
        has_tool_output = bool(llm_response.tools_call_args)
        if has_text_output or has_reasoning_output or has_tool_output:
            return
        raise EmptyModelOutputError(
            "Gemini completion has no usable output. "
            f"response_id={response_id}, finish_reason={finish_reason}"
        )

    def _process_content_parts(
        self,
        candidate: types.Candidate,
        llm_response: LLMResponse,
        *,
        validate_output: bool = True,
    ) -> MessageChain:
        """处理内容部分并构建消息链"""
        if not candidate.content:
            logger.warning(f"Gemini candidate.content is empty: {candidate}")
            if validate_output:
                raise EmptyModelOutputError(
                    "Gemini candidate content is empty. "
                    f"finish_reason={candidate.finish_reason}"
                )
            llm_response.result_chain = MessageChain(chain=[])
            return llm_response.result_chain

        finish_reason = candidate.finish_reason
        result_parts: list[types.Part] | None = candidate.content.parts

        if finish_reason == types.FinishReason.SAFETY:
            raise Exception("The model output failed Gemini platform safety checks.")

        if finish_reason in {
            types.FinishReason.PROHIBITED_CONTENT,
            types.FinishReason.SPII,
            types.FinishReason.BLOCKLIST,
        }:
            raise Exception("The model output violates Gemini platform policy.")

        # 防止旧版本SDK不存在IMAGE_SAFETY
        if hasattr(types.FinishReason, "IMAGE_SAFETY"):
            if finish_reason == types.FinishReason.IMAGE_SAFETY:
                raise Exception("The model output violates Gemini platform policy.")

        if not result_parts:
            logger.warning(f"Gemini candidate.content.parts is empty: {candidate}")
            if validate_output:
                raise EmptyModelOutputError(
                    "Gemini candidate content parts are empty. "
                    f"finish_reason={candidate.finish_reason}"
                )
            llm_response.result_chain = MessageChain(chain=[])
            return llm_response.result_chain

        # 提取 reasoning content
        reasoning = self._extract_reasoning_content(candidate)
        if reasoning:
            llm_response.reasoning_content = reasoning

        chain = []
        part: types.Part

        # 暂时这样Fallback
        if all(
            part.inline_data
            and part.inline_data.mime_type
            and part.inline_data.mime_type.startswith("image/")
            for part in result_parts
        ):
            chain.append(Comp.Plain("这是图片"))
        for part in result_parts:
            # Skip thinking parts — their text is already captured via
            # _extract_reasoning_content above.  Including them here would
            # leak the model's internal reasoning into the user-facing message,
            # which also causes duplicate/triple replies on some platforms.
            if part.text and not part.thought:
                chain.append(Comp.Plain(part.text))

            if (
                part.function_call
                and part.function_call.name is not None
                and part.function_call.args is not None
            ):
                llm_response.role = "tool"
                llm_response.tools_call_name.append(part.function_call.name)
                llm_response.tools_call_args.append(part.function_call.args)
                # function_call.id might be None, use name as fallback
                tool_call_id = part.function_call.id or part.function_call.name
                llm_response.tools_call_ids.append(tool_call_id)
                # extra_content
                if part.thought_signature:
                    ts_bs64 = base64.b64encode(part.thought_signature).decode("utf-8")
                    llm_response.tools_call_extra_content[tool_call_id] = {
                        "google": {"thought_signature": ts_bs64}
                    }

            if (
                part.inline_data
                and part.inline_data.mime_type
                and part.inline_data.mime_type.startswith("image/")
                and part.inline_data.data
            ):
                chain.append(Comp.Image.fromBytes(part.inline_data.data))

            if ts := part.thought_signature:
                # only keep the last thinking signature
                llm_response.reasoning_signature = base64.b64encode(ts).decode("utf-8")
        chain_result = MessageChain(chain=chain)
        llm_response.result_chain = chain_result
        if validate_output:
            self._ensure_usable_response(
                llm_response,
                response_id=None,
                finish_reason=str(finish_reason) if finish_reason is not None else None,
            )
        return chain_result

    async def _query(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> LLMResponse:
        """非流式请求 Gemini API"""
        system_instruction = next(
            (msg["content"] for msg in payloads["messages"] if msg["role"] == "system"),
            None,
        )

        model = payloads.get("model", self.get_model())

        modalities = ["TEXT"]
        if self.provider_config.get("gm_resp_image_modal", False):
            modalities.append("IMAGE")

        conversation = self._prepare_conversation(payloads)
        temperature = payloads.get("temperature", 0.7)

        result: types.GenerateContentResponse | None = None
        while True:
            try:
                config = await self._prepare_query_config(
                    payloads,
                    tools,
                    payloads.get("tool_choice", "auto"),
                    system_instruction,
                    modalities,
                    temperature,
                )
                result = await retry_provider_request(
                    "Gemini",
                    lambda: self.client.models.generate_content(
                        model=model,
                        contents=cast(types.ContentListUnion, conversation),
                        config=config,
                    ),
                    max_attempts=request_max_retries,
                )
                logger.debug(f"genai result: {result}")

                if not result.candidates:
                    logger.error(
                        f"Gemini request failed: candidates is empty: {result}"
                    )
                    raise Exception("Gemini request failed: candidates is empty.")

                if result.candidates[0].finish_reason == types.FinishReason.RECITATION:
                    if temperature > 2:
                        raise Exception(
                            "Temperature exceeded the maximum value of 2, but Gemini recitation still occurred."
                        )
                    temperature += 0.2
                    logger.warning(
                        f"Gemini recitation detected; increasing temperature to {temperature:.1f} and retrying...",
                    )
                    continue

                break

            except APIError as e:
                if e.message is None:
                    e.message = ""
                if "Developer instruction is not enabled" in e.message:
                    logger.warning(
                        f"{model} does not support system prompts; removing it automatically. This may affect persona settings.",
                    )
                    system_instruction = None
                elif "Function calling is not enabled" in e.message:
                    logger.warning(
                        f"{model} does not support function calling; removing tools automatically."
                    )
                    tools = None
                elif (
                    "Multi-modal output is not supported" in e.message
                    or "Model does not support the requested response modalities"
                    in e.message
                    or "only supports text output" in e.message
                ):
                    logger.warning(
                        f"{model} does not support multimodal output; falling back to TEXT modality.",
                    )
                    modalities = ["TEXT"]
                else:
                    raise
                continue

        llm_response = LLMResponse("assistant")
        llm_response.raw_completion = result
        llm_response.result_chain = self._process_content_parts(
            result.candidates[0],
            llm_response,
        )
        llm_response.id = result.response_id
        if result.usage_metadata:
            llm_response.usage = self._extract_usage(result.usage_metadata)
        return llm_response

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> AsyncGenerator[LLMResponse, None]:
        """流式请求 Gemini API"""
        system_instruction = next(
            (msg["content"] for msg in payloads["messages"] if msg["role"] == "system"),
            None,
        )
        model = payloads.get("model", self.get_model())
        conversation = self._prepare_conversation(payloads)

        result = None
        while True:
            try:
                config = await self._prepare_query_config(
                    payloads,
                    tools,
                    payloads.get("tool_choice", "auto"),
                    system_instruction,
                )
                result = await retry_provider_request(
                    "Gemini",
                    lambda: self.client.models.generate_content_stream(
                        model=model,
                        contents=cast(types.ContentListUnion, conversation),
                        config=config,
                    ),
                    max_attempts=request_max_retries,
                )
                break
            except APIError as e:
                if e.message is None:
                    e.message = ""
                if "Developer instruction is not enabled" in e.message:
                    logger.warning(
                        f"{model} does not support system prompts; removing it automatically. This may affect persona settings.",
                    )
                    system_instruction = None
                elif "Function calling is not enabled" in e.message:
                    logger.warning(
                        f"{model} does not support function calling; removing tools automatically."
                    )
                    tools = None
                else:
                    raise
                continue

        # Accumulate the complete response text for the final response
        accumulated_text = ""
        accumulated_reasoning = ""
        final_response = None

        async for chunk in result:
            llm_response = LLMResponse("assistant", is_chunk=True)

            if not chunk.candidates:
                logger.warning(f"Gemini stream chunk has empty candidates: {chunk}")
                continue
            if not chunk.candidates[0].content:
                logger.warning(f"Gemini stream chunk has empty content: {chunk}")
                continue

            if chunk.candidates[0].content.parts and any(
                part.function_call for part in chunk.candidates[0].content.parts
            ):
                llm_response = LLMResponse("assistant", is_chunk=False)
                llm_response.raw_completion = chunk
                llm_response.result_chain = self._process_content_parts(
                    chunk.candidates[0],
                    llm_response,
                    validate_output=False,
                )
                llm_response.id = chunk.response_id
                if chunk.usage_metadata:
                    llm_response.usage = self._extract_usage(chunk.usage_metadata)
                yield llm_response
                return

            _f = False

            # 提取 reasoning content
            reasoning = self._extract_reasoning_content(chunk.candidates[0])
            if reasoning:
                _f = True
                accumulated_reasoning += reasoning
                llm_response.reasoning_content = reasoning
            if chunk.text:
                _f = True
                accumulated_text += chunk.text
                llm_response.result_chain = MessageChain(chain=[Comp.Plain(chunk.text)])
            if _f:
                yield llm_response

            if chunk.candidates[0].finish_reason:
                # Process the final chunk for potential tool calls or other content
                if chunk.candidates[0].content.parts:
                    final_response = LLMResponse("assistant", is_chunk=False)
                    final_response.raw_completion = chunk
                    final_response.result_chain = self._process_content_parts(
                        chunk.candidates[0],
                        final_response,
                        validate_output=False,
                    )
                    final_response.id = chunk.response_id
                    if chunk.usage_metadata:
                        final_response.usage = self._extract_usage(chunk.usage_metadata)
                break

        # Yield final complete response with accumulated text
        if not final_response:
            final_response = LLMResponse("assistant", is_chunk=False)

        # Set the complete accumulated reasoning in the final response
        if accumulated_reasoning:
            final_response.reasoning_content = accumulated_reasoning

        # Set the complete accumulated text in the final response
        if accumulated_text:
            final_response.result_chain = MessageChain(
                chain=[Comp.Plain(accumulated_text)],
            )

        self._ensure_usable_response(
            final_response,
            response_id=getattr(final_response, "id", None),
            finish_reason=None,
        )

        yield final_response

    async def text_chat(
        self,
        prompt=None,
        session_id=None,
        image_urls=None,
        audio_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        extra_user_content_parts=None,
        tool_choice: Literal["auto", "required"] = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        if contexts is None:
            contexts = []
        new_record = None
        if prompt is not None:
            new_record = await self.assemble_context(
                prompt or "",
                image_urls,
                audio_urls,
                extra_user_content_parts,
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

        model = model or self.get_model()

        payloads = {"messages": context_query, "model": model}
        if func_tool and not func_tool.empty():
            payloads["tool_choice"] = tool_choice

        retry = 10
        keys = self.api_keys.copy()

        for _ in range(retry):
            try:
                return await self._query(
                    payloads,
                    func_tool,
                    request_max_retries=request_max_retries,
                )
            except APIError as e:
                if await self._handle_api_error(e, keys):
                    continue
                break

        raise Exception("Gemini request failed.")

    async def text_chat_stream(
        self,
        prompt=None,
        session_id=None,
        image_urls=None,
        audio_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        extra_user_content_parts=None,
        tool_choice: Literal["auto", "required"] = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        if contexts is None:
            contexts = []
        new_record = None
        if prompt is not None:
            new_record = await self.assemble_context(
                prompt or "",
                image_urls,
                audio_urls,
                extra_user_content_parts,
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

        model = model or self.get_model()

        payloads = {"messages": context_query, "model": model}
        if func_tool and not func_tool.empty():
            payloads["tool_choice"] = tool_choice

        retry = 10
        keys = self.api_keys.copy()

        for _ in range(retry):
            try:
                async for response in self._query_stream(
                    payloads,
                    func_tool,
                    request_max_retries=request_max_retries,
                ):
                    yield response
                break
            except APIError as e:
                if await self._handle_api_error(e, keys):
                    continue
                break

    async def get_models(self):
        try:
            models = await retry_provider_request(
                "Gemini",
                lambda: self.client.models.list(),
            )
            return [
                m.name.replace("models/", "")
                for m in models
                if m.supported_actions
                and "generateContent" in m.supported_actions
                and m.name
            ]
        except APIError as e:
            raise Exception(f"Failed to fetch Gemini model list: {e.message}")

    def get_current_key(self) -> str:
        return self.chosen_api_key

    def get_keys(self) -> list[str]:
        return self.api_keys

    def set_key(self, key) -> None:
        self.chosen_api_key = key
        self._init_client()

    async def assemble_context(
        self,
        text: str,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
    ):
        """组装上下文。"""

        async def resolve_image_part(image_url: str) -> dict | None:
            image_data = await resolve_media_ref_to_base64_data(
                image_url,
                media_type="image",
            )
            if not image_data:
                logger.warning("Image preprocessing returned no data; ignoring it.")
                return None
            return {
                "type": "image_url",
                "image_url": {"url": image_data.to_data_url()},
            }

        async def resolve_audio_part(audio_path: str) -> dict | None:
            try:
                audio_data = await resolve_media_ref_to_base64_data(
                    audio_path,
                    media_type="audio",
                    strict=True,
                )
            except Exception as exc:
                logger.warning(
                    "Audio preprocessing failed; ignoring it. Error: %s", exc
                )
                return None

            if not audio_data:
                logger.warning("Audio preprocessing returned no data; ignoring it.")
                return None
            return {
                "type": "audio_url",
                "audio_url": {"url": audio_data.to_data_url()},
            }

        # 构建内容块列表
        content_blocks = []

        # 1. 用户原始发言（OpenAI 建议：用户发言在前）
        if text:
            content_blocks.append({"type": "text", "text": text})
        elif image_urls:
            # 如果没有文本但有图片，添加占位文本
            content_blocks.append({"type": "text", "text": "[Image]"})
        elif audio_urls:
            content_blocks.append({"type": "text", "text": "[Audio]"})
        elif extra_user_content_parts:
            # 如果只有额外内容块，也需要添加占位文本
            content_blocks.append({"type": "text", "text": " "})

        # 2. 额外的内容块（系统提醒、指令等）
        if extra_user_content_parts:
            for part in extra_user_content_parts:
                if isinstance(part, TextPart):
                    content_blocks.append({"type": "text", "text": part.text})
                elif isinstance(part, ImageURLPart):
                    image_part = await resolve_image_part(part.image_url.url)
                    if image_part:
                        content_blocks.append(image_part)
                elif isinstance(part, AudioURLPart):
                    audio_part = await resolve_audio_part(part.audio_url.url)
                    if audio_part:
                        content_blocks.append(audio_part)
                else:
                    raise ValueError(
                        f"Unsupported extra content part type: {type(part)}"
                    )

        # 3. 图片内容
        if image_urls:
            for image_url in image_urls:
                image_part = await resolve_image_part(image_url)
                if image_part:
                    content_blocks.append(image_part)

        if audio_urls:
            for audio_path in audio_urls:
                audio_part = await resolve_audio_part(audio_path)
                if audio_part:
                    content_blocks.append(audio_part)

        # 如果只有主文本且没有额外内容块和图片，返回简单格式以保持向后兼容
        if (
            text
            and not extra_user_content_parts
            and not image_urls
            and not audio_urls
            and len(content_blocks) == 1
            and content_blocks[0]["type"] == "text"
        ):
            return {"role": "user", "content": content_blocks[0]["text"]}

        # 否则返回多模态格式
        return {"role": "user", "content": content_blocks}

    async def encode_image_bs64(self, image_url: str) -> str:
        """将图片转换为 base64"""
        image_data = await resolve_media_ref_to_base64_data(
            image_url,
            media_type="image",
            strict=True,
        )
        if image_data is None:
            raise RuntimeError(
                f"Failed to encode image data: {describe_media_ref(image_url)}"
            )
        return image_data.to_data_url()

    async def _close_httpx_client(self, client: httpx.AsyncClient | None) -> None:
        """Safely close an httpx.AsyncClient, swallowing errors for idempotency."""
        if client is None:
            return
        try:
            await client.aclose()
        except Exception as e:
            # Idempotent: ignore errors from already-closed or broken clients,
            # but log at debug to aid diagnosing unexpected shutdown issues.
            logger.debug(f"[Gemini] Ignored error while closing httpx client: {e}")

    async def terminate(self) -> None:
        # Close the active Gemini client (external httpx client is managed
        # separately so genai.Client.aclose skips it).
        if self.client is not None:
            try:
                await self.client.aclose()
            except Exception:
                pass
            self.client = None

        # Close all tracked httpx clients (stale + current).
        for client in self._stale_http_clients:
            await self._close_httpx_client(client)
        self._stale_http_clients.clear()
        await self._close_httpx_client(self._http_client)
        self._http_client = None
