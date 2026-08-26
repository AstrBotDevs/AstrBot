from collections.abc import AsyncGenerator
from typing import Literal

from astrbot.api.provider import Provider
from astrbot.core.agent.message import ContentPart, Message
from astrbot.core.agent.tool import ToolSet
from astrbot.core.provider.entities import LLMResponse, ToolCallsResult

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial

OPENCODE_GO_API_BASE = "https://opencode.ai/zen/go/v1"
OPENCODE_GO_MODEL_PREFIX = "opencode-go/"
OPENCODE_GO_DEFAULT_MODEL = "kimi-k2.6"
OPENCODE_GO_MESSAGES_ONLY_MODELS = {"minimax-m2.5", "minimax-m2.7"}


@register_provider_adapter(
    "opencode_go_chat_completion",
    "OpenCode Go Subscription Provider Adapter",
)
class ProviderOpenCodeGo(Provider):
    API_BASE = OPENCODE_GO_API_BASE
    MODEL_PREFIX = OPENCODE_GO_MODEL_PREFIX
    DEFAULT_MODEL = OPENCODE_GO_DEFAULT_MODEL
    PROVIDER_NAME = "OpenCode Go"
    UNSUPPORTED_MODEL_ENDPOINTS = dict.fromkeys(
        OPENCODE_GO_MESSAGES_ONLY_MODELS, "/v1/messages"
    )
    UNSUPPORTED_MODEL_PREFIX_ENDPOINTS: tuple[tuple[str, str], ...] = ()

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_base = provider_config.get("api_base", self.API_BASE).rstrip("/")
        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)

        model = self._to_api_model(provider_config.get("model", self.DEFAULT_MODEL))
        self.set_model(model)

        self.openai_provider = ProviderOpenAIOfficial(
            self._build_delegate_config(model=model),
            provider_settings,
        )

    def _build_delegate_config(self, *, model: str) -> dict:
        config = dict(self.provider_config)
        config["api_base"] = self.api_base
        config["model"] = model
        config.setdefault("force_tool_call_reasoning_content", True)
        return config

    @classmethod
    def _to_api_model(cls, model: str | None) -> str:
        resolved_model = (model or cls.DEFAULT_MODEL).strip()
        if resolved_model.startswith(cls.MODEL_PREFIX):
            return resolved_model.removeprefix(cls.MODEL_PREFIX)
        return resolved_model

    @classmethod
    def _to_provider_model(cls, model: str) -> str:
        api_model = cls._to_api_model(model)
        return f"{cls.MODEL_PREFIX}{api_model}"

    @classmethod
    def _unsupported_endpoint(cls, api_model: str) -> str | None:
        if endpoint := cls.UNSUPPORTED_MODEL_ENDPOINTS.get(api_model):
            return endpoint
        for prefix, endpoint in cls.UNSUPPORTED_MODEL_PREFIX_ENDPOINTS:
            if api_model.startswith(prefix):
                return endpoint
        return None

    @classmethod
    def _ensure_chat_completions_model(cls, model: str | None) -> str:
        api_model = cls._to_api_model(model)
        if endpoint := cls._unsupported_endpoint(api_model):
            raise ValueError(
                f"{cls.PROVIDER_NAME} model {cls.MODEL_PREFIX}{api_model} uses "
                f"{endpoint}. This adapter currently supports "
                "/v1/chat/completions models only."
            )
        return api_model

    def _resolve_model(self, model: str | None = None) -> str:
        return self._ensure_chat_completions_model(model or self.get_model())

    def get_current_key(self) -> str:
        return self.openai_provider.get_current_key()

    def get_keys(self) -> list[str]:
        return self.openai_provider.get_keys()

    def set_key(self, key: str) -> None:
        self.openai_provider.set_key(key)

    async def get_models(self) -> list[str]:
        models = await self.openai_provider.get_models()
        provider_models: list[str] = []
        for model in models:
            api_model = self._to_api_model(model)
            if not api_model or self._unsupported_endpoint(api_model):
                continue
            provider_models.append(f"{self.MODEL_PREFIX}{api_model}")
        return sorted(provider_models)

    async def text_chat(
        self,
        prompt: str | None = None,
        session_id: str | None = None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        func_tool: ToolSet | None = None,
        contexts: list[Message] | list[dict] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None = None,
        model: str | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
        tool_choice: Literal["auto", "required"] = "auto",
        **kwargs,
    ) -> LLMResponse:
        return await self.openai_provider.text_chat(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls,
            audio_urls=audio_urls,
            func_tool=func_tool,
            contexts=contexts,
            system_prompt=system_prompt,
            tool_calls_result=tool_calls_result,
            model=self._resolve_model(model),
            extra_user_content_parts=extra_user_content_parts,
            tool_choice=tool_choice,
            **kwargs,
        )

    async def text_chat_stream(
        self,
        prompt: str | None = None,
        session_id: str | None = None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        func_tool: ToolSet | None = None,
        contexts: list[Message] | list[dict] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None = None,
        model: str | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
        tool_choice: Literal["auto", "required"] = "auto",
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        async for response in self.openai_provider.text_chat_stream(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls,
            audio_urls=audio_urls,
            func_tool=func_tool,
            contexts=contexts,
            system_prompt=system_prompt,
            tool_calls_result=tool_calls_result,
            model=self._resolve_model(model),
            extra_user_content_parts=extra_user_content_parts,
            tool_choice=tool_choice,
            **kwargs,
        ):
            yield response

    async def terminate(self) -> None:
        await self.openai_provider.terminate()
