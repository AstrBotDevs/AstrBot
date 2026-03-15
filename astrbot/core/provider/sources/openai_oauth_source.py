import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, TokenUsage

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "openai_oauth_chat_completion",
    "OpenAI OAuth / ChatGPT Codex 提供商适配器",
)
class ProviderOpenAIOAuth(ProviderOpenAIOfficial):
    def __init__(self, provider_config, provider_settings) -> None:
        patched_config = dict(provider_config)
        access_token = (patched_config.get("oauth_access_token") or "").strip()
        if access_token:
            patched_config["key"] = [access_token]
        super().__init__(patched_config, provider_settings)
        self.provider_config = patched_config
        self.api_keys = [access_token] if access_token else self.api_keys
        self.chosen_api_key = access_token or (self.api_keys[0] if self.api_keys else "")
        self.account_id = (
            patched_config.get("oauth_account_id")
            or patched_config.get("account_id")
            or ""
        ).strip()
        self.base_url = (
            patched_config.get("api_base")
            or "https://chatgpt.com/backend-api/codex"
        ).rstrip("/")
        self.http_client = httpx.AsyncClient(
            proxy=patched_config.get("proxy") or None,
            timeout=self.timeout,
            follow_redirects=True,
        )

    async def get_models(self):
        logger.info(
            "账号态 OAuth provider source %s 不支持自动拉取模型列表，将使用手动填写的模型 ID。",
            self.provider_config.get("id", "unknown"),
        )
        return []

    async def _request_backend(self, payload: dict[str, Any]) -> dict[str, Any]:
        access_token = (self.provider_config.get("oauth_access_token") or self.chosen_api_key or "").strip()
        account_id = (self.provider_config.get("oauth_account_id") or self.account_id or "").strip()
        if not access_token:
            raise Exception("当前 OAuth Source 尚未绑定 access token")
        if not account_id:
            raise Exception("当前 OAuth Source 缺少 chatgpt_account_id，请重新绑定或导入完整 JSON 凭据")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "OpenAI-Beta": "responses=experimental",
            "originator": "codex_cli_rs",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        custom_headers = self.provider_config.get("custom_headers")
        if isinstance(custom_headers, dict):
            for key, value in custom_headers.items():
                headers[str(key)] = str(value)

        response = await self.http_client.post(
            f"{self.base_url}/responses",
            headers=headers,
            json=payload,
        )
        raw_text = await response.aread()
        text = raw_text.decode("utf-8", errors="replace")
        if response.status_code < 200 or response.status_code >= 300:
            raise Exception(self._format_backend_error(response.status_code, text))
        return self._parse_backend_response(text)

    def _format_backend_error(self, status_code: int, text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return f"Codex backend request failed: status={status_code}"
        try:
            data = json.loads(stripped)
            return f"Codex backend request failed: status={status_code}, body={data}"
        except Exception:
            return f"Codex backend request failed: status={status_code}, body={stripped}"

    def _parse_backend_response(self, text: str) -> dict[str, Any]:
        completed_response: dict[str, Any] | None = None
        error_payload: dict[str, Any] | None = None
        for line in text.splitlines():
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                event = json.loads(raw)
            except Exception:
                continue
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            if event_type in {"response.error", "response.failed"}:
                error_payload = event
            if event_type == "response.completed":
                response = event.get("response")
                if isinstance(response, dict):
                    completed_response = response
                else:
                    completed_response = event
        if completed_response:
            return completed_response
        if error_payload:
            raise Exception(f"Codex backend returned error event: {error_payload}")
        stripped = text.strip()
        if stripped.startswith("{"):
            data = json.loads(stripped)
            if isinstance(data, dict):
                if data.get("type") == "response.completed" and isinstance(data.get("response"), dict):
                    return data["response"]
                return data
        raise Exception("Codex backend response did not contain response.completed event")

    def _convert_message_content(self, raw_content: Any) -> str | list[dict[str, Any]]:
        if isinstance(raw_content, str):
            return raw_content
        if isinstance(raw_content, dict):
            raw_content = [raw_content]
        if not isinstance(raw_content, list):
            return str(raw_content) if raw_content is not None else ""

        content_parts: list[dict[str, Any]] = []
        for part in raw_content:
            if not isinstance(part, dict):
                continue
            part_type = part.get("type")
            if part_type == "text":
                content_parts.append(
                    {
                        "type": "input_text",
                        "text": str(part.get("text") or ""),
                    }
                )
            elif part_type == "image_url":
                image_url = part.get("image_url")
                if isinstance(image_url, dict):
                    image_url = image_url.get("url")
                if image_url:
                    content_parts.append(
                        {
                            "type": "input_image",
                            "image_url": str(image_url),
                        }
                    )
        if not content_parts:
            return ""
        if len(content_parts) == 1 and content_parts[0]["type"] == "input_text":
            return content_parts[0]["text"]
        return content_parts

    def _stringify_tool_output(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return str(value)

    def _extract_instructions(self, message: dict[str, Any]) -> str:
        content = self._convert_message_content(message.get("content"))
        if isinstance(content, str):
            return content.strip()
        parts: list[str] = []
        for item in content:
            if item.get("type") == "input_text" and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(part for part in parts if part).strip()

    def _convert_messages_to_backend_input(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str, list[dict[str, Any]]]:
        instructions_parts: list[str] = []
        response_items: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "user")
            if role in {"system", "developer"}:
                instruction = self._extract_instructions(message)
                if instruction:
                    instructions_parts.append(instruction)
                continue

            content = message.get("content")
            if role == "tool":
                call_id = str(message.get("tool_call_id") or "").strip()
                if not call_id:
                    logger.warning("检测到缺少 tool_call_id 的工具回传，已忽略。")
                    continue
                response_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": self._stringify_tool_output(content),
                    }
                )
                continue

            tool_calls = message.get("tool_calls") or []
            normalized_role = role if role in {"user", "assistant"} else "user"
            if content not in (None, "", []):
                response_items.append(
                    {
                        "type": "message",
                        "role": normalized_role,
                        "content": self._convert_message_content(content),
                    }
                )

            if role == "assistant" and isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if isinstance(tool_call, str):
                        tool_call = json.loads(tool_call)
                    if not isinstance(tool_call, dict):
                        continue
                    function = tool_call.get("function") or {}
                    name = str(function.get("name") or "").strip()
                    arguments = function.get("arguments") or "{}"
                    call_id = str(tool_call.get("id") or "").strip()
                    if not name or not call_id:
                        continue
                    if not isinstance(arguments, str):
                        arguments = json.dumps(arguments, ensure_ascii=False, default=str)
                    response_items.append(
                        {
                            "type": "function_call",
                            "call_id": call_id,
                            "name": name,
                            "arguments": arguments,
                        }
                    )
        return "\n\n".join(part for part in instructions_parts if part).strip(), response_items

    def _extract_response_usage(self, usage: Any) -> TokenUsage | None:
        if usage is None:
            return None
        if isinstance(usage, dict):
            input_tokens = int(usage.get("input_tokens", 0) or 0)
            output_tokens = int(usage.get("output_tokens", 0) or 0)
            details = usage.get("input_tokens_details") or {}
            cached_tokens = int(details.get("cached_tokens", 0) or 0)
        else:
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            details = getattr(usage, "input_tokens_details", None)
            cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)
        return TokenUsage(
            input_other=max(0, input_tokens - cached_tokens),
            input_cached=cached_tokens,
            output=output_tokens,
        )

    def _convert_tools_to_backend_format(self, tool_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        backend_tools: list[dict[str, Any]] = []
        for tool in tool_list:
            if not isinstance(tool, dict):
                continue
            if tool.get("type") != "function":
                backend_tools.append(tool)
                continue
            function = tool.get("function") or {}
            if not isinstance(function, dict):
                continue
            name = str(function.get("name") or "").strip()
            if not name:
                continue
            backend_tool = {
                "type": "function",
                "name": name,
                "description": str(function.get("description") or "").strip(),
                "parameters": function.get("parameters") or {"type": "object", "properties": {}},
            }
            backend_tools.append(backend_tool)
        return backend_tools

    async def _parse_responses_completion(self, response: Any, tools) -> LLMResponse:
        llm_response = LLMResponse("assistant")
        output_text = ""
        if isinstance(response, dict):
            output_text = str(response.get("output_text") or "").strip()
        else:
            output_text = (getattr(response, "output_text", None) or "").strip()
        if output_text:
            llm_response.result_chain = MessageChain().message(output_text)

        output_items = list(response.get("output", []) if isinstance(response, dict) else getattr(response, "output", []) or [])
        reasoning_parts: list[str] = []
        tool_args: list[dict[str, Any]] = []
        tool_names: list[str] = []
        tool_ids: list[str] = []

        for item in output_items:
            item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
            if item_type == "reasoning":
                summaries = item.get("summary", []) if isinstance(item, dict) else getattr(item, "summary", []) or []
                for summary in summaries:
                    text = summary.get("text") if isinstance(summary, dict) else getattr(summary, "text", None)
                    if text:
                        reasoning_parts.append(str(text))
            elif item_type == "function_call" and tools is not None:
                arguments = item.get("arguments", "{}") if isinstance(item, dict) else getattr(item, "arguments", "{}")
                try:
                    parsed_args = json.loads(arguments) if isinstance(arguments, str) else arguments
                except Exception:
                    parsed_args = {}
                tool_args.append(parsed_args if isinstance(parsed_args, dict) else {})
                tool_names.append(str(item.get("name", "") if isinstance(item, dict) else getattr(item, "name", "") or ""))
                tool_ids.append(str(item.get("call_id", "") if isinstance(item, dict) else getattr(item, "call_id", "") or ""))
            elif item_type == "message" and not output_text:
                content_items = item.get("content", []) if isinstance(item, dict) else getattr(item, "content", []) or []
                item_text_parts: list[str] = []
                for content in content_items:
                    ctype = content.get("type") if isinstance(content, dict) else getattr(content, "type", None)
                    if ctype in {"output_text", "text"}:
                        text = content.get("text") if isinstance(content, dict) else getattr(content, "text", None)
                        if text:
                            item_text_parts.append(str(text))
                if item_text_parts:
                    llm_response.result_chain = MessageChain().message("".join(item_text_parts).strip())

        if reasoning_parts:
            llm_response.reasoning_content = "\n".join(part for part in reasoning_parts if part)

        if tool_args:
            llm_response.role = "tool"
            llm_response.tools_call_args = tool_args
            llm_response.tools_call_name = tool_names
            llm_response.tools_call_ids = tool_ids

        if llm_response.completion_text is None and not llm_response.tools_call_args:
            raise Exception(f"账号态 responses 响应无法解析：{response}。")

        llm_response.raw_completion = response
        response_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
        if response_id:
            llm_response.id = response_id
        usage = self._extract_response_usage(response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None))
        if usage is not None:
            llm_response.usage = usage
        return llm_response

    async def _query(self, payloads: dict, tools) -> LLMResponse:
        instructions, backend_input = self._convert_messages_to_backend_input(
            payloads.get("messages", []) or []
        )
        params: dict[str, Any] = {
            "model": payloads.get("model", self.get_model()),
            "input": backend_input,
            "instructions": instructions,
            "stream": True,
            "store": False,
        }
        if tools:
            tool_list = tools.get_func_desc_openai_style(
                omit_empty_parameter_field=False,
            )
            if tool_list:
                params["tools"] = self._convert_tools_to_backend_format(tool_list)
        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        if isinstance(custom_extra_body, dict):
            for key, value in custom_extra_body.items():
                if key in {"model", "input", "instructions"}:
                    continue
                params[key] = value
        params.pop("max_output_tokens", None)
        params.pop("temperature", None)
        response = await self._request_backend(params)
        return await self._parse_responses_completion(response, tools)

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
    ) -> AsyncGenerator[LLMResponse, None]:
        yield await self.text_chat(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls,
            func_tool=func_tool,
            contexts=contexts,
            system_prompt=system_prompt,
            tool_calls_result=tool_calls_result,
            model=model,
            extra_user_content_parts=extra_user_content_parts,
            **kwargs,
        )
