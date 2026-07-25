import base64
import json
from collections.abc import AsyncGenerator
from typing import Any, Literal
from urllib.parse import urlparse

import anthropic
import httpx
from anthropic import AsyncAnthropic
from anthropic.types import Message
from anthropic.types.message_delta_usage import MessageDeltaUsage
from anthropic.types.usage import Usage

from astrbot import logger
from astrbot.api.provider import Provider
from astrbot.core.agent.message import AudioURLPart, ContentPart, ImageURLPart, TextPart
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot.core.provider.func_tool_manager import ToolSet
from astrbot.core.utils.media_utils import (
    describe_media_ref,
    resolve_media_ref_to_base64_data,
)
from astrbot.core.utils.network_utils import (
    create_proxy_client,
    is_connection_error,
    log_connection_failure,
)

from ..register import register_provider_adapter
from .request_retry import retry_provider_request, retry_provider_request_context


@register_provider_adapter(
    "anthropic_chat_completion",
    "Anthropic Claude API 提供商适配器",
)
class ProviderAnthropic(Provider):
    # --- prompt caching 调参区（可直接改这些常量） ------------------------
    _PROMPT_CACHE_CONTROL = {"type": "ephemeral"}
    """cache_control 基础结构，``ttl`` 在运行时按需补上。"""

    _PROMPT_CACHE_MAX_BREAKPOINTS = 4
    """Anthropic 单次请求允许的 cache_control 断点上限（API 硬限制）。"""

    _PROMPT_CACHE_TRAILING_MESSAGES = 3
    """在消息列表尾部滚动放置的断点数量。

    每轮请求通常只往历史里追加 2 条消息（assistant + user/tool_result），
    标记最后 3 条即可保证「上一次请求的断点位置」必然与本次某个断点**完全重合**，
    从而拿到精确命中，不依赖 API 20 个 block 的回看窗口。
    """

    _PROMPT_CACHE_MIN_CHARS = 6000
    """小于该字符规模的请求不打断点。

    prompt 前缀低于模型的最小可缓存长度时缓存会被静默忽略；而刚刚过线的一次性
    短请求（例如会话标题生成）只会白付 1.25x 的写入费。
    """

    _PROMPT_CACHE_IMAGE_CHARS = 4000
    """估算规模时，单个图片 block 折算的字符数。"""

    _PROMPT_CACHE_LONG_TTL_HOSTS = ("api.anthropic.com",)
    """默认启用 1h TTL 的官方域名。

    IM 闲聊场景相邻两轮常常间隔超过 5 分钟，默认 5 分钟 TTL 会整段失效。
    第三方 Anthropic 兼容端点不一定支持 ``ttl`` 字段，因此只对官方域名默认开启，
    其余保持原有的 5 分钟行为。可用 provider 配置 ``anth_prompt_cache_ttl``
    覆盖（``"1h"`` / ``"5m"`` / ``"off"``）。
    """

    _PROMPT_CACHE_MARKABLE_BLOCK_TYPES = frozenset(
        {"text", "image", "tool_use", "tool_result", "document"},
    )
    """允许挂 cache_control 的 block 类型（``thinking`` 等不在其列）。"""

    @staticmethod
    def _ensure_usable_response(
        llm_response: LLMResponse,
        *,
        completion_id: str | None = None,
        stop_reason: str | None = None,
    ) -> None:
        has_text_output = bool((llm_response.completion_text or "").strip())
        has_reasoning_output = bool((llm_response.reasoning_content or "").strip())
        has_tool_output = bool(llm_response.tools_call_args)
        if has_text_output or has_reasoning_output or has_tool_output:
            return
        raise EmptyModelOutputError(
            "Anthropic completion has no usable output. "
            f"completion_id={completion_id}, stop_reason={stop_reason}"
        )

    @staticmethod
    def _normalize_custom_headers(provider_config: dict) -> dict[str, str] | None:
        custom_headers = provider_config.get("custom_headers", {})
        if not isinstance(custom_headers, dict) or not custom_headers:
            return None
        normalized_headers: dict[str, str] = {}
        for key, value in custom_headers.items():
            normalized_headers[str(key)] = str(value)
        return normalized_headers or None

    @classmethod
    def _resolve_custom_headers(
        cls,
        provider_config: dict,
        *,
        required_headers: dict[str, str] | None = None,
    ) -> dict[str, str] | None:
        merged_headers = cls._normalize_custom_headers(provider_config) or {}
        if required_headers:
            for header_name, header_value in required_headers.items():
                if not merged_headers.get(header_name, "").strip():
                    merged_headers[header_name] = header_value
        return merged_headers or None

    def __init__(
        self,
        provider_config,
        provider_settings,
        *,
        use_api_key: bool = True,
    ) -> None:
        super().__init__(
            provider_config,
            provider_settings,
        )

        self.base_url = provider_config.get("api_base", "https://api.anthropic.com")
        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)
        self.thinking_config = provider_config.get("anth_thinking_config", {})
        self.custom_headers = self._resolve_custom_headers(provider_config)

        if use_api_key:
            self._init_api_key(provider_config)

        self.set_model(provider_config.get("model", "unknown"))

    def _init_api_key(self, provider_config: dict) -> None:
        self.chosen_api_key: str = ""
        self.api_keys: list = super().get_keys()
        self.chosen_api_key = self.api_keys[0] if len(self.api_keys) > 0 else ""
        self.client = AsyncAnthropic(
            api_key=self.chosen_api_key,
            timeout=self.timeout,
            base_url=self.base_url,
            default_headers=self.custom_headers,
            http_client=self._create_http_client(provider_config),
        )

    def _create_http_client(self, provider_config: dict) -> httpx.AsyncClient | None:
        """Create an HTTP client with optional proxy and system SSL trust store.

        The Anthropic SDK validates ``http_client`` with
        ``isinstance(..., httpx.AsyncClient)`` against its own ``httpx`` import.
        When multiple ``httpx`` installations are present on ``sys.path``
        (e.g. bundled Python + system Python), constructing the client from a
        different ``httpx`` module makes that check fail. We therefore prefer
        the SDK's own ``httpx`` module when available.
        """
        proxy = provider_config.get("proxy", "")
        if not proxy:
            return None
        httpx_module: Any = httpx
        try:
            from anthropic import _base_client as anthropic_base_client

            httpx_module = getattr(anthropic_base_client, "httpx", httpx)
        except ImportError:
            pass
        return create_proxy_client(
            "Anthropic",
            proxy,
            headers=self.custom_headers,
            httpx_module=httpx_module,
        )

    def _apply_thinking_config(self, payloads: dict) -> None:
        thinking_type = self.thinking_config.get("type", "")
        if thinking_type == "adaptive":
            payloads["thinking"] = {"type": "adaptive"}
            effort = self.thinking_config.get("effort", "")
            output_cfg = dict(payloads.get("output_config", {}))
            if effort:
                output_cfg["effort"] = effort
            if output_cfg:
                payloads["output_config"] = output_cfg
        elif not thinking_type and self.thinking_config.get("budget"):
            payloads["thinking"] = {
                "budget_tokens": self.thinking_config.get("budget"),
                "type": "enabled",
            }

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
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": message["tool_call_id"],
                    "content": message["content"] or "<empty response>",
                }
                last_message = new_messages[-1] if new_messages else None
                last_content = (
                    last_message.get("content")
                    if isinstance(last_message, dict)
                    else None
                )

                if (
                    last_message is not None
                    and last_message.get("role") == "user"
                    and isinstance(last_content, list)
                    and len(last_content) > 0
                    and all(
                        isinstance(block, dict) and block.get("type") == "tool_result"
                        for block in last_content
                    )
                ):
                    last_content.append(tool_result_block)
                else:
                    new_messages.append(
                        {
                            "role": "user",
                            "content": [tool_result_block],
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
                        elif part.get("type") == "audio_url":
                            converted_content.append(
                                {
                                    "type": "text",
                                    "text": "[Audio Attachment]",
                                }
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

    @staticmethod
    def _merge_consecutive_anthropic_messages(messages: list[Any]) -> list[Any]:
        """Merge adjacent Anthropic messages with the same role.

        Args:
            messages: Anthropic messages to merge.

        Returns:
            Merged Anthropic messages. When merging user messages, tool result
            blocks are moved before other blocks to satisfy Anthropic ordering.
        """
        merged: list[Any] = []
        for msg in messages:
            if not isinstance(msg, dict):
                merged.append(msg)
                continue

            if (
                msg.get("role")
                and merged
                and isinstance(merged[-1], dict)
                and merged[-1].get("role") == msg.get("role")
            ):
                prev = merged[-1]
                prev_content = prev.get("content") or []
                if isinstance(prev_content, str):
                    prev_content = [{"type": "text", "text": prev_content}]
                elif isinstance(prev_content, list):
                    prev_content = list(prev_content)
                else:
                    prev_content = [prev_content]

                cur_content = msg.get("content") or []
                if isinstance(cur_content, str):
                    cur_content = [{"type": "text", "text": cur_content}]
                elif isinstance(cur_content, list):
                    cur_content = list(cur_content)
                else:
                    cur_content = [cur_content]

                combined_content = prev_content + cur_content
                if msg.get("role") == "user":
                    tool_results = [
                        block
                        for block in combined_content
                        if isinstance(block, dict)
                        and block.get("type") == "tool_result"
                    ]
                    if tool_results:
                        combined_content = tool_results + [
                            block
                            for block in combined_content
                            if not (
                                isinstance(block, dict)
                                and block.get("type") == "tool_result"
                            )
                        ]

                merged[-1] = {**prev, "content": combined_content}
            else:
                merged.append(msg)

        return merged

    @staticmethod
    def _sanitize_assistant_messages(payloads: dict) -> None:
        """Remove orphaned tool results from Anthropic messages.

        Args:
            payloads: Anthropic request payload containing a messages list.

        Returns:
            None. The messages list is updated in place on ``payloads``.
        """
        messages = payloads.get("messages")
        if not isinstance(messages, list):
            return

        merged = ProviderAnthropic._merge_consecutive_anthropic_messages(messages)
        sanitized: list[Any] = []
        pending_tool_use_ids: set[str] = set()
        for msg in merged:
            if not isinstance(msg, dict):
                sanitized.append(msg)
                pending_tool_use_ids = set()
                continue

            role = msg.get("role")
            content = msg.get("content")
            if role == "assistant":
                pending_tool_use_ids = set()
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_use_id = block.get("id")
                            if tool_use_id:
                                pending_tool_use_ids.add(tool_use_id)
                sanitized.append(msg)
                continue

            if role == "user" and isinstance(content, list):
                tool_results: list[Any] = []
                other_blocks: list[Any] = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id in pending_tool_use_ids:
                            tool_results.append(block)
                            pending_tool_use_ids.remove(tool_use_id)
                        continue
                    other_blocks.append(block)

                cleaned_content = tool_results + other_blocks
                if cleaned_content:
                    sanitized.append({**msg, "content": cleaned_content})
                pending_tool_use_ids = set()
                continue

            sanitized.append(msg)
            pending_tool_use_ids = set()

        payloads["messages"] = ProviderAnthropic._merge_consecutive_anthropic_messages(
            sanitized
        )

    def _extract_usage(self, usage: Usage | None) -> TokenUsage:
        if usage is None:
            return TokenUsage()
        # https://docs.claude.com/en/docs/build-with-claude/prompt-caching#tracking-cache-performance
        # cache_creation_input_tokens 在 TokenUsage 里没有对应字段，但它是判断
        # 断点是否生效的唯一依据，所以至少打到 debug 日志里。
        logger.debug(
            "Anthropic prompt cache usage: uncached=%s cache_write=%s "
            "cache_read=%s output=%s",
            usage.input_tokens or 0,
            getattr(usage, "cache_creation_input_tokens", None) or 0,
            usage.cache_read_input_tokens or 0,
            usage.output_tokens or 0,
        )
        return TokenUsage(
            input_other=usage.input_tokens or 0,
            input_cached=usage.cache_read_input_tokens or 0,
            output=usage.output_tokens or 0,
        )

    def _update_usage(self, token_usage: TokenUsage, usage: MessageDeltaUsage) -> None:
        if usage.input_tokens is not None:
            token_usage.input_other = usage.input_tokens
        if usage.cache_read_input_tokens is not None:
            token_usage.input_cached = usage.cache_read_input_tokens
        if usage.output_tokens is not None:
            token_usage.output = usage.output_tokens

    @staticmethod
    def _normalize_tool_choice(tool_choice) -> dict:
        """将 tool_choice 转换为 Anthropic API 要求的格式

        参考: https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools#controlling-claudes-output

        Args:
            tool_choice: 原始 tool_choice 值，支持 str 或 dict

        Returns:
            Anthropic API 格式的 tool_choice 字典
        """
        if isinstance(tool_choice, dict):
            return tool_choice

        if tool_choice == "required":
            # 兼容 OpenAI 命名：required → any
            return {"type": "any"}

        if tool_choice in ("auto", "any", "none"):
            return {"type": tool_choice}

        if tool_choice == "tool":
            # {"type": "tool"} 必须配合 name 字段指定具体工具
            # 纯字符串 "tool" 无法指定工具名，回退为 auto
            logger.warning("tool_choice='tool' 无法指定工具名，已回退为 'auto'")
            return {"type": "auto"}

        logger.warning(f"未知的 tool_choice 值: {tool_choice}，已回退为 'auto'")
        return {"type": "auto"}

    def _prompt_cache_control(self) -> dict | None:
        """解析本次请求要用的 cache_control，返回 ``None`` 表示禁用 prompt caching。"""
        configured = (
            str(self.provider_config.get("anth_prompt_cache_ttl", "") or "")
            .strip()
            .lower()
        )
        if configured in ("off", "none", "disable", "disabled"):
            return None

        cache_control = dict(self._PROMPT_CACHE_CONTROL)
        if configured in ("", "auto"):
            host = urlparse(getattr(self, "base_url", "") or "").hostname or ""
            if host in self._PROMPT_CACHE_LONG_TTL_HOSTS:
                cache_control["ttl"] = "1h"
        elif configured not in ("5m", "default"):
            cache_control["ttl"] = configured
        return cache_control

    @classmethod
    def _estimate_block_chars(cls, block: Any) -> int:
        """粗略估算单个 content block 的字符规模（仅用于「值不值得缓存」判断）。"""
        if isinstance(block, str):
            return len(block)
        if not isinstance(block, dict):
            return 0
        if block.get("type") == "image":
            return cls._PROMPT_CACHE_IMAGE_CHARS

        total = 0
        text = block.get("text")
        if isinstance(text, str):
            total += len(text)
        content = block.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for sub_block in content:
                total += cls._estimate_block_chars(sub_block)
        tool_input = block.get("input")
        if tool_input is not None:
            total += len(str(tool_input))
        return total

    @classmethod
    def _estimate_cacheable_chars(cls, payloads: dict, *, stop_at: int) -> int:
        """估算 tools + system + messages 的总字符数，达到 ``stop_at`` 即提前返回。"""
        total = 0
        for block in payloads.get("system") or []:
            total += cls._estimate_block_chars(block)
            if total >= stop_at:
                return total
        for tool in payloads.get("tools") or []:
            if isinstance(tool, dict):
                total += len(json.dumps(tool, ensure_ascii=False, default=str))
            if total >= stop_at:
                return total
        for message in payloads.get("messages") or []:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for block in content:
                    total += cls._estimate_block_chars(block)
            if total >= stop_at:
                return total
        return total

    @staticmethod
    def _count_existing_cache_breakpoints(payloads: dict) -> int:
        """统计调用方（插件等）已经放置的 cache_control 断点数量。"""
        count = 0
        for section in ("system", "tools"):
            for block in payloads.get(section) or []:
                if isinstance(block, dict) and block.get("cache_control"):
                    count += 1
        for message in payloads.get("messages") or []:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("cache_control"):
                        count += 1
        return count

    @staticmethod
    def _normalize_message_content_blocks(payloads: dict) -> None:
        """把字符串 content 统一规范化成单个 text block。

        只有 block 才能承载 cache_control。如果只在「需要打断点的那条消息」上做转换，
        同一条历史消息会因为在不同请求里是否被标记而呈现两种形状，前缀字节随之抖动，
        缓存必然落空。所以这里对所有消息无条件规范化，保证形状稳定。
        """
        messages = payloads.get("messages")
        if not isinstance(messages, list):
            return
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                messages[index] = {
                    **message,
                    "content": [{"type": "text", "text": content}],
                }

    @staticmethod
    def _with_cache_control(block: dict, cache_control: dict) -> dict:
        """返回带 cache_control 的 block 副本（不修改调用方持有的历史对象）。"""
        return {**block, "cache_control": dict(cache_control)}

    @classmethod
    def _message_with_cache_breakpoint(
        cls,
        message: dict,
        cache_control: dict,
    ) -> dict | None:
        """把断点挂到 message 的最后一个 block 上，返回消息副本。

        无法安全挂载时返回 ``None``（调用方应跳过该消息，不消耗断点额度）。
        纯字符串 content 会被规范化成单个 text block —— 只有 block 才能承载
        cache_control，且必须对所有请求保持同样的形状，否则前缀字节不一致。
        """
        content = message.get("content")
        if isinstance(content, str):
            if not content.strip():
                return None
            blocks: list[Any] = [{"type": "text", "text": content}]
        elif isinstance(content, list) and content:
            blocks = list(content)
        else:
            return None

        last_block = blocks[-1]
        if not isinstance(last_block, dict) or last_block.get("cache_control"):
            return None
        if last_block.get("type") not in cls._PROMPT_CACHE_MARKABLE_BLOCK_TYPES:
            return None

        blocks[-1] = cls._with_cache_control(last_block, cache_control)
        return {**message, "content": blocks}

    @classmethod
    def _apply_message_cache_breakpoints(
        cls,
        payloads: dict,
        cache_control: dict,
        limit: int,
    ) -> int:
        """从尾部往前给最多 ``limit`` 条消息打断点，返回实际打上的数量。"""
        if limit <= 0:
            return 0
        messages = payloads.get("messages")
        if not isinstance(messages, list) or not messages:
            return 0

        marked = 0
        for index in range(len(messages) - 1, -1, -1):
            if marked >= limit:
                break
            message = messages[index]
            if not isinstance(message, dict):
                continue
            updated = cls._message_with_cache_breakpoint(message, cache_control)
            if updated is None:
                continue
            messages[index] = updated
            marked += 1
        return marked

    def _apply_explicit_prompt_cache_breakpoints(self, payloads: dict) -> None:
        """放置 prompt cache 断点。

        渲染顺序是 ``tools`` → ``system`` → ``messages``，前缀里任何字节变化都会让
        其后的缓存失效。因此：

        * system 末尾放一个断点，缓存 ``tools + system``。它跨会话共享，
          新会话 / 标题生成 / 上下文压缩之后仍然能命中。
        * 消息尾部滚动放最多 3 个断点，把不断增长的历史也纳入缓存 ——
          这是 IM 长对话和工具调用循环里真正在涨的那部分。

        断点总数受 API 限制为 4 个，且已经被调用方占用的额度会被扣除。
        """
        cache_control = self._prompt_cache_control()
        if cache_control is None:
            return

        # 无条件执行，不受下面的规模阈值影响：同一会话在跨过阈值前后必须是同一种形状。
        self._normalize_message_content_blocks(payloads)

        min_chars = self._PROMPT_CACHE_MIN_CHARS
        if self._estimate_cacheable_chars(payloads, stop_at=min_chars) < min_chars:
            return

        budget = self._PROMPT_CACHE_MAX_BREAKPOINTS - (
            self._count_existing_cache_breakpoints(payloads)
        )
        if budget <= 0:
            return

        # 插件如果自己在 system 里放了断点，说明它想自己控制切分位置，我们不再插手。
        system_blocks = payloads.get("system")
        system_markable = (
            isinstance(system_blocks, list)
            and bool(system_blocks)
            and isinstance(system_blocks[-1], dict)
            and not any(
                isinstance(block, dict) and block.get("cache_control")
                for block in system_blocks
            )
        )
        system_slot = 1 if system_markable else 0

        message_slots = max(
            0,
            min(budget - system_slot, self._PROMPT_CACHE_TRAILING_MESSAGES),
        )
        used = self._apply_message_cache_breakpoints(
            payloads,
            cache_control,
            message_slots,
        )

        if system_slot and used + system_slot <= budget:
            new_system_blocks = list(system_blocks)  # type: ignore[arg-type]
            new_system_blocks[-1] = self._with_cache_control(
                new_system_blocks[-1],
                cache_control,
            )
            payloads["system"] = new_system_blocks

    async def _query(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> LLMResponse:
        if tools:
            if tool_list := tools.get_func_desc_anthropic_style():
                payloads["tools"] = tool_list
                payloads["tool_choice"] = self._normalize_tool_choice(
                    payloads.get("tool_choice", "auto")
                )

        extra_body = self.provider_config.get("custom_extra_body", {})

        if "max_tokens" not in payloads:
            payloads["max_tokens"] = 65536
        self._apply_thinking_config(payloads)
        self._sanitize_assistant_messages(payloads)
        # 必须在 sanitize 之后：那一步会合并/重排消息，断点位置只有在最终消息列表上才有意义。
        self._apply_explicit_prompt_cache_breakpoints(payloads)

        try:
            completion = await retry_provider_request(
                "Anthropic",
                lambda: self.client.messages.create(
                    **payloads, stream=False, extra_body=extra_body
                ),
                max_attempts=request_max_retries,
            )
        except httpx.RequestError as e:
            proxy = self.provider_config.get("proxy", "")
            log_connection_failure("Anthropic", e, proxy)
            raise
        except Exception as e:
            if is_connection_error(e):
                proxy = self.provider_config.get("proxy", "")
                log_connection_failure("Anthropic", e, proxy)
            raise

        assert isinstance(completion, Message)
        logger.debug(f"completion: {completion}")

        if len(completion.content) == 0:
            raise EmptyModelOutputError(
                f"Anthropic completion is empty. completion_id={completion.id}"
            )

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

        # Handle cases where completion only contains ThinkingBlock (e.g., MiniMax max_tokens)
        # When stop_reason='max_tokens', the model may return only thinking content
        # This is valid and should not raise an exception
        if not llm_response.completion_text and not llm_response.tools_call_args:
            # Guard clause: raise early if no valid content at all
            if not llm_response.reasoning_content:
                raise EmptyModelOutputError(
                    "Anthropic completion has no usable output. "
                    f"completion_id={completion.id}, stop_reason={completion.stop_reason}"
                )

            # We have reasoning content (ThinkingBlock) - this is valid
            stop_reason = getattr(completion, "stop_reason", "unknown")
            logger.debug(
                f"Completion contains only ThinkingBlock (stop_reason={stop_reason})"
            )
            llm_response.completion_text = ""  # Ensure empty string, not None

        self._ensure_usable_response(
            llm_response,
            completion_id=completion.id,
            stop_reason=completion.stop_reason,
        )
        return llm_response

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> AsyncGenerator[LLMResponse, None]:
        if tools:
            if tool_list := tools.get_func_desc_anthropic_style():
                payloads["tools"] = tool_list
                payloads["tool_choice"] = self._normalize_tool_choice(
                    payloads.get("tool_choice", "auto")
                )

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
            payloads["max_tokens"] = 65536
        self._apply_thinking_config(payloads)
        self._sanitize_assistant_messages(payloads)
        # 必须在 sanitize 之后：那一步会合并/重排消息，断点位置只有在最终消息列表上才有意义。
        self._apply_explicit_prompt_cache_breakpoints(payloads)

        async with retry_provider_request_context(
            "Anthropic",
            lambda: self.client.messages.stream(**payloads, extra_body=extra_body),
            max_attempts=request_max_retries,
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

        self._ensure_usable_response(
            final_response,
            completion_id=id,
            stop_reason=None,
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
        tool_choice: Literal["auto", "any", "tool", "none"] | dict[str, str] = "auto",
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
                for tool_call_result in tool_calls_result:
                    context_query.extend(tool_call_result.to_openai_messages())

        system_prompt, new_messages = self._prepare_payload(context_query)

        model = model or self.get_model()

        payloads = {"messages": new_messages, "model": model}
        if func_tool and not func_tool.empty():
            payloads["tool_choice"] = tool_choice

        # Anthropic has a different way of handling system prompts
        if system_prompt:
            payloads["system"] = (
                [{"type": "text", "text": system_prompt}]
                if isinstance(system_prompt, str)
                else system_prompt
            )

        llm_response = None
        try:
            llm_response = await self._query(
                payloads,
                func_tool,
                request_max_retries=request_max_retries,
            )
        except Exception as e:
            raise e

        return llm_response

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
        tool_choice: Literal["auto", "any", "tool", "none"] | dict[str, str] = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ):
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
                for tool_call_result in tool_calls_result:
                    context_query.extend(tool_call_result.to_openai_messages())

        system_prompt, new_messages = self._prepare_payload(context_query)

        model = model or self.get_model()

        payloads = {"messages": new_messages, "model": model}
        if func_tool and not func_tool.empty():
            payloads["tool_choice"] = tool_choice

        # Anthropic has a different way of handling system prompts
        if system_prompt:
            payloads["system"] = (
                [{"type": "text", "text": system_prompt}]
                if isinstance(system_prompt, str)
                else system_prompt
            )

        async for llm_response in self._query_stream(
            payloads,
            func_tool,
            request_max_retries=request_max_retries,
        ):
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
        audio_urls: list[str] | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
    ):
        """组装上下文，支持文本和图片"""

        async def resolve_image_url(image_url: str) -> dict | None:
            image_data = await resolve_media_ref_to_base64_data(
                image_url,
                media_type="image",
            )
            if not image_data:
                logger.warning("图片预处理结果为空，将忽略。")
                return None

            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_data.mime_type,
                    "data": image_data.base64_data,
                },
            }

        content = []

        # 1. 用户原始发言（OpenAI 建议：用户发言在前）
        if text:
            content.append({"type": "text", "text": text})
        elif image_urls:
            # 如果没有文本但有图片，添加占位文本
            content.append({"type": "text", "text": "[Image]"})
        elif audio_urls:
            content.append({"type": "text", "text": "[Audio]"})
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
                elif isinstance(block, AudioURLPart):
                    content.append({"type": "text", "text": "[Audio]"})
                else:
                    raise ValueError(f"不支持的额外内容块类型: {type(block)}")

        # 3. 图片内容
        if image_urls:
            for image_url in image_urls:
                image_dict = await resolve_image_url(image_url)
                if image_dict:
                    content.append(image_dict)
        if audio_urls:
            for _audio_path in audio_urls:
                content.append({"type": "text", "text": "[Audio]"})

        # 如果只有主文本且没有额外内容块和图片，返回简单格式以保持向后兼容
        if (
            text
            and not extra_user_content_parts
            and not image_urls
            and not audio_urls
            and len(content) == 1
            and content[0]["type"] == "text"
        ):
            return {"role": "user", "content": content[0]["text"]}

        # 否则返回多模态格式
        return {"role": "user", "content": content}

    async def encode_image_bs64(self, image_url: str) -> tuple[str, str]:
        """将图片转换为 base64，同时检测实际 MIME 类型"""
        image_data = await resolve_media_ref_to_base64_data(
            image_url,
            media_type="image",
            strict=True,
        )
        if image_data is None:
            raise RuntimeError(
                f"Failed to encode image data: {describe_media_ref(image_url)}"
            )
        return image_data.to_data_url(), image_data.mime_type

    def get_current_key(self) -> str:
        return self.chosen_api_key

    async def get_models(self) -> list[str]:
        models_str = []
        models = await retry_provider_request(
            "Anthropic",
            lambda: self.client.models.list(),
        )
        models = sorted(models.data, key=lambda x: x.id)
        for model in models:
            models_str.append(model.id)
        return models_str

    def set_key(self, key: str) -> None:
        self.chosen_api_key = key

    async def terminate(self):
        if self.client:
            await self.client.close()
