import asyncio
import base64
import copy
import importlib
import inspect
import json
import mimetypes
import os
import random
import re
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.api.provider import Provider
from astrbot.core.agent.message import ContentPart, ImageURLPart, Message, TextPart
from astrbot.core.agent.tool import ToolSet
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, TokenUsage, ToolCallsResult
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.network_utils import (
    create_proxy_client,
    is_connection_error,
    log_connection_failure,
)

from ..register import register_provider_adapter


@register_provider_adapter(
    "volcengine_ark_chat_completion",
    "Volcengine Ark Responses API provider adapter",
)
class ProviderVolcengineArk(Provider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_keys = super().get_keys()
        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)

        self.custom_headers = provider_config.get("custom_headers", {})
        if not isinstance(self.custom_headers, dict) or not self.custom_headers:
            self.custom_headers = None
        else:
            self.custom_headers = {
                str(key): str(value) for key, value in self.custom_headers.items()
            }

        self.api_base = str(provider_config.get("api_base", "") or "").strip()
        self.proxy = str(provider_config.get("proxy", "") or "").strip()
        self._async_http_client: httpx.AsyncClient | None = None
        self._sdk_client: Any | None = None
        self._ark_cls: Any | None = None
        self._current_key: str = self.api_keys[0] if self.api_keys else ""

        model = provider_config.get("model", "unknown")
        self.set_model(model)
        self._set_up_client(self._current_key)

    @staticmethod
    def _sdk_import_error() -> ImportError:
        return ImportError(
            "volcengine-python-sdk with Ark runtime support is required for "
            "volcengine_ark_chat_completion. Install it with "
            '`pip install "volcengine-python-sdk[ark]>=5.0.17"`.'
        )

    def _load_ark_cls(self) -> Any:
        if self._ark_cls is not None:
            return self._ark_cls
        try:
            module = importlib.import_module("volcenginesdkarkruntime")
            self._ark_cls = getattr(module, "AsyncArk")
        except (ImportError, AttributeError) as exc:
            raise self._sdk_import_error() from exc
        return self._ark_cls

    async def _close_client_resources(self) -> None:
        sdk_client = self._sdk_client
        self._sdk_client = None
        if sdk_client is not None:
            close = getattr(sdk_client, "close", None)
            if callable(close):
                try:
                    await close()
                except Exception:
                    logger.debug("Failed to close Volcengine Ark SDK client cleanly.")

        http_client = self._async_http_client
        self._async_http_client = None
        if http_client is not None:
            try:
                await http_client.aclose()
            except Exception:
                logger.debug("Failed to close Volcengine Ark proxy client cleanly.")

    def _build_sdk_client(self, api_key: str) -> Any:
        ark_cls = self._load_ark_cls()
        sig = inspect.signature(ark_cls)
        kwargs: dict[str, Any] = {}

        if "api_key" in sig.parameters:
            kwargs["api_key"] = api_key
        if "base_url" in sig.parameters and self.api_base:
            kwargs["base_url"] = self.api_base
        if "timeout" in sig.parameters:
            kwargs["timeout"] = self.timeout
        if "default_headers" in sig.parameters and self.custom_headers:
            kwargs["default_headers"] = self.custom_headers
        if "http_client" in sig.parameters:
            self._async_http_client = create_proxy_client("Volcengine Ark", self.proxy)
            if self._async_http_client is not None:
                kwargs["http_client"] = self._async_http_client

        return ark_cls(**kwargs)

    def _set_up_client(self, api_key: str) -> None:
        old_client = self._sdk_client
        old_http_client = self._async_http_client
        self._sdk_client = None
        self._async_http_client = None
        self._current_key = api_key
        self._sdk_client = self._build_sdk_client(api_key)
        if old_client is not None or old_http_client is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and loop.is_running():

                async def _cleanup() -> None:
                    if old_client is not None:
                        close = getattr(old_client, "close", None)
                        if callable(close):
                            try:
                                await close()
                            except Exception:
                                logger.debug(
                                    "Failed to close previous Volcengine Ark SDK client cleanly."
                                )
                    if old_http_client is not None:
                        try:
                            await old_http_client.aclose()
                        except Exception:
                            logger.debug(
                                "Failed to close previous Volcengine Ark proxy client cleanly."
                            )

                loop.create_task(_cleanup())

    @staticmethod
    def _obj_get(value: Any, key: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    @classmethod
    def _as_list(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @staticmethod
    def _safe_json_loads(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    @staticmethod
    def _strip_think_tags(text: str) -> tuple[str, str]:
        reasoning_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
        matches = reasoning_pattern.findall(text)
        reasoning = "\n".join(match.strip() for match in matches if match.strip())
        stripped = reasoning_pattern.sub("", text).strip()
        stripped = re.sub(r"</think>\s*$", "", stripped).strip()
        return stripped, reasoning

    @staticmethod
    def _summarize_input_items(input_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summary: list[dict[str, Any]] = []
        for item in input_items:
            role = str(item.get("role", ""))
            content_summary: list[dict[str, Any]] = []
            for content in ProviderVolcengineArk._as_list(item.get("content")):
                content_type = str(ProviderVolcengineArk._obj_get(content, "type", ""))
                if content_type == "input_text":
                    text = str(ProviderVolcengineArk._obj_get(content, "text", ""))
                    content_summary.append(
                        {"type": "input_text", "text_preview": text[:120]}
                    )
                elif content_type == "input_image":
                    image_url = str(
                        ProviderVolcengineArk._obj_get(content, "image_url", "")
                    )
                    content_summary.append(
                        {"type": "input_image", "image_url": image_url[:200]}
                    )
                else:
                    content_summary.append({"type": content_type})
            summary.append({"role": role, "content": content_summary})
        return summary

    def _extract_usage(self, usage: Any) -> TokenUsage | None:
        if usage is None:
            return None
        prompt_tokens = self._obj_get(
            usage,
            "input_tokens",
            self._obj_get(usage, "prompt_tokens", 0),
        )
        completion_tokens = self._obj_get(
            usage,
            "output_tokens",
            self._obj_get(usage, "completion_tokens", 0),
        )
        prompt_details = self._obj_get(
            usage,
            "input_tokens_details",
            self._obj_get(usage, "prompt_tokens_details"),
        )
        cached_tokens = self._obj_get(prompt_details, "cached_tokens", 0) or 0
        prompt_tokens = prompt_tokens or 0
        completion_tokens = completion_tokens or 0
        return TokenUsage(
            input_other=max(prompt_tokens - cached_tokens, 0),
            input_cached=cached_tokens,
            output=completion_tokens,
        )

    def _build_tool_schema(self, tools: ToolSet | None) -> list[dict[str, Any]]:
        if tools is None or tools.empty():
            return []
        payload: list[dict[str, Any]] = []
        for tool in tools.func_list:
            tool_payload: dict[str, Any] = {
                "type": "function",
                "name": tool.name,
            }
            if tool.description:
                tool_payload["description"] = tool.description
            if tool.parameters:
                tool_payload["parameters"] = tool.parameters
            payload.append(tool_payload)
        return payload

    async def _encode_image_to_data_url(self, image_url: str) -> str:
        if image_url.startswith("data:"):
            return image_url
        if image_url.startswith("base64://"):
            return image_url.replace("base64://", "data:image/jpeg;base64,", 1)
        if image_url.startswith("http://") or image_url.startswith("https://"):
            downloaded_path = await download_image_by_url(image_url)
            return await self._encode_image_to_data_url(downloaded_path)
        local_path = (
            image_url.replace("file:///", "", 1)
            if image_url.startswith("file:///")
            else image_url
        )
        image_path = Path(local_path)
        image_bytes = await asyncio.to_thread(image_path.read_bytes)
        image_bs64 = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:image/jpeg;base64,{image_bs64}"

    async def _write_data_url_to_temp_file(self, data_url: str) -> str:
        match = re.match(
            r"^data:(?P<mime>[\w.+-]+/[\w.+-]+);base64,(?P<data>.+)$",
            data_url,
            re.DOTALL,
        )
        if not match:
            raise ValueError("Unsupported data URL format for Volcengine Ark image.")

        mime_type = match.group("mime")
        image_data = base64.b64decode(match.group("data"))
        suffix = mimetypes.guess_extension(mime_type) or ".jpg"
        temp_dir = Path(get_astrbot_temp_path()) / "volcengine_ark"
        temp_dir.mkdir(parents=True, exist_ok=True)
        file_path = temp_dir / f"ark_img_{uuid.uuid4().hex}{suffix}"
        await asyncio.to_thread(file_path.write_bytes, image_data)
        return self._to_ark_file_reference(file_path)

    @staticmethod
    def _to_ark_file_reference(file_path: str | Path) -> str:
        path = Path(file_path).expanduser().resolve()
        return f"file://{path.as_posix()}"

    @classmethod
    def _normalize_file_uri(cls, image_url: str) -> str:
        local_path = unquote(image_url.removeprefix("file://"))
        local_path = local_path.replace("\\", os.sep)
        if re.match(r"^/[A-Za-z]:[/\\]", local_path):
            local_path = local_path[1:]
        return cls._to_ark_file_reference(local_path)

    async def _convert_image_to_file_uri(self, image_url: str) -> str:
        if image_url.startswith("file://"):
            return self._normalize_file_uri(image_url)
        if image_url.startswith("data:"):
            return await self._write_data_url_to_temp_file(image_url)
        if image_url.startswith("base64://"):
            return await self._write_data_url_to_temp_file(
                image_url.replace("base64://", "data:image/jpeg;base64,", 1)
            )
        if image_url.startswith("http://") or image_url.startswith("https://"):
            downloaded_path = await download_image_by_url(image_url)
            return await self._convert_image_to_file_uri(downloaded_path)

        local_path = (
            image_url.replace("file:///", "", 1)
            if image_url.startswith("file:///")
            else image_url
        )
        return self._to_ark_file_reference(local_path)

    @staticmethod
    def _is_invalid_scheme_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return "invalid scheme" in text and "'param': 'url'" in text

    @staticmethod
    def _input_contains_file_images(input_items: list[dict[str, Any]]) -> bool:
        for item in input_items:
            for content in ProviderVolcengineArk._as_list(item.get("content")):
                if ProviderVolcengineArk._obj_get(content, "type") != "input_image":
                    continue
                image_url = ProviderVolcengineArk._obj_get(content, "image_url", "")
                if isinstance(image_url, str) and image_url.startswith("file://"):
                    return True
        return False

    async def _convert_payload_file_images_to_data_urls(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        converted_payload = copy.deepcopy(payload)
        for item in converted_payload.get("input", []):
            for content in self._as_list(item.get("content")):
                if self._obj_get(content, "type") != "input_image":
                    continue
                image_url = self._obj_get(content, "image_url", "")
                if not isinstance(image_url, str) or not image_url.startswith("file://"):
                    continue
                local_path = unquote(image_url.removeprefix("file://"))
                local_path = local_path.replace("\\", os.sep)
                if re.match(r"^/[A-Za-z]:[/\\]", local_path):
                    local_path = local_path[1:]
                content["image_url"] = await self._encode_image_to_data_url(local_path)
        return converted_payload

    async def _resolve_image_part(self, image_url: str) -> dict[str, Any]:
        resolved_uri = await self._convert_image_to_file_uri(image_url)
        logger.info(
            "Volcengine Ark resolved image input: source=%s resolved=%s",
            image_url[:200],
            resolved_uri[:200],
        )
        return {
            "type": "input_image",
            "image_url": resolved_uri,
        }

    async def _normalize_content_items(self, content: Any) -> list[dict[str, Any]]:
        if content is None:
            return []
        if isinstance(content, str):
            return [{"type": "input_text", "text": content}]

        items: list[dict[str, Any]] = []
        for part in self._as_list(content):
            part_type = self._obj_get(part, "type")
            if part_type in {"text", "input_text"}:
                text = self._obj_get(part, "text", "")
                items.append({"type": "input_text", "text": str(text)})
            elif part_type == "think":
                think = self._obj_get(part, "think", "")
                if think:
                    items.append({"type": "input_text", "text": str(think)})
            elif part_type == "input_image":
                image_url = self._obj_get(part, "image_url", "")
                if isinstance(image_url, str) and image_url.strip():
                    items.append(
                        {
                            "type": "input_image",
                            "image_url": await self._convert_image_to_file_uri(
                                image_url.strip()
                            ),
                        }
                    )
            elif part_type == "image_url":
                image_payload = self._obj_get(part, "image_url")
                image_url = self._obj_get(image_payload, "url", image_payload)
                if isinstance(image_url, str) and image_url.strip():
                    items.append(await self._resolve_image_part(image_url.strip()))
            else:
                logger.debug(
                    f"Skipping unsupported Volcengine Ark input content part: {part_type}"
                )
        return items

    async def assemble_context(
        self,
        text: str,
        image_urls: list[str] | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
    ) -> dict[str, Any]:
        content_items: list[dict[str, Any]] = []
        if text:
            content_items.append({"type": "input_text", "text": text})
        elif image_urls:
            content_items.append({"type": "input_text", "text": "[Image]"})
        elif extra_user_content_parts:
            content_items.append({"type": "input_text", "text": " "})

        for part in extra_user_content_parts or []:
            if isinstance(part, TextPart):
                content_items.append({"type": "input_text", "text": part.text})
            elif isinstance(part, ImageURLPart):
                content_items.append(await self._resolve_image_part(part.image_url.url))
            else:
                raise ValueError(f"Unsupported extra content part type: {type(part)}")

        for image_url in image_urls or []:
            content_items.append(await self._resolve_image_part(image_url))

        return {"role": "user", "content": content_items}

    async def _convert_message_to_input(self, message: dict[str, Any]) -> list[dict]:
        role = str(message.get("role", "user"))
        items: list[dict[str, Any]] = []

        content_items = await self._normalize_content_items(message.get("content"))
        if content_items and role in {"system", "user", "assistant"}:
            items.append({"role": role, "content": content_items})

        for tool_call in self._as_list(message.get("tool_calls")):
            call_type = self._obj_get(tool_call, "type", "function")
            if call_type != "function":
                continue
            function_payload = self._obj_get(tool_call, "function", {})
            call_name = self._obj_get(tool_call, "name") or self._obj_get(
                function_payload, "name"
            )
            call_arguments = self._obj_get(tool_call, "arguments") or self._obj_get(
                function_payload, "arguments"
            )
            call_id = self._obj_get(tool_call, "call_id") or self._obj_get(
                tool_call, "id"
            )
            if not call_name or not call_id:
                continue
            items.append(
                {
                    "type": "function_call",
                    "call_id": str(call_id),
                    "name": str(call_name),
                    "arguments": str(call_arguments or "{}"),
                }
            )

        if role == "tool":
            tool_output = ""
            if isinstance(message.get("content"), str):
                tool_output = message["content"]
            else:
                text_parts = []
                for content_item in await self._normalize_content_items(
                    message.get("content")
                ):
                    if content_item.get("type") == "input_text":
                        text_parts.append(str(content_item.get("text", "")))
                tool_output = "".join(text_parts)
            call_id = message.get("tool_call_id")
            if call_id:
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(call_id),
                        "output": tool_output,
                    }
                )

        return items

    async def _prepare_payload(
        self,
        prompt: str | None,
        image_urls: list[str] | None = None,
        contexts: list[dict] | list[Message] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None = None,
        model: str | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
        tools: ToolSet | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        context_query = self._ensure_message_to_dicts(contexts)
        if prompt is not None:
            context_query.append(
                await self.assemble_context(
                    prompt, image_urls, extra_user_content_parts
                )
            )
        elif image_urls or extra_user_content_parts:
            context_query.append(
                await self.assemble_context("", image_urls, extra_user_content_parts)
            )

        if system_prompt:
            context_query.insert(0, {"role": "system", "content": system_prompt})

        if tool_calls_result:
            if isinstance(tool_calls_result, ToolCallsResult):
                context_query.extend(tool_calls_result.to_openai_messages())
            else:
                for tool_result in tool_calls_result:
                    context_query.extend(tool_result.to_openai_messages())

        input_items: list[dict[str, Any]] = []
        for message in context_query:
            input_items.extend(await self._convert_message_to_input(message))

        payload: dict[str, Any] = {
            "model": model or self.get_model(),
            "input": input_items,
        }

        input_image_count = sum(
            1
            for item in input_items
            for content in self._as_list(item.get("content"))
            if self._obj_get(content, "type") == "input_image"
        )
        logger.info(
            "Volcengine Ark prepared payload: model=%s input_items=%d input_images=%d",
            payload["model"],
            len(input_items),
            input_image_count,
        )
        if input_image_count > 0:
            logger.info(
                "Volcengine Ark payload summary: %s",
                self._summarize_input_items(input_items),
            )

        tool_payload = self._build_tool_schema(tools)
        if tool_payload:
            payload["tools"] = tool_payload

        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        if isinstance(custom_extra_body, dict):
            payload.update(custom_extra_body)

        payload.update(kwargs)
        return payload

    def _extract_text_from_message_item(self, item: Any) -> str:
        text_parts: list[str] = []
        for content_part in self._as_list(self._obj_get(item, "content", [])):
            part_type = self._obj_get(content_part, "type")
            if part_type in {"output_text", "text", "input_text"}:
                text_value = self._obj_get(content_part, "text", "")
                if text_value is not None:
                    text_parts.append(str(text_value))
        return "".join(text_parts)

    def _extract_reasoning_item(self, item: Any) -> str:
        summary = self._obj_get(item, "summary")
        if summary is not None:
            texts = []
            for summary_part in self._as_list(summary):
                text_value = self._obj_get(summary_part, "text", "")
                if text_value:
                    texts.append(str(text_value))
            if texts:
                return "\n".join(texts)
        text_value = self._obj_get(item, "text", "")
        return str(text_value) if text_value else ""

    def _parse_response(
        self, response: Any, tools: ToolSet | None = None
    ) -> LLMResponse:
        llm_response = LLMResponse("assistant")
        output_items = self._as_list(self._obj_get(response, "output"))
        text_parts: list[str] = []
        reasoning_parts: list[str] = []

        for item in output_items:
            item_type = self._obj_get(item, "type")
            if item_type == "message":
                text = self._extract_text_from_message_item(item)
                if text:
                    text_parts.append(text)
            elif item_type == "reasoning":
                reasoning = self._extract_reasoning_item(item)
                if reasoning:
                    reasoning_parts.append(reasoning)
            elif item_type == "function_call":
                call_name = self._obj_get(item, "name")
                call_id = self._obj_get(item, "call_id", self._obj_get(item, "id"))
                call_arguments = self._obj_get(item, "arguments", "{}")
                if call_name and call_id:
                    llm_response.role = "tool"
                    llm_response.tools_call_name.append(str(call_name))
                    llm_response.tools_call_ids.append(str(call_id))
                    args = self._safe_json_loads(call_arguments)
                    if not isinstance(args, dict):
                        args = {"raw_arguments": call_arguments}
                    llm_response.tools_call_args.append(args)
            elif item_type in {"output_text", "text"}:
                text_value = self._obj_get(item, "text", "")
                if text_value:
                    text_parts.append(str(text_value))

        top_level_text = self._obj_get(response, "output_text")
        if top_level_text and not text_parts:
            text_parts.append(str(top_level_text))

        llm_response.reasoning_content = "\n".join(
            part.strip() for part in reasoning_parts if part.strip()
        )

        completion_text = "".join(text_parts).strip()
        if completion_text:
            completion_text, think_reasoning = self._strip_think_tags(completion_text)
            if think_reasoning:
                llm_response.reasoning_content = think_reasoning
            if completion_text:
                llm_response.result_chain = MessageChain().message(completion_text)

        if llm_response.completion_text is None and not llm_response.tools_call_args:
            raise Exception(f"Volcengine Ark response could not be parsed: {response}")

        llm_response.raw_completion = response
        llm_response.id = self._obj_get(response, "id")
        llm_response.usage = self._extract_usage(self._obj_get(response, "usage"))
        return llm_response

    async def _stream_response(
        self, payload: dict[str, Any], tools: ToolSet | None = None
    ) -> AsyncGenerator[LLMResponse, None]:
        if self._sdk_client is None:
            self._set_up_client(self._current_key)
        stream = await self._sdk_client.responses.create(**payload, stream=True)

        accumulated_text = ""
        accumulated_reasoning = ""
        final_response: Any = None

        async for event in stream:
            event_type = str(self._obj_get(event, "type", ""))
            if event_type.endswith("output_text.delta"):
                delta = self._obj_get(event, "delta", "")
                if delta:
                    accumulated_text += str(delta)
                    yield LLMResponse(
                        "assistant",
                        result_chain=MessageChain(chain=[Comp.Plain(str(delta))]),
                        is_chunk=True,
                        id=self._obj_get(event, "response_id"),
                    )
            elif "reasoning" in event_type and event_type.endswith(".delta"):
                delta = self._obj_get(event, "delta", "")
                if delta:
                    accumulated_reasoning += str(delta)
                    yield LLMResponse(
                        "assistant",
                        reasoning_content=str(delta),
                        is_chunk=True,
                        id=self._obj_get(event, "response_id"),
                    )
            elif event_type == "response.completed":
                final_response = self._obj_get(
                    event,
                    "response",
                    self._obj_get(event, "data"),
                )

        if final_response is not None:
            yield self._parse_response(final_response, tools)
            return

        final_llm_response = LLMResponse("assistant")
        if accumulated_reasoning:
            final_llm_response.reasoning_content = accumulated_reasoning
        if accumulated_text:
            final_llm_response.result_chain = MessageChain().message(accumulated_text)
        yield final_llm_response

    async def get_models(self) -> list[str]:
        if self._sdk_client is None:
            self._set_up_client(self._current_key)
        models_client = getattr(self._sdk_client, "models", None)
        if models_client is None or not hasattr(models_client, "list"):
            return [self.get_model()] if self.get_model() else []

        def _list_models() -> list[str]:
            models = models_client.list()
            model_data = self._as_list(self._obj_get(models, "data", models))
            items = []
            for item in model_data:
                model_id = self._obj_get(item, "id")
                if model_id:
                    items.append(str(model_id))
            return sorted(items)

        try:
            models = await asyncio.to_thread(_list_models)
            return models or ([self.get_model()] if self.get_model() else [])
        except Exception:
            return [self.get_model()] if self.get_model() else []

    def get_current_key(self) -> str:
        return self._current_key

    def get_keys(self) -> list[str]:
        return self.api_keys

    def set_key(self, key: str) -> None:
        self._set_up_client(key)

    async def text_chat(
        self,
        prompt: str | None = None,
        session_id: str | None = None,
        image_urls: list[str] | None = None,
        func_tool: ToolSet | None = None,
        contexts: list[dict] | list[Message] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None = None,
        model: str | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
        **kwargs,
    ) -> LLMResponse:
        if image_urls:
            logger.info(
                "Volcengine Ark text_chat received image_urls: count=%d values=%s",
                len(image_urls),
                [url[:200] for url in image_urls[:3]],
            )
        payload = await self._prepare_payload(
            prompt,
            image_urls=image_urls,
            contexts=contexts,
            system_prompt=system_prompt,
            tool_calls_result=tool_calls_result,
            model=model,
            extra_user_content_parts=extra_user_content_parts,
            tools=func_tool,
            **kwargs,
        )

        last_exception: Exception | None = None
        available_api_keys = self.api_keys.copy() or [self._current_key]
        chosen_key = random.choice(available_api_keys)

        for _ in range(10):
            try:
                self.set_key(chosen_key)
                response = await self._sdk_client.responses.create(**payload, stream=False)
                return self._parse_response(response, func_tool)
            except Exception as exc:
                last_exception = exc
                if self._is_invalid_scheme_error(exc) and self._input_contains_file_images(
                    payload.get("input", [])
                ):
                    logger.warning(
                        "Volcengine Ark rejected file:// image input, retrying with data URLs."
                    )
                    payload = await self._convert_payload_file_images_to_data_urls(payload)
                    continue
                if "429" in str(exc) and len(available_api_keys) > 1:
                    logger.warning(
                        "Volcengine Ark rate limit hit, rotating API key. "
                        f"Current key prefix: {chosen_key[:12]}"
                    )
                    available_api_keys.remove(chosen_key)
                    chosen_key = random.choice(available_api_keys)
                    await asyncio.sleep(1)
                    continue
                if is_connection_error(exc):
                    log_connection_failure("Volcengine Ark", exc, self.proxy)
                raise

        if last_exception is None:
            raise Exception("Unknown Volcengine Ark error")
        raise last_exception

    async def text_chat_stream(
        self,
        prompt: str | None = None,
        session_id: str | None = None,
        image_urls: list[str] | None = None,
        func_tool: ToolSet | None = None,
        contexts: list[dict] | list[Message] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None = None,
        model: str | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        if image_urls:
            logger.info(
                "Volcengine Ark text_chat_stream received image_urls: count=%d values=%s",
                len(image_urls),
                [url[:200] for url in image_urls[:3]],
            )
        payload = await self._prepare_payload(
            prompt,
            image_urls=image_urls,
            contexts=contexts,
            system_prompt=system_prompt,
            tool_calls_result=tool_calls_result,
            model=model,
            extra_user_content_parts=extra_user_content_parts,
            tools=func_tool,
            **kwargs,
        )

        available_api_keys = self.api_keys.copy() or [self._current_key]
        chosen_key = random.choice(available_api_keys)
        last_exception: Exception | None = None

        for _ in range(10):
            try:
                self.set_key(chosen_key)
                async for response in self._stream_response(payload, func_tool):
                    yield response
                return
            except Exception as exc:
                last_exception = exc
                if self._is_invalid_scheme_error(exc) and self._input_contains_file_images(
                    payload.get("input", [])
                ):
                    logger.warning(
                        "Volcengine Ark rejected file:// image input during streaming, retrying with data URLs."
                    )
                    payload = await self._convert_payload_file_images_to_data_urls(payload)
                    continue
                if "429" in str(exc) and len(available_api_keys) > 1:
                    logger.warning(
                        "Volcengine Ark rate limit hit during streaming, rotating API key. "
                        f"Current key prefix: {chosen_key[:12]}"
                    )
                    available_api_keys.remove(chosen_key)
                    chosen_key = random.choice(available_api_keys)
                    await asyncio.sleep(1)
                    continue
                if is_connection_error(exc):
                    log_connection_failure("Volcengine Ark", exc, self.proxy)
                raise

        if last_exception is None:
            raise Exception("Unknown Volcengine Ark streaming error")
        raise last_exception

    async def terminate(self) -> None:
        await self._close_client_resources()
