from collections.abc import AsyncGenerator

from anthropic import AsyncAnthropic

from astrbot.core.provider.entities import LLMResponse

from ..register import register_provider_adapter
from .anthropic_source import ProviderAnthropic

_OAUTH_DEFAULT_HEADERS = {
    "anthropic-beta": "claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07",
    "user-agent": "claude-cli/1.0.0 (external, cli)",
    "x-app": "cli",
    "anthropic-dangerous-direct-browser-access": "true",
}

_CLAUDE_CODE_SYSTEM_PREFIX = (
    "You are Claude Code, Anthropic's official CLI for Claude.\n\n"
)

# 支持 1M 上下文窗口的模型前缀（需配合 context-1m beta header）。
# 新增 4.6+ 模型时需同步更新此列表。
_1M_CONTEXT_MODEL_PREFIXES = (
    "claude-opus-4-6",
    "claude-sonnet-4-6",
)


@register_provider_adapter(
    "anthropic_oauth",
    "Anthropic Claude Code OAuth provider adapter",
)
class ProviderAnthropicOAuth(ProviderAnthropic):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        # 禁用父类的 API key 客户端初始化，避免重复构造客户端
        super().__init__(provider_config, provider_settings, use_api_key=False)

        # 手动解析 key 列表（父类跳过了 _init_api_key）
        self.api_keys: list = self.get_keys()
        self.chosen_api_key: str = self.api_keys[0] if self.api_keys else ""

        # 使用 auth_token（OAuth Bearer 认证）构建客户端
        self.client = AsyncAnthropic(
            auth_token=self.chosen_api_key,
            timeout=self.timeout,
            base_url=self.base_url,
            default_headers=_OAUTH_DEFAULT_HEADERS,
            http_client=self._create_http_client(provider_config),
        )

    def set_model(self, model_name: str) -> None:
        super().set_model(model_name)
        if any(model_name.startswith(p) for p in _1M_CONTEXT_MODEL_PREFIXES):
            if self.provider_config.get("max_context_tokens", 0) <= 0:
                self.provider_config["max_context_tokens"] = 1_000_000

    def get_model_metadata_overrides(self, model_ids: list[str]) -> dict[str, dict]:
        overrides = {}
        for mid in model_ids:
            if any(mid.startswith(p) for p in _1M_CONTEXT_MODEL_PREFIXES):
                overrides[mid] = {"limit": {"context": 1_000_000}}
        return overrides

    def set_key(self, key: str) -> None:
        self.chosen_api_key = key
        # 切换 key 时需要重建客户端以使用新的 auth_token
        self.client = AsyncAnthropic(
            auth_token=key,
            timeout=self.timeout,
            base_url=self.base_url,
            default_headers=_OAUTH_DEFAULT_HEADERS,
            http_client=self._create_http_client(self.provider_config),
        )

    async def get_models(self) -> list[str]:
        return await super().get_models()

    async def test(self, timeout: float = 45.0) -> None:
        await super().test(timeout)

    async def text_chat(
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
    ) -> LLMResponse:
        system_prompt = _CLAUDE_CODE_SYSTEM_PREFIX + (system_prompt or "")

        return await super().text_chat(
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
        system_prompt = _CLAUDE_CODE_SYSTEM_PREFIX + (system_prompt or "")

        async for llm_response in super().text_chat_stream(
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
        ):
            yield llm_response
