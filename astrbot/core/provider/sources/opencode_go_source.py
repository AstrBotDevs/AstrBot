import hashlib
from collections.abc import AsyncGenerator
from uuid import uuid4

from astrbot import __version__
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.provider import Provider

from ..register import register_provider_adapter
from .anthropic_source import ProviderAnthropic
from .openai_responses_source import ProviderOpenAIResponses
from .openai_source import ProviderOpenAIOfficial

OPENCODE_GO_API_BASE = "https://opencode.ai/zen/go/v1"


@register_provider_adapter(
    "opencode_go_chat_completion", "OpenCode Go Chat Completions Provider Adapter"
)
class ProviderOpenCodeGo(Provider):
    """Send Go requests using the explicitly selected protocol adapter."""

    ADAPTER: type[Provider] = ProviderOpenAIOfficial

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model(provider_config.get("model") or "unknown")
        config = dict(provider_config)
        config["api_base"] = config.get("api_base") or OPENCODE_GO_API_BASE
        config["model"] = self.get_model().removeprefix("opencode-go/")
        headers = config.get("custom_headers") or {}
        config["custom_headers"] = {
            key: value
            for key, value in headers.items()
            if key.lower() not in {"user-agent", "x-opencode-session"}
        }
        config["custom_headers"]["User-Agent"] = f"AstrBot/{__version__}"
        self.delegate = self.ADAPTER(config, provider_settings)

    def get_current_key(self) -> str:
        return self.delegate.get_current_key()

    def get_keys(self) -> list[str]:
        return self.delegate.get_keys()

    def set_key(self, key: str) -> None:
        self.delegate.set_key(key)

    async def get_models(self) -> list[str]:
        return await self.delegate.get_models()

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
        **kwargs,
    ) -> LLMResponse:
        """Send a request using the conversation UUID as the session identity.

        Args:
            prompt: Current user prompt.
            session_id: Deprecated provider argument, forwarded for compatibility.
            image_urls: Images attached to the request.
            audio_urls: Audio attached to the request.
            func_tool: Available function tools.
            contexts: Conversation history.
            system_prompt: System instructions.
            tool_calls_result: Results of previous tool calls.
            model: Optional per-request model override.
            extra_user_content_parts: Additional user content blocks.
            tool_choice: Whether tool use is automatic or required.
            **kwargs: Optional conversation_id (AstrBot conversation UUID) and
                additional arguments forwarded to the protocol adapter.

        Returns:
            The normalized model response.
        """
        model = (model or self.get_model()).removeprefix("opencode-go/")
        delegate = self.delegate
        extra_headers = {
            key: value
            for key, value in (kwargs.pop("extra_headers", None) or {}).items()
            if key.lower() not in {"user-agent", "x-opencode-session"}
        }
        # Calls without a conversation (such as connection tests) are independent.
        extra_headers["x-opencode-session"] = hashlib.sha256(
            (kwargs.pop("conversation_id", None) or uuid4().hex).encode()
        ).hexdigest()
        return await delegate.text_chat(
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
            tool_choice="any"
            if isinstance(delegate, ProviderAnthropic) and tool_choice == "required"
            else tool_choice,
            extra_headers=extra_headers,
            **kwargs,
        )

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
        tool_choice="auto",
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        """Stream a response with the same session identity as non-streaming calls.

        Args:
            prompt: Current user prompt.
            session_id: Deprecated provider argument, forwarded for compatibility.
            image_urls: Images attached to the request.
            audio_urls: Audio attached to the request.
            func_tool: Available function tools.
            contexts: Conversation history.
            system_prompt: System instructions.
            tool_calls_result: Results of previous tool calls.
            model: Optional per-request model override.
            extra_user_content_parts: Additional user content blocks.
            tool_choice: Whether tool use is automatic or required.
            **kwargs: Optional conversation_id (AstrBot conversation UUID) and
                additional arguments forwarded to the protocol adapter.

        Yields:
            Normalized response chunks.
        """
        model = (model or self.get_model()).removeprefix("opencode-go/")
        delegate = self.delegate
        extra_headers = {
            key: value
            for key, value in (kwargs.pop("extra_headers", None) or {}).items()
            if key.lower() not in {"user-agent", "x-opencode-session"}
        }
        extra_headers["x-opencode-session"] = hashlib.sha256(
            (kwargs.pop("conversation_id", None) or uuid4().hex).encode()
        ).hexdigest()
        async for response in delegate.text_chat_stream(
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
            tool_choice="any"
            if isinstance(delegate, ProviderAnthropic) and tool_choice == "required"
            else tool_choice,
            extra_headers=extra_headers,
            **kwargs,
        ):
            yield response

    async def terminate(self) -> None:
        await self.delegate.terminate()


@register_provider_adapter(
    "opencode_go_responses", "OpenCode Go Responses Provider Adapter"
)
class ProviderOpenCodeGoResponses(ProviderOpenCodeGo):
    """Use Go's Responses endpoint for user-selected models."""

    ADAPTER = ProviderOpenAIResponses


@register_provider_adapter(
    "opencode_go_messages", "OpenCode Go Messages Provider Adapter"
)
class ProviderOpenCodeGoMessages(ProviderOpenCodeGo):
    """Use Go's Messages endpoint for user-selected models."""

    ADAPTER = ProviderAnthropic
