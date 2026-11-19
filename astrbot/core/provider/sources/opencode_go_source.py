import hashlib
from collections.abc import AsyncGenerator
from typing import Literal
from uuid import uuid4

from astrbot import __version__
from astrbot.api.provider import Provider
from astrbot.core.agent.message import ContentPart, Message
from astrbot.core.agent.tool import ToolSet
from astrbot.core.provider.entities import LLMResponse, ToolCallsResult

from ..register import register_provider_adapter
from .openai_responses_source import ProviderOpenAIResponses
from .openai_source import ProviderOpenAIOfficial

OPENCODE_GO_API_BASE = "https://opencode.ai/zen/go/v1"
OPENCODE_GO_MODEL_PREFIX = "opencode-go/"
OPENCODE_GO_DEFAULT_MODEL = "kimi-k2.6"
OPENCODE_GO_RESPONSES_MODELS = {
    "gpt-5.6-luna",
    "grok-4.6",
    "muse-spark-1.2-contributor",
    "muse-spark-1.3-contributor",
}
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
    RESPONSES_MODELS = OPENCODE_GO_RESPONSES_MODELS
    RESPONSES_MODEL_PREFIXES: tuple[str, ...] = ()
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
        self._fallback_session_id = uuid4().hex

        uses_responses = model in self.RESPONSES_MODELS or model.startswith(
            self.RESPONSES_MODEL_PREFIXES
        )
        delegate_class = (
            ProviderOpenAIResponses if uses_responses else ProviderOpenAIOfficial
        )
        self.openai_provider = delegate_class(
            self._build_delegate_config(model=model),
            provider_settings,
        )

    def _build_delegate_config(self, *, model: str) -> dict:
        config = dict(self.provider_config)
        config["api_base"] = self.api_base
        config["model"] = model
        custom_headers = config.get("custom_headers")
        custom_headers = (
            dict(custom_headers) if isinstance(custom_headers, dict) else {}
        )
        custom_headers.setdefault("User-Agent", f"AstrBot-Coding-Agent/{__version__}")
        config["custom_headers"] = custom_headers
        return config

    @classmethod
    def _to_api_model(cls, model: str | None) -> str:
        resolved_model = (model or cls.DEFAULT_MODEL).strip()
        if resolved_model.startswith(cls.MODEL_PREFIX):
            return resolved_model.removeprefix(cls.MODEL_PREFIX)
        return resolved_model

    @classmethod
    def _to_provider_model(cls, model: str) -> str:
        return f"{cls.MODEL_PREFIX}{cls._to_api_model(model)}"

    @classmethod
    def _unsupported_endpoint(cls, api_model: str) -> str | None:
        if endpoint := cls.UNSUPPORTED_MODEL_ENDPOINTS.get(api_model):
            return endpoint
        for prefix, endpoint in cls.UNSUPPORTED_MODEL_PREFIX_ENDPOINTS:
            if api_model.startswith(prefix):
                return endpoint
        return None

    @classmethod
    def _ensure_supported_model(cls, model: str | None) -> str:
        api_model = cls._to_api_model(model)
        if endpoint := cls._unsupported_endpoint(api_model):
            raise ValueError(
                f"{cls.PROVIDER_NAME} model {cls.MODEL_PREFIX}{api_model} uses "
                f"unsupported endpoint {endpoint}."
            )
        return api_model

    def _resolve_model(self, model: str | None = None) -> str:
        return self._ensure_supported_model(model or self.get_model())

    def get_current_key(self) -> str:
        return self.openai_provider.get_current_key()

    def get_keys(self) -> list[str]:
        return self.openai_provider.get_keys()

    def set_key(self, key: str) -> None:
        self.openai_provider.set_key(key)

    async def get_models(self) -> list[str]:
        models = await self.openai_provider.get_models()
        api_models = []
        for model in models:
            api_model = self._to_api_model(model)
            if api_model and not self._unsupported_endpoint(api_model):
                api_models.append(api_model)
        return sorted(api_models)

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
        extra_headers = dict(kwargs.pop("extra_headers", {}) or {})
        extra_headers["x-opencode-session"] = hashlib.sha256(
            str(session_id or self._fallback_session_id).encode()
        ).hexdigest()
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
            extra_headers=extra_headers,
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
        extra_headers = dict(kwargs.pop("extra_headers", {}) or {})
        extra_headers["x-opencode-session"] = hashlib.sha256(
            str(session_id or self._fallback_session_id).encode()
        ).hexdigest()
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
            extra_headers=extra_headers,
            **kwargs,
        ):
            yield response

    async def terminate(self) -> None:
        await self.openai_provider.terminate()
