import asyncio
import base64
import inspect
import json
import mimetypes
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import aclosing, asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from astrbot import logger
from astrbot.core import db_helper
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot.core.provider.oauth.openai_oauth import (
    decode_jwt_claims,
    refresh_access_token,
)
from astrbot.core.provider.oauth.openai_oauth_audio import OpenAIOAuthAudioMixin
from astrbot.core.provider.oauth.openai_oauth_shared_state import (
    OpenAIOAuthSharedState,
)
from astrbot.core.provider.oauth.openai_oauth_sse import iter_json_sse_events
from astrbot.core.provider.provider import provider_stats_managed_by_agent
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial
from .request_retry import retry_provider_request

OAUTH_PLACEHOLDER_KEY = "__openai_oauth__"
CODEX_CLIENT_VERSION = "0.153.4"
oauth_provider_stat_kind: ContextVar[str] = ContextVar(
    "oauth_provider_stat_kind",
    default="text",
)


@dataclass
class OpenAIOAuthImageResult:
    path: str
    mime_type: str = "image/png"
    revised_prompt: str = ""
    raw: dict[str, Any] | None = None


@register_provider_adapter(
    "openai_oauth_chat_completion",
    "OpenAI OAuth / ChatGPT Codex 提供商适配器",
)
class ProviderOpenAIOAuth(OpenAIOAuthAudioMixin, ProviderOpenAIOfficial):
    capabilities = {
        "chat": True,
        "stream": True,
        "vision_input": True,
        "function_call": True,
        "reasoning": True,
        "image_generate": True,
        "image_edit": True,
    }
    model_capabilities = {
        "gpt-6-astra": {
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": (
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
            ),
        },
        "gpt-5.6-sol": {
            "default_reasoning_effort": "low",
            "supported_reasoning_efforts": (
                "none",
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
            ),
        },
        "gpt-5.6-terra": {
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": (
                "none",
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
            ),
        },
        "gpt-5.6-luna": {
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": (
                "none",
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
            ),
        },
        "gpt-5.5": {
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": (
                "none",
                "low",
                "medium",
                "high",
                "xhigh",
            ),
        },
        "gpt-5.4": {
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": (
                "none",
                "low",
                "medium",
                "high",
                "xhigh",
            ),
        },
        "gpt-5.4-mini": {
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": (
                "none",
                "low",
                "medium",
                "high",
                "xhigh",
            ),
        },
        "gpt-5.3-codex-spark": {
            "default_reasoning_effort": "high",
            "supported_reasoning_efforts": (
                "none",
                "low",
                "medium",
                "high",
                "xhigh",
            ),
        },
    }

    def __init__(self, provider_config, provider_settings) -> None:
        patched_config = dict(provider_config)
        patched_config.pop("oauth_shared_state", None)
        patched_config["key"] = [OAUTH_PLACEHOLDER_KEY]
        super().__init__(patched_config, provider_settings)
        self.provider_config = dict(provider_config)
        shared_state = self.provider_config.pop("oauth_shared_state", None)
        if isinstance(shared_state, OpenAIOAuthSharedState):
            self._oauth_shared_state = shared_state
        else:
            source_id = str(
                self.provider_config.get("provider_source_id")
                or self.provider_config.get("id")
                or "openai_oauth"
            )
            self._oauth_shared_state = OpenAIOAuthSharedState(
                source_id,
                self.provider_config,
            )
        self.provider_config["key"] = [OAUTH_PLACEHOLDER_KEY]
        self.api_keys = [OAUTH_PLACEHOLDER_KEY]
        self.chosen_api_key = ""
        self.account_id = (
            self.provider_config.get("oauth_account_id")
            or self.provider_config.get("account_id")
            or ""
        ).strip()
        self.base_url = (
            self.provider_config.get("api_base")
            or "https://chatgpt.com/backend-api/codex"
        ).rstrip("/")
        self._oauth_refresh_lock = self._oauth_shared_state.refresh_lock
        self._oauth_refresh_skew_seconds = int(
            self.provider_config.get("oauth_refresh_skew_seconds") or 300
        )
        self._oauth_persist_callback = self.provider_config.get(
            "oauth_persist_callback"
        )
        self._sync_oauth_credentials_from_shared()

    async def get_models(self):
        return list(self.model_capabilities)

    async def _prepare_chat_payload(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Preserve per-request reasoning controls for Codex Responses.

        Args:
            *args: Positional arguments forwarded to the OpenAI payload builder.
            **kwargs: Keyword arguments forwarded to the OpenAI payload builder.

        Returns:
            The prepared request payload and normalized message context.
        """
        payloads, context_query = await super()._prepare_chat_payload(
            *args,
            **kwargs,
        )
        for key in ("reasoning_effort", "reasoning"):
            if kwargs.get(key) is not None:
                payloads[key] = kwargs[key]
        return payloads, context_query

    def _parse_oauth_expires_at(self) -> datetime | None:
        value = (self.provider_config.get("oauth_expires_at") or "").strip()
        if not value:
            return None
        try:
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return None

    def _oauth_expiring_soon(self) -> bool:
        self._sync_oauth_credentials_from_shared()
        expires_at = self._parse_oauth_expires_at()
        if expires_at is None:
            return False
        refresh_at = datetime.now(timezone.utc) + timedelta(
            seconds=self._oauth_refresh_skew_seconds
        )
        return expires_at <= refresh_at

    def _sync_oauth_credentials_from_shared(self) -> None:
        self.provider_config.update(self._oauth_shared_state.snapshot())
        self.account_id = str(
            self.provider_config.get("oauth_account_id")
            or self.provider_config.get("account_id")
            or ""
        ).strip()
        self.api_keys = [OAUTH_PLACEHOLDER_KEY]
        self.chosen_api_key = ""
        self.client.api_key = OAUTH_PLACEHOLDER_KEY

    def _apply_oauth_token_to_runtime(self, token: dict[str, Any]) -> None:
        access_token = str(token.get("access_token") or "").strip()
        refresh_token = str(token.get("refresh_token") or "").strip()
        patch: dict[str, Any] = {}
        if access_token:
            patch["oauth_access_token"] = access_token
        if refresh_token:
            patch["oauth_refresh_token"] = refresh_token
        patch["oauth_expires_at"] = str(token.get("expires_at") or "")
        patch["oauth_account_email"] = str(
            token.get("email") or ""
        ) or self.provider_config.get("oauth_account_email", "")
        patch["oauth_account_id"] = str(
            token.get("account_id") or ""
        ) or self.provider_config.get("oauth_account_id", "")
        self._oauth_shared_state.apply(patch)
        self._sync_oauth_credentials_from_shared()

    async def _refresh_oauth_token(self) -> bool:
        self._sync_oauth_credentials_from_shared()
        refresh_version, credentials = self._oauth_shared_state.versioned_snapshot()
        refresh_token_value = str(credentials.get("oauth_refresh_token") or "").strip()
        if not refresh_token_value:
            return False

        token = await refresh_access_token(
            refresh_token_value,
            self.provider_config.get("proxy", ""),
        )
        if self._oauth_shared_state.version != refresh_version:
            self._sync_oauth_credentials_from_shared()
            return True
        self._apply_oauth_token_to_runtime(token)

        persist_callback = self._oauth_persist_callback
        if callable(persist_callback):
            patch = {
                "auth_mode": "openai_oauth",
                "oauth_provider": "openai",
                "oauth_access_token": self.provider_config["oauth_access_token"],
                "oauth_refresh_token": self.provider_config["oauth_refresh_token"],
                "oauth_expires_at": self.provider_config["oauth_expires_at"],
                "oauth_account_email": self.provider_config.get(
                    "oauth_account_email", ""
                ),
                "oauth_account_id": self.provider_config.get("oauth_account_id", ""),
            }
            result = persist_callback(patch)
            if inspect.isawaitable(result):
                await result
        return True

    async def _ensure_fresh_oauth_token(self) -> None:
        self._sync_oauth_credentials_from_shared()
        if not self._oauth_expiring_soon():
            return
        async with self._oauth_refresh_lock:
            self._sync_oauth_credentials_from_shared()
            if not self._oauth_expiring_soon():
                return
            await self._refresh_oauth_token()

    async def _refresh_after_auth_failure(self, attempted_version: int) -> bool:
        async with self._oauth_refresh_lock:
            self._sync_oauth_credentials_from_shared()
            if self._oauth_shared_state.version != attempted_version:
                return True
            return await self._refresh_oauth_token()

    def _build_backend_headers(self) -> dict[str, str]:
        headers, _version = self._build_backend_headers_with_version()
        return headers

    def _build_backend_headers_with_version(self) -> tuple[dict[str, str], int]:
        attempted_version, credentials = self._oauth_shared_state.versioned_snapshot()
        self.provider_config.update(credentials)
        access_token = str(credentials.get("oauth_access_token") or "").strip()
        account_id = (
            str(credentials.get("oauth_account_id") or "") or self.account_id
        ).strip()
        if not access_token:
            raise Exception("当前 OAuth Source 尚未绑定 access token")
        if not account_id:
            raise Exception(
                "当前 OAuth Source 缺少 chatgpt_account_id，请重新绑定或导入完整 JSON 凭据"
            )

        claims = decode_jwt_claims(access_token)
        auth_claims = claims.get("https://api.openai.com/auth")
        residency = ""
        if isinstance(auth_claims, dict):
            residency = str(
                auth_claims.get("chatgpt_data_residency")
                or auth_claims.get("chatgpt_compute_residency")
                or ""
            ).strip()
        if not residency:
            residency = str(
                claims.get("chatgpt_data_residency")
                or claims.get("chatgpt_compute_residency")
                or ""
            ).strip()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "OpenAI-Beta": "responses=experimental",
            "originator": "codex_cli_rs",
            "version": CODEX_CLIENT_VERSION,
            "User-Agent": f"codex_cli_rs/{CODEX_CLIENT_VERSION}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if residency:
            headers["x-openai-internal-codex-residency"] = residency
        custom_headers = self.provider_config.get("custom_headers")
        if isinstance(custom_headers, dict):
            for key, value in custom_headers.items():
                headers[str(key)] = str(value)
        return headers, attempted_version

    async def _request_backend_once(
        self,
        payload: dict[str, Any],
    ) -> tuple[int, str, int]:
        headers, attempted_version = self._build_backend_headers_with_version()

        async with httpx.AsyncClient(
            proxy=self.provider_config.get("proxy") or None,
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            response = await client.post(
                f"{self.base_url}/responses",
                headers=headers,
                json=payload,
            )
            raw_text = await response.aread()
        text = raw_text.decode("utf-8", errors="replace")
        return response.status_code, text, attempted_version

    async def _request_backend(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_fresh_oauth_token()
        status_code, text, attempted_version = await self._request_backend_once(payload)

        if status_code in {401, 403}:
            refreshed = await self._refresh_after_auth_failure(attempted_version)
            if refreshed:
                (
                    status_code,
                    text,
                    _attempted_version,
                ) = await self._request_backend_once(payload)

        if status_code < 200 or status_code >= 300:
            raise Exception(self._format_backend_error(status_code, text))
        return self._parse_backend_response(text)

    @asynccontextmanager
    async def _open_oauth_stream_client(self):
        if getattr(self, "_oauth_media_closed", False):
            raise RuntimeError("OAuth provider is closed")
        if not hasattr(self, "_oauth_stream_clients"):
            self._oauth_stream_clients = set()
        client = httpx.AsyncClient(
            proxy=self.provider_config.get("proxy") or None,
            timeout=self.timeout,
            follow_redirects=False,
        )
        self._oauth_stream_clients.add(client)
        try:
            async with client:
                yield client
        finally:
            self._oauth_stream_clients.discard(client)

    async def _stream_backend_events(
        self,
        payload: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield decoded SSE events and refresh OAuth only before any output."""
        if getattr(self, "_oauth_media_closed", False):
            raise RuntimeError("OAuth provider is closed")
        await self._ensure_fresh_oauth_token()
        auth_retry_available = True
        while True:
            headers, attempted_version = self._build_backend_headers_with_version()
            retry_after_auth = False
            async with self._open_oauth_stream_client() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/responses",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code == 401 and auth_retry_available:
                        raw_body = await response.aread()
                        refreshed = await self._refresh_after_auth_failure(
                            attempted_version
                        )
                        if refreshed:
                            auth_retry_available = False
                            retry_after_auth = True
                        else:
                            text = raw_body.decode("utf-8", errors="replace")
                            raise Exception(
                                self._format_backend_error(response.status_code, text)
                            )
                    elif response.status_code < 200 or response.status_code >= 300:
                        raw_body = await response.aread()
                        text = raw_body.decode("utf-8", errors="replace")
                        raise Exception(
                            self._format_backend_error(response.status_code, text)
                        )
                    else:
                        async for event in iter_json_sse_events(response.aiter_lines()):
                            yield event
                            if event.get("type") in {
                                "response.completed",
                                "response.error",
                                "response.failed",
                                "response.incomplete",
                                "error",
                            }:
                                return
            if retry_after_auth:
                continue
            return

    async def _request_image_backend_once(
        self,
        payload: dict[str, Any],
    ) -> tuple[int, str, int]:
        headers, attempted_version = self._build_backend_headers_with_version()

        text_parts: list[str] = []
        async with httpx.AsyncClient(
            proxy=self.provider_config.get("proxy") or None,
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/responses",
                headers=headers,
                json=payload,
            ) as response:
                async for line in response.aiter_lines():
                    text_parts.append(line)
                    stripped = line.strip()
                    if not stripped.startswith("data:"):
                        continue
                    raw = stripped[5:].strip()
                    if not raw:
                        continue
                    if raw == "[DONE]":
                        break
                    try:
                        event = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(event, dict):
                        continue
                    event_type = event.get("type")
                    if event_type in {
                        "response.completed",
                        "response.error",
                        "response.failed",
                    }:
                        break

        return response.status_code, "\n".join(text_parts), attempted_version

    async def _request_image_backend(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_fresh_oauth_token()
        status_code, text, attempted_version = await self._request_image_backend_once(
            payload
        )

        if status_code in {401, 403}:
            refreshed = await self._refresh_after_auth_failure(attempted_version)
            if refreshed:
                (
                    status_code,
                    text,
                    _attempted_version,
                ) = await self._request_image_backend_once(payload)

        if status_code < 200 or status_code >= 300:
            raise Exception(self._format_backend_error(status_code, text))
        return self._parse_backend_response(text)

    def _format_backend_error(self, status_code: int, text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return f"Codex backend request failed: status={status_code}"
        try:
            data = json.loads(stripped)
            return f"Codex backend request failed: status={status_code}, body={data}"
        except Exception:
            return (
                f"Codex backend request failed: status={status_code}, body={stripped}"
            )

    def _parse_backend_response(self, text: str) -> dict[str, Any]:
        completed_response: dict[str, Any] | None = None
        error_payload: dict[str, Any] | None = None
        output_text_parts: list[str] = []
        output_text_done: str | None = None
        output_items: list[dict[str, Any]] = []
        output_item_ids: set[str] = set()
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
            elif event_type == "response.output_text.delta":
                delta = event.get("delta")
                if delta:
                    output_text_parts.append(str(delta))
            elif event_type == "response.output_text.done":
                text_value = event.get("text")
                if text_value is not None:
                    output_text_done = str(text_value)
            elif event_type == "response.output_item.done":
                item = event.get("item")
                if isinstance(item, dict):
                    item_id = str(item.get("id") or "")
                    dedupe_key = item_id or f"index:{len(output_items)}"
                    if dedupe_key not in output_item_ids:
                        output_item_ids.add(dedupe_key)
                        output_items.append(item)
            if event_type == "response.completed":
                response = event.get("response")
                if isinstance(response, dict):
                    completed_response = response
                else:
                    completed_response = event
        merged_output_text = (
            output_text_done
            if output_text_done is not None
            else "".join(output_text_parts)
        )
        if completed_response:
            if not completed_response.get("output") and output_items:
                completed_response["output"] = output_items
            if merged_output_text and not completed_response.get("output_text"):
                completed_response["output_text"] = merged_output_text
            return completed_response
        if error_payload:
            raise Exception(f"Codex backend returned error event: {error_payload}")
        stripped = text.strip()
        if stripped.startswith("{"):
            data = json.loads(stripped)
            if isinstance(data, dict):
                if data.get("type") == "response.completed" and isinstance(
                    data.get("response"), dict
                ):
                    response = data["response"]
                    if not response.get("output") and output_items:
                        response["output"] = output_items
                    if merged_output_text and not response.get("output_text"):
                        response["output_text"] = merged_output_text
                    return response
                return data
        raise Exception(
            "Codex backend response did not contain response.completed event"
        )

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
                raise ValueError(
                    f"OpenAI OAuth 不支持非对象消息内容：{type(part).__name__}。"
                )
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
            else:
                unsupported_type = str(part_type or "unknown")
                raise ValueError(
                    "OpenAI OAuth 尚未适配消息内容类型 "
                    f"{unsupported_type}，不能静默丢弃。"
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
                        arguments = json.dumps(
                            arguments, ensure_ascii=False, default=str
                        )
                    response_items.append(
                        {
                            "type": "function_call",
                            "call_id": call_id,
                            "name": name,
                            "arguments": arguments,
                        }
                    )
        return "\n\n".join(
            part for part in instructions_parts if part
        ).strip(), response_items

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

    async def _record_provider_stat(
        self,
        *,
        request_kind: str,
        status: str,
        usage: TokenUsage | None,
        start_time: float,
        end_time: float,
        model: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Persist one OAuth provider call without affecting its caller.

        Args:
            request_kind: Logical call type used by the synthetic UMO.
            status: Provider call status stored in the database.
            usage: Parsed token usage, or None when the backend omitted it.
            start_time: Epoch time immediately before the public call.
            end_time: Epoch time immediately after the public call.
            model: Explicit request model when supplied.
            session_id: Session identifier when supplied by the caller.
        """
        try:
            provider_id = str(self.provider_config.get("id") or self.meta().id)
            await db_helper.insert_provider_stat(
                umo=session_id or f"provider:{provider_id}:{request_kind}",
                provider_id=provider_id,
                provider_model=model or self.get_model(),
                status=status,
                stats={
                    "token_usage": {
                        "input_other": usage.input_other if usage else 0,
                        "input_cached": usage.input_cached if usage else 0,
                        "output": usage.output if usage else 0,
                    },
                    "start_time": start_time,
                    "end_time": end_time,
                    "time_to_first_token": 0.0,
                },
                agent_type="test" if request_kind == "test" else "provider",
            )
        except Exception:
            logger.warning(
                "Failed to record OpenAI OAuth provider statistics.",
                exc_info=True,
            )

    def _convert_tools_to_backend_format(
        self, tool_list: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
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
                "parameters": function.get("parameters")
                or {"type": "object", "properties": {}},
            }
            backend_tools.append(backend_tool)
        return backend_tools

    @staticmethod
    def _tool_identity(tool: dict[str, Any]) -> str:
        tool_type = str(tool.get("type") or "").strip()
        if tool_type == "function":
            name = str(tool.get("name") or "").strip()
            if not name:
                raise ValueError("function 工具缺少 name。")
            return f"function:{name}"
        if tool_type == "mcp":
            label = str(tool.get("server_label") or "").strip()
            if not label:
                raise ValueError("mcp 工具缺少 server_label。")
            return f"mcp:{label}"
        if not tool_type:
            raise ValueError("工具定义缺少 type。")
        return tool_type

    def _merge_backend_tools(
        self,
        *tool_groups: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        by_identity: dict[str, dict[str, Any]] = {}
        for group in tool_groups:
            for tool in group:
                if not isinstance(tool, dict):
                    raise ValueError("工具定义必须是对象。")
                identity = self._tool_identity(tool)
                existing = by_identity.get(identity)
                if existing is None:
                    copied = dict(tool)
                    by_identity[identity] = copied
                    merged.append(copied)
                    continue
                if existing != tool:
                    raise ValueError(f"工具 {identity} 存在冲突定义。")
        return merged

    def _configured_web_search_tool(self) -> list[dict[str, Any]]:
        mode = (
            str(self.provider_config.get("oauth_web_search") or "disabled")
            .strip()
            .lower()
        )
        if mode == "disabled":
            return []
        if mode not in {"cached", "live"}:
            raise ValueError("oauth_web_search 必须是 disabled、cached 或 live。")
        tool: dict[str, Any] = {
            "type": "web_search",
            "external_web_access": mode == "live",
        }
        domains = self.provider_config.get("oauth_web_search_domains") or []
        if not isinstance(domains, list):
            raise ValueError("oauth_web_search_domains 必须是字符串列表。")
        normalized_domains = []
        for domain in domains:
            if not isinstance(domain, str) or not domain.strip():
                raise ValueError("oauth_web_search_domains 必须是非空字符串列表。")
            normalized = domain.strip().lower()
            if "://" in normalized or "/" in normalized:
                raise ValueError(
                    "oauth_web_search_domains 仅接受域名，不接受 URL 或路径。"
                )
            if normalized not in normalized_domains:
                normalized_domains.append(normalized)
        if normalized_domains:
            tool["filters"] = {"allowed_domains": normalized_domains}
        return [tool]

    def _build_responses_params(self, payloads: dict, tools) -> dict[str, Any]:
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
        function_tools: list[dict[str, Any]] = []
        if tools:
            tool_list = tools.get_func_desc_openai_style(
                omit_empty_parameter_field=False,
            )
            if tool_list:
                function_tools = self._convert_tools_to_backend_format(tool_list)

        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        custom_tools: list[dict[str, Any]] = []
        if isinstance(custom_extra_body, dict):
            for key, value in custom_extra_body.items():
                if key in {"model", "input", "instructions"}:
                    continue
                if key == "tools":
                    if not isinstance(value, list):
                        raise ValueError("custom_extra_body.tools 必须是列表。")
                    custom_tools = value
                    continue
                params[key] = value

        merged_tools = self._merge_backend_tools(
            function_tools,
            custom_tools,
            self._configured_web_search_tool(),
        )
        if merged_tools:
            params["tools"] = merged_tools
        if payloads.get("tool_choice") is not None:
            params["tool_choice"] = payloads["tool_choice"]

        reasoning_value = params.get("reasoning")
        if reasoning_value is not None and not isinstance(reasoning_value, dict):
            raise ValueError("reasoning 必须是对象。")
        reasoning = dict(reasoning_value or {})

        configured_effort = params.pop("reasoning_effort", None)
        if configured_effort is not None and "effort" not in reasoning:
            reasoning["effort"] = configured_effort

        request_effort = payloads.get("reasoning_effort")
        if request_effort is not None:
            reasoning["effort"] = request_effort
        request_reasoning = payloads.get("reasoning")
        if request_reasoning is not None:
            if not isinstance(request_reasoning, dict):
                raise ValueError("reasoning 必须是对象。")
            reasoning.update(request_reasoning)

        if "effort" in reasoning:
            effort = str(reasoning["effort"] or "").strip().lower()
            if effort == "off":
                effort = "none"
            if effort == "ultra":
                raise ValueError(
                    "reasoning_effort=ultra 需要多代理调度，不能作为单次 Provider 请求发送。"
                )
            model = str(params["model"] or "").strip().lower()
            capability = self.model_capabilities.get(model)
            if capability:
                supported = capability["supported_reasoning_efforts"]
                if effort == "max" and effort not in supported and "xhigh" in supported:
                    effort = "xhigh"
                elif effort not in supported:
                    supported_text = ", ".join(supported)
                    raise ValueError(
                        f"模型 {model} 不支持 reasoning_effort={effort}；"
                        f"可用值：{supported_text}。"
                    )
            reasoning["effort"] = effort

        if reasoning:
            params["reasoning"] = reasoning
        else:
            params.pop("reasoning", None)
        params.pop("max_output_tokens", None)
        params.pop("temperature", None)
        return params

    @staticmethod
    def _extract_url_citations(response: Any) -> list[tuple[str, str]]:
        if not isinstance(response, dict):
            return []
        citations: list[tuple[str, str]] = []
        seen_urls: set[str] = set()
        for item in response.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                for annotation in content.get("annotations", []) or []:
                    if not isinstance(annotation, dict):
                        continue
                    if annotation.get("type") not in {"url_citation", "source"}:
                        continue
                    url = str(annotation.get("url") or "").strip()
                    if not url.startswith(("https://", "http://")) or url in seen_urls:
                        continue
                    if any(ord(char) < 32 for char in url):
                        continue
                    try:
                        parsed_url = urlsplit(url)
                        if not parsed_url.hostname or parsed_url.username:
                            continue
                    except ValueError:
                        continue
                    title = str(annotation.get("title") or url).strip() or url
                    title = " ".join(title.split())[:512]
                    title = (
                        title.replace("\\", "\\\\")
                        .replace("[", "\\[")
                        .replace("]", "\\]")
                    )
                    seen_urls.add(url)
                    citations.append((title, quote(url, safe=":/?#@!$&'*+,;=%~.-_")))
        return citations

    async def _parse_responses_completion(self, response: Any, tools) -> LLMResponse:
        llm_response = LLMResponse("assistant")
        output_text = ""
        if isinstance(response, dict):
            output_text = str(response.get("output_text") or "").strip()
        else:
            output_text = (getattr(response, "output_text", None) or "").strip()
        output_items = list(
            response.get("output", [])
            if isinstance(response, dict)
            else getattr(response, "output", []) or []
        )
        reasoning_parts: list[str] = []
        tool_args: list[dict[str, Any]] = []
        tool_names: list[str] = []
        tool_ids: list[str] = []
        message_text_parts: list[str] = []

        for item in output_items:
            item_type = (
                item.get("type")
                if isinstance(item, dict)
                else getattr(item, "type", None)
            )
            if item_type == "reasoning":
                summaries = (
                    item.get("summary", [])
                    if isinstance(item, dict)
                    else getattr(item, "summary", []) or []
                )
                for summary in summaries:
                    text = (
                        summary.get("text")
                        if isinstance(summary, dict)
                        else getattr(summary, "text", None)
                    )
                    if text:
                        reasoning_parts.append(str(text))
            elif item_type == "function_call":
                arguments = (
                    item.get("arguments", "{}")
                    if isinstance(item, dict)
                    else getattr(item, "arguments", "{}")
                )
                try:
                    parsed_args = (
                        json.loads(arguments)
                        if isinstance(arguments, str)
                        else arguments
                    )
                except Exception:
                    parsed_args = {}
                tool_args.append(parsed_args if isinstance(parsed_args, dict) else {})
                tool_names.append(
                    str(
                        item.get("name", "")
                        if isinstance(item, dict)
                        else getattr(item, "name", "") or ""
                    )
                )
                tool_ids.append(
                    str(
                        item.get("call_id", "")
                        if isinstance(item, dict)
                        else getattr(item, "call_id", "") or ""
                    )
                )
            elif item_type == "message" and not output_text:
                content_items = (
                    item.get("content", [])
                    if isinstance(item, dict)
                    else getattr(item, "content", []) or []
                )
                item_text_parts: list[str] = []
                for content in content_items:
                    ctype = (
                        content.get("type")
                        if isinstance(content, dict)
                        else getattr(content, "type", None)
                    )
                    if ctype in {"output_text", "text"}:
                        text = (
                            content.get("text")
                            if isinstance(content, dict)
                            else getattr(content, "text", None)
                        )
                        if text:
                            item_text_parts.append(str(text))
                if item_text_parts:
                    message_text_parts.append("".join(item_text_parts).strip())

        output_text = output_text or "\n".join(message_text_parts)
        citations = self._extract_url_citations(response)
        if output_text:
            if citations:
                citation_text = "\n".join(
                    f"- [{title}]({url})" for title, url in citations
                )
                output_text += f"\n\n来源：\n{citation_text}"
            llm_response.result_chain = MessageChain().message(output_text)

        if reasoning_parts:
            llm_response.reasoning_content = "\n".join(
                part for part in reasoning_parts if part
            )

        if tool_args:
            llm_response.role = "tool"
            llm_response.tools_call_args = tool_args
            llm_response.tools_call_name = tool_names
            llm_response.tools_call_ids = tool_ids

        if llm_response.completion_text is None and not llm_response.tools_call_args:
            raise Exception(f"账号态 responses 响应无法解析：{response}。")

        llm_response.raw_completion = response
        response_id = (
            response.get("id")
            if isinstance(response, dict)
            else getattr(response, "id", None)
        )
        if response_id:
            llm_response.id = response_id
        usage = self._extract_response_usage(
            response.get("usage")
            if isinstance(response, dict)
            else getattr(response, "usage", None)
        )
        if usage is not None:
            llm_response.usage = usage
        return llm_response

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
        tool_choice="auto",
        request_max_retries=None,
        **kwargs,
    ) -> LLMResponse:
        """Run an OAuth chat request and account for direct provider usage.

        Args:
            prompt: User prompt for a new conversation turn.
            session_id: Session identifier used by provider statistics.
            image_urls: Image inputs attached to the user message.
            audio_urls: Audio inputs attached to the user message.
            func_tool: Tools available to the model.
            contexts: Existing conversation messages.
            system_prompt: System instruction for the request.
            tool_calls_result: Results returned from earlier tool calls.
            model: Explicit model override.
            extra_user_content_parts: Additional user message content parts.
            tool_choice: Tool selection policy.
            request_max_retries: Maximum attempts for retryable backend requests.
            **kwargs: Additional provider request options.

        Returns:
            Parsed model response from the inherited OpenAI provider.

        Raises:
            Exception: Re-raises the original provider exception unchanged.
        """
        managed_by_agent = provider_stats_managed_by_agent.get()
        request_kind = oauth_provider_stat_kind.get()
        start_time = time.time()
        kwargs["_oauth_tool_choice"] = tool_choice
        try:
            response = await super().text_chat(
                prompt=prompt,
                session_id=session_id,
                image_urls=image_urls,
                audio_urls=audio_urls,
                func_tool=func_tool,
                contexts=contexts,
                system_prompt=system_prompt,
                tool_calls_result=tool_calls_result,
                model=model,
                extra_user_content_parts=extra_user_content_parts,
                tool_choice=tool_choice,
                request_max_retries=request_max_retries,
                **kwargs,
            )
        except asyncio.CancelledError:
            if not managed_by_agent:
                await self._record_provider_stat(
                    request_kind=request_kind,
                    status="error",
                    usage=None,
                    start_time=start_time,
                    end_time=time.time(),
                    model=model,
                    session_id=session_id,
                )
            raise
        except Exception as exc:
            if not managed_by_agent:
                await self._record_provider_stat(
                    request_kind=request_kind,
                    status="error",
                    usage=getattr(exc, "_astrbot_token_usage", None),
                    start_time=start_time,
                    end_time=time.time(),
                    model=model,
                    session_id=session_id,
                )
            raise

        if not managed_by_agent:
            await self._record_provider_stat(
                request_kind=request_kind,
                status="error" if response.role == "err" else "completed",
                usage=response.usage,
                start_time=start_time,
                end_time=time.time(),
                model=model,
                session_id=session_id,
            )
        return response

    async def test(self, timeout: float = 45.0) -> None:
        token = oauth_provider_stat_kind.set("test")
        try:
            await super().test(timeout)
        finally:
            oauth_provider_stat_kind.reset(token)

    async def _query(
        self,
        payloads: dict,
        tools,
        *,
        request_max_retries: int | None = None,
    ) -> LLMResponse:
        params = self._build_responses_params(payloads, tools)
        response = await retry_provider_request(
            "OpenAI OAuth",
            lambda: self._request_backend(params),
            max_attempts=request_max_retries,
        )
        try:
            return await self._parse_responses_completion(response, tools)
        except Exception as exc:
            usage = self._extract_response_usage(
                response.get("usage")
                if isinstance(response, dict)
                else getattr(response, "usage", None)
            )
            if usage is not None:
                setattr(exc, "_astrbot_token_usage", usage)
            raise

    async def _query_stream(
        self,
        payloads: dict,
        tools,
        *,
        request_max_retries: int | None = None,
    ) -> AsyncGenerator[LLMResponse, None]:
        del request_max_retries
        params = self._build_responses_params(payloads, tools)
        output_text_parts: list[str] = []
        reasoning_parts: list[str] = []
        output_items: dict[str, dict[str, Any]] = {}
        completed_response: dict[str, Any] | None = None

        async with aclosing(self._stream_backend_events(params)) as event_stream:
            async for event in event_stream:
                chunk, completed = self._apply_stream_event(
                    event,
                    output_text_parts,
                    reasoning_parts,
                    output_items,
                )
                if completed is not None:
                    completed_response = completed
                if chunk is not None:
                    yield chunk

        if completed_response is None:
            raise Exception(
                "Codex backend stream ended without response.completed event"
            )
        if not completed_response.get("output") and output_items:
            completed_response["output"] = list(output_items.values())
        if output_text_parts and not completed_response.get("output_text"):
            completed_response["output_text"] = "".join(output_text_parts)
        if reasoning_parts:
            existing_output = list(completed_response.get("output") or [])
            if not any(
                isinstance(item, dict) and item.get("type") == "reasoning"
                for item in existing_output
            ):
                existing_output.append(
                    {
                        "type": "reasoning",
                        "summary": [
                            {"type": "summary_text", "text": "".join(reasoning_parts)}
                        ],
                    }
                )
                completed_response["output"] = existing_output
        final_response = await self._parse_responses_completion(
            completed_response, tools
        )
        if not output_text_parts and final_response.completion_text:
            yield LLMResponse(
                role="assistant",
                completion_text=final_response.completion_text,
                is_chunk=True,
            )
        elif output_text_parts:
            citations = self._extract_url_citations(completed_response)
            if citations:
                citation_text = "\n".join(
                    f"- [{title}]({url})" for title, url in citations
                )
                yield LLMResponse(
                    role="assistant",
                    completion_text=f"\n\n来源：\n{citation_text}",
                    is_chunk=True,
                )
        yield final_response

    def _apply_stream_event(
        self,
        event: dict[str, Any],
        output_text_parts: list[str],
        reasoning_parts: list[str],
        output_items: dict[str, dict[str, Any]],
    ) -> tuple[LLMResponse | None, dict[str, Any] | None]:
        event_type = event.get("type")
        if event_type in {
            "error",
            "response.error",
            "response.failed",
            "response.incomplete",
        }:
            error = RuntimeError(f"Codex backend stream ended with {event_type}")
            response = event.get("response")
            if isinstance(response, dict):
                usage = self._extract_response_usage(response.get("usage"))
                if usage is not None:
                    setattr(error, "_astrbot_token_usage", usage)
            raise error
        if event_type == "response.output_text.delta":
            delta = str(event.get("delta") or "")
            if delta:
                output_text_parts.append(delta)
                return (
                    LLMResponse(
                        role="assistant",
                        completion_text=delta,
                        is_chunk=True,
                    ),
                    None,
                )
        elif event_type in {
            "response.reasoning_summary_text.delta",
            "response.reasoning_text.delta",
        }:
            delta = str(event.get("delta") or "")
            if delta:
                reasoning_parts.append(delta)
                return (
                    LLMResponse(
                        role="assistant",
                        reasoning_content=delta,
                        is_chunk=True,
                    ),
                    None,
                )
        elif event_type == "response.output_item.added":
            item = event.get("item")
            if isinstance(item, dict):
                item_id = str(item.get("id") or event.get("output_index") or "")
                if item_id:
                    output_items[item_id] = dict(item)
        elif event_type == "response.function_call_arguments.delta":
            item_id = str(event.get("item_id") or event.get("output_index") or "")
            delta = str(event.get("delta") or "")
            item = output_items.setdefault(
                item_id,
                {
                    "type": "function_call",
                    "call_id": str(event.get("call_id") or ""),
                    "name": str(event.get("name") or ""),
                    "arguments": "",
                },
            )
            item["arguments"] = str(item.get("arguments") or "") + delta
            if delta:
                return (
                    LLMResponse(
                        role="tool",
                        tools_call_args=[{"_arguments_delta": delta}],
                        tools_call_name=[str(item.get("name") or "")],
                        tools_call_ids=[str(item.get("call_id") or item_id)],
                        is_chunk=True,
                    ),
                    None,
                )
        elif event_type == "response.output_item.done":
            item = event.get("item")
            if isinstance(item, dict):
                item_id = str(item.get("id") or event.get("output_index") or "")
                output_items[item_id] = dict(item)
        elif event_type == "response.completed":
            response = event.get("response")
            return None, dict(response) if isinstance(response, dict) else {}
        return None, None

    async def generate_image(
        self,
        prompt: str,
        model: str | None = None,
        size: str | None = None,
        n: int = 1,
        reference_images: list[str] | None = None,
        action: str | None = None,
    ) -> list[OpenAIOAuthImageResult]:
        """Generate images and persist aggregate OAuth token usage.

        Args:
            prompt: Image generation or editing instruction.
            model: Explicit model override.
            size: Requested image dimensions.
            n: Number of backend image generations.
            reference_images: Local files, URLs, or data URLs used as references.
            action: Image tool action override.

        Returns:
            Extracted image results from all backend generations.

        Raises:
            Exception: Re-raises validation, backend, or extraction failures.
        """
        start_time = time.time()
        total_usage = TokenUsage()
        try:
            references = [
                str(image).strip()
                for image in reference_images or []
                if str(image).strip()
            ]
            instructions = str(prompt or "").strip()
            if not instructions:
                raise ValueError("图片生成提示词不能为空。")
            image_input = self._build_image_generation_input(instructions, references)
            image_action = (action or ("edit" if references else "generate")).strip()
            if not image_action:
                image_action = "edit" if references else "generate"
            results: list[OpenAIOAuthImageResult] = []
            count = max(1, int(n or 1))
            for _ in range(count):
                tool: dict[str, Any] = {
                    "type": "image_generation",
                    "action": image_action,
                }
                if size:
                    tool["size"] = size
                payload = {
                    "model": model or self.get_model(),
                    "input": image_input,
                    "instructions": instructions,
                    "tools": [tool],
                    "tool_choice": {"type": "image_generation"},
                    "stream": True,
                    "store": False,
                }
                response = await self._request_image_backend(payload)
                response_usage = self._extract_response_usage(response.get("usage"))
                if response_usage is not None:
                    total_usage = total_usage + response_usage
                results.extend(await self._extract_generated_images(response))
        except (Exception, asyncio.CancelledError):
            await self._record_provider_stat(
                request_kind="image",
                status="error",
                usage=total_usage,
                start_time=start_time,
                end_time=time.time(),
                model=model,
            )
            raise

        await self._record_provider_stat(
            request_kind="image",
            status="completed",
            usage=total_usage,
            start_time=start_time,
            end_time=time.time(),
            model=model,
        )
        return results

    def _build_image_generation_input(
        self,
        prompt: str,
        reference_images: list[str],
    ) -> list[dict[str, Any]]:
        image_parts = [
            self._reference_image_to_input_part(image)
            for image in reference_images
            if str(image or "").strip()
        ]
        return [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    },
                    *image_parts,
                ],
            }
        ]

    def _reference_image_to_input_part(self, image: str) -> dict[str, str]:
        return {
            "type": "input_image",
            "image_url": self._reference_image_to_image_url(image),
        }

    def _reference_image_to_image_url(self, image: str) -> str:
        value = str(image or "").strip()
        if not value:
            raise ValueError("参考图不能为空。")

        lower = value.lower()
        if lower.startswith("data:image/"):
            return value
        if lower.startswith(("http://", "https://")):
            return value

        path_value = value[7:] if lower.startswith("file://") else value
        path = Path(path_value).expanduser()
        if not path.is_file():
            raise ValueError(f"参考图文件不存在: {value}")

        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        if not mime_type.startswith("image/"):
            mime_type = "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode()
        return f"data:{mime_type};base64,{encoded}"

    async def _extract_generated_images(
        self,
        response: dict[str, Any],
    ) -> list[OpenAIOAuthImageResult]:
        output = response.get("output") or []
        if not isinstance(output, list):
            output = []

        image_dir_value = self.provider_config.get("generated_image_dir")
        image_dir = (
            Path(str(image_dir_value))
            if image_dir_value
            else Path(get_astrbot_data_path()) / "generated" / "openai_oauth_images"
        )
        image_dir.mkdir(parents=True, exist_ok=True)

        results: list[OpenAIOAuthImageResult] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            image_base64 = self._extract_image_base64_from_output_item(item)
            if not image_base64:
                continue
            if "," in image_base64 and image_base64.startswith("data:"):
                image_base64 = image_base64.split(",", 1)[1]
            file_path = image_dir / f"{uuid.uuid4().hex}.png"
            file_path.write_bytes(base64.b64decode(image_base64))
            results.append(
                OpenAIOAuthImageResult(
                    path=str(file_path),
                    mime_type="image/png",
                    revised_prompt=str(item.get("revised_prompt") or ""),
                    raw=item,
                )
            )

        if not results:
            raise Exception(f"Codex 图像生成响应未包含可提取图片：{response}")
        return results

    def _extract_image_base64_from_output_item(self, item: dict[str, Any]) -> str:
        if item.get("type") == "image_generation_call":
            value = item.get("result")
            if value:
                return str(value)

        content = item.get("content")
        if not isinstance(content, list):
            return ""
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") not in {"output_image", "image"}:
                continue
            value = (
                part.get("image_base64")
                or part.get("b64_json")
                or part.get("data")
                or ""
            )
            if value:
                return str(value)
        return ""

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
        tool_choice="auto",
        request_max_retries=None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        extra_user_content_parts = kwargs.pop("extra_user_content_parts", None)
        payloads, _context_query = await self._prepare_chat_payload(
            prompt,
            image_urls,
            audio_urls,
            contexts,
            system_prompt,
            tool_calls_result,
            model=model,
            extra_user_content_parts=extra_user_content_parts,
            **kwargs,
        )
        if (func_tool and not func_tool.empty()) or tool_choice != "auto":
            payloads["tool_choice"] = tool_choice

        managed_by_agent = provider_stats_managed_by_agent.get()
        request_kind = oauth_provider_stat_kind.get()
        start_time = time.time()
        final_response: LLMResponse | None = None
        try:
            async with aclosing(
                self._query_stream(
                    payloads,
                    func_tool,
                    request_max_retries=request_max_retries,
                )
            ) as response_stream:
                async for response in response_stream:
                    if not response.is_chunk:
                        final_response = response
                    yield response
        except (asyncio.CancelledError, GeneratorExit):
            if not managed_by_agent:
                await self._record_provider_stat(
                    request_kind=request_kind,
                    status="error",
                    usage=None,
                    start_time=start_time,
                    end_time=time.time(),
                    model=model,
                    session_id=session_id,
                )
            raise
        except Exception as exc:
            if not managed_by_agent:
                await self._record_provider_stat(
                    request_kind=request_kind,
                    status="error",
                    usage=getattr(exc, "_astrbot_token_usage", None),
                    start_time=start_time,
                    end_time=time.time(),
                    model=model,
                    session_id=session_id,
                )
            raise

        if final_response is None:
            raise Exception("Codex backend stream did not produce a final response")
        if not managed_by_agent:
            await self._record_provider_stat(
                request_kind=request_kind,
                status="error" if final_response.role == "err" else "completed",
                usage=final_response.usage,
                start_time=start_time,
                end_time=time.time(),
                model=model,
                session_id=session_id,
            )
