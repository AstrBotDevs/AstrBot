"""Provider-neutral contracts used by the local agent runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core.agent.message import (
    AssistantMessageSegment,
    ContentPart,
    ProviderMessageState,
    ToolCall,
    ToolCallMessageSegment,
    is_checkpoint_message,
)
from astrbot.core.agent.tool import ToolSet
from astrbot.core.db.po import Conversation
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.media_utils import MediaResolver


@dataclass(frozen=True, slots=True)
class ProviderContentBlock:
    """Provider-neutral, prepared user-media content.

    The transport-facing provider adapters remain responsible for mapping these
    blocks to their own payloads.  A block never contains an unvalidated remote
    URL: media preparation materializes accepted local/data references first.
    """

    type: Literal["text", "image", "audio", "video", "file"]
    value: str
    mime_type: str | None = None


@dataclass
class ToolCallsResult:
    """A function-call request and its result messages."""

    tool_calls_info: AssistantMessageSegment
    """The function-call request message."""
    tool_calls_result: list[ToolCallMessageSegment]
    """The function-call result messages."""

    def to_messages(self) -> list[dict]:
        ret = [
            self.tool_calls_info.model_dump(),
            *[item.model_dump() for item in self.tool_calls_result],
        ]
        return ret

    def to_message_models(
        self,
    ) -> list[AssistantMessageSegment | ToolCallMessageSegment]:
        return [
            self.tool_calls_info,
            *self.tool_calls_result,
        ]


@dataclass
class ProviderRequest:
    prompt: str | None = None
    """The prompt."""
    session_id: str | None = ""
    """The session ID."""
    image_urls: list[str] = field(default_factory=list)
    """Image URLs."""
    audio_urls: list[str] = field(default_factory=list)
    """Audio URLs or local paths."""
    extra_user_content_parts: list[ContentPart] = field(default_factory=list)
    """Additional user content parts appended after the prompt."""
    message_component_context: str = ""
    """Rendered non-plain current-message context for prompt-only runners."""
    func_tool: ToolSet | None = None
    """Available function tools."""
    contexts: list[dict] = field(default_factory=list)
    """Protocol-neutral conversation history for provider adapters to map."""
    system_prompt: str = ""
    """The system prompt."""
    conversation: Conversation | None = None
    """The related conversation."""
    tool_calls_result: list[ToolCallsResult] | ToolCallsResult | None = None
    """Function-call results from the previous request."""
    model: str | None = None
    """The model name; use the provider default when unset."""
    _attachments_prepared: bool = field(default=False, repr=False, compare=False)
    """Runtime-only marker for idempotent event attachment preparation."""
    tool_history_mode: str = "full"
    tool_history_placeholder: str = ""
    prepared_content: tuple[ProviderContentBlock, ...] = field(default_factory=tuple)
    """Prepared provider-neutral content retained for inspection and adapters."""

    def __repr__(self) -> str:
        return (
            f"ProviderRequest(prompt={self.prompt}, session_id={self.session_id}, "
            f"image_count={len(self.image_urls or [])}, "
            f"audio_count={len(self.audio_urls or [])}, "
            f"func_tool={self.func_tool}, "
            f"contexts={self._print_friendly_context()}, "
            f"system_prompt={self.system_prompt}, "
            f"conversation_id={self.conversation.cid if self.conversation else 'N/A'}, "
        )

    def __str__(self) -> str:
        return self.__repr__()

    def append_tool_calls_result(self, tool_calls_result: ToolCallsResult) -> None:
        """Append a tool-call result to this request."""
        if not self.tool_calls_result:
            self.tool_calls_result = []
        if isinstance(self.tool_calls_result, ToolCallsResult):
            self.tool_calls_result = [self.tool_calls_result]
        self.tool_calls_result.append(tool_calls_result)

    def _print_friendly_context(self) -> str:
        """Render message context with multimodal content collapsed to markers."""
        if not self.contexts:
            return (
                f"prompt: {self.prompt}, image_count: {len(self.image_urls or [])}, "
                f"audio_count: {len(self.audio_urls or [])}"
            )

        result_parts = []

        for ctx in self.contexts:
            if is_checkpoint_message(ctx):
                continue
            role = ctx.get("role", "unknown")
            content = ctx.get("content", "")

            if isinstance(content, str):
                result_parts.append(f"{role}: {content}")
            elif isinstance(content, list):
                msg_parts = []
                image_count = 0
                audio_count = 0

                for item in content:
                    item_type = item.get("type", "")

                    if item_type == "text":
                        msg_parts.append(item.get("text", ""))
                    elif item_type == "image_url":
                        image_count += 1
                    elif item_type == "audio_url":
                        audio_count += 1

                if image_count > 0:
                    if msg_parts:
                        msg_parts.append(f"[+{image_count} images]")
                    else:
                        msg_parts.append(f"[{image_count} images]")
                if audio_count > 0:
                    if msg_parts:
                        msg_parts.append(f"[+{audio_count} audios]")
                    else:
                        msg_parts.append(f"[{audio_count} audios]")

                result_parts.append(f"{role}: {''.join(msg_parts)}")

        return "\n".join(result_parts)

    async def assemble_context(self) -> dict:
        """Build the neutral user message representation for this request."""
        content_blocks = []

        if self.prompt and self.prompt.strip():
            content_blocks.append({"type": "text", "text": self.prompt})
        elif self.image_urls:
            content_blocks.append({"type": "text", "text": "[图片]"})
        elif self.audio_urls:
            content_blocks.append({"type": "text", "text": "[音频]"})

        if self.extra_user_content_parts:
            for part in self.extra_user_content_parts:
                content_blocks.append(part.model_dump_for_context())

        if self.image_urls:
            for image_url in self.image_urls:
                image_data = await MediaResolver(
                    image_url,
                    media_type="image",
                ).to_base64_data()
                if not image_data:
                    logger.warning("图片预处理结果为空，将忽略。")
                    continue
                content_blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data.to_data_url()},
                    },
                )

        if self.audio_urls:
            for audio_url in self.audio_urls:
                try:
                    audio_data = await MediaResolver(
                        audio_url,
                        media_type="audio",
                        default_suffix=".wav",
                    ).to_base64_data(
                        strict=True,
                        target_format="wav",
                    )
                except Exception as exc:
                    logger.warning("音频预处理失败，将忽略。错误: %s", exc)
                    continue
                if not audio_data:
                    logger.warning("音频预处理结果为空，将忽略。")
                    continue
                content_blocks.append(
                    {
                        "type": "audio_url",
                        "audio_url": {"url": audio_data.to_data_url()},
                    },
                )

        if (
            len(content_blocks) == 1
            and content_blocks[0]["type"] == "text"
            and not self.extra_user_content_parts
            and not self.image_urls
            and not self.audio_urls
        ):
            return {"role": "user", "content": content_blocks[0]["text"]}

        return {"role": "user", "content": content_blocks}


@dataclass
class TokenUsage:
    input_other: int = 0
    """The number of input tokens excluding cached tokens."""
    input_cached: int = 0
    """The number of cached input tokens."""
    output: int = 0
    """The number of output tokens."""

    @property
    def total(self) -> int:
        return self.input_other + self.input_cached + self.output

    @property
    def input(self) -> int:
        return self.input_other + self.input_cached

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_other=self.input_other + other.input_other,
            input_cached=self.input_cached + other.input_cached,
            output=self.output + other.output,
        )

    def __sub__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_other=self.input_other - other.input_other,
            input_cached=self.input_cached - other.input_cached,
            output=self.output - other.output,
        )


@dataclass
class LLMResponse:
    role: str
    """The message role, for example assistant, tool, or err."""
    result_chain: MessageChain | None = None
    """A message-component chain representing the LLM completion."""
    tools_call_args: list[dict[str, Any]] = field(default_factory=list)
    """Tool call arguments."""
    tools_call_name: list[str] = field(default_factory=list)
    """Tool call names."""
    tools_call_ids: list[str] = field(default_factory=list)
    """Tool call IDs."""
    tools_call_extra_content: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Per-tool-call extra content."""
    reasoning_content: str | None = None
    """Reasoning content extracted from the LLM, if present."""
    reasoning_signature: str | None = None
    """The reasoning signature, if present."""
    raw_completion: object | None = None
    """The provider-specific raw completion response."""
    _completion_text: str | None = ""
    """The plain completion text."""
    is_chunk: bool = False
    """Whether this is a streamed chunk."""
    id: str | None = None
    """The response or chunk ID."""
    usage: TokenUsage | None = None
    """The completion's token usage."""
    provider_state: ProviderMessageState | None = None
    finish_reason: str | None = None
    incomplete_details: dict[str, Any] | None = None
    provider_error: dict[str, Any] | None = None
    refusal: str | None = None
    citations: list[LLMCitation] = field(default_factory=list)
    sources: list[LLMSource] = field(default_factory=list)

    def __init__(
        self,
        role: str,
        completion_text: str | None = None,
        result_chain: MessageChain | None = None,
        tools_call_args: list[dict[str, Any]] | None = None,
        tools_call_name: list[str] | None = None,
        tools_call_ids: list[str] | None = None,
        tools_call_extra_content: dict[str, dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
        reasoning_signature: str | None = None,
        raw_completion: object | None = None,
        is_chunk: bool = False,
        id: str | None = None,
        usage: TokenUsage | None = None,
        provider_state: ProviderMessageState | None = None,
        finish_reason: str | None = None,
        incomplete_details: dict[str, Any] | None = None,
        provider_error: dict[str, Any] | None = None,
        refusal: str | None = None,
        citations: list[LLMCitation] | None = None,
        sources: list[LLMSource] | None = None,
    ) -> None:
        """Initialize a provider-neutral LLM completion."""
        if tools_call_args is None:
            tools_call_args = []
        if tools_call_name is None:
            tools_call_name = []
        if tools_call_ids is None:
            tools_call_ids = []
        if tools_call_extra_content is None:
            tools_call_extra_content = {}

        self.role = role
        self.result_chain = result_chain
        # A response chain is authoritative when no explicit text was supplied.
        # Assign it before routing explicit text through the property so the text
        # is reflected in the chain rather than being lost in `_completion_text`.
        if completion_text is None:
            self._completion_text = None
        else:
            self.completion_text = completion_text
        self.tools_call_args = tools_call_args
        self.tools_call_name = tools_call_name
        self.tools_call_ids = tools_call_ids
        self.tools_call_extra_content = tools_call_extra_content
        self.reasoning_content = reasoning_content
        self.reasoning_signature = reasoning_signature
        self.raw_completion = raw_completion
        self.is_chunk = is_chunk

        if id is not None:
            self.id = id
        if usage is not None:
            self.usage = usage
        self.provider_state = provider_state
        self.finish_reason = finish_reason
        self.incomplete_details = incomplete_details
        self.provider_error = provider_error
        self.refusal = refusal
        self.citations = citations or []
        self.sources = sources or []

    @property
    def completion_text(self) -> str | None:
        if self.result_chain:
            return self.result_chain.get_plain_text()
        return self._completion_text

    @completion_text.setter
    def completion_text(self, value: str | None) -> None:
        if self.result_chain:
            self.result_chain.chain = [
                comp
                for comp in self.result_chain.chain
                if not isinstance(comp, Comp.Plain)
            ]
            if value is not None:
                self.result_chain.chain.insert(0, Comp.Plain(value))
        else:
            self._completion_text = value

    def to_function_tool_calls_model(self) -> list[ToolCall]:
        """Return the internal function-call message models."""
        if not (
            len(self.tools_call_args)
            == len(self.tools_call_name)
            == len(self.tools_call_ids)
        ):
            raise ValueError("Function tool call fields have mismatched lengths.")
        ret = []
        for idx, tool_call_arg in enumerate(self.tools_call_args):
            ret.append(
                ToolCall(
                    id=self.tools_call_ids[idx],
                    function=ToolCall.FunctionBody(
                        name=self.tools_call_name[idx],
                        arguments=json.dumps(tool_call_arg),
                    ),
                    extra_content=self.tools_call_extra_content.get(
                        self.tools_call_ids[idx]
                    ),
                ),
            )
        return ret


@dataclass
class LLMSource:
    url: str
    title: str | None = None
    snippet: str | None = None
    source_type: str | None = None


@dataclass
class LLMCitation:
    url: str
    title: str | None = None
    start_index: int | None = None
    end_index: int | None = None
