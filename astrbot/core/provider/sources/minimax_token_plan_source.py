from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

from ..register import register_provider_adapter

MINIMAX_TOKEN_PLAN_MODELS = [
    "MiniMax-M2.7",
    "MiniMax-M2.5",
    "MiniMax-M2.1",
    "MiniMax-M2",
]


@register_provider_adapter(
    "minimax_token_plan",
    "MiniMax Token Plan 提供商适配器",
    default_config_tmpl={
        "key": "",
        "api_base": "https://api.minimaxi.com/anthropic",
    },
    provider_display_name="MiniMax Token Plan",
)
class ProviderMiniMaxTokenPlan(ProviderAnthropic):
    """MiniMax Token Plan provider.

    Token Plan API 不支持 /models 接口，因此 get_models() 返回硬编码的模型列表。
    这是 Token Plan API 本身的限制，详见 https://github.com/AstrBotDevs/AstrBot/issues/7585
    """

    def __init__(
        self,
        provider_config,
        provider_settings,
    ) -> None:
        # 使用固定的 api_base，不允许用户自定义
        provider_config["api_base"] = "https://api.minimaxi.com/anthropic"
        # 强制使用 auth header（Token Plan 要求）
        provider_config["auth_header"] = True

        super().__init__(
            provider_config,
            provider_settings,
        )

        self.set_model(provider_config.get("model", "MiniMax-M2.7"))

    async def get_models(self) -> list[str]:
        """Token Plan 不支持动态获取模型列表，返回硬编码的已知模型列表。"""
        return MINIMAX_TOKEN_PLAN_MODELS.copy()
