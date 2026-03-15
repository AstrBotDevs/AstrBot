"""Minimax API Provider Adapter

MiniMax API 兼容 OpenAI API 格式
文档: https://platform.minimaxi.com/docs/api-reference/api-overview
"""

import httpx
from astrbot import logger

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "minimax_chat_completion",
    "MiniMax Chat Completion Provider Adapter",
    default_config_tmpl={
        "type": "minimax_chat_completion",
        "enable": False,
        "id": "minimax",
        "key": ["your-minimax-api-key"],
        "api_base": "https://api.minimaxi.com/v1",
        "model": "MiniMax-M2.5",
        "timeout": 120,
        "proxy": "",
        "custom_headers": {},
    },
    provider_display_name="MiniMax",
)
class ProviderMiniMax(ProviderOpenAIOfficial):
    """MiniMax 提供商适配器
    
    支持的模型:
    - MiniMax-M2.5: 顶尖性能与极致性价比，轻松驾驭复杂任务 (输出速度约60tps)
    - MiniMax-M2.5-highspeed: M2.5 极速版，效果不变，更快更敏捷 (输出速度约100tps)
    - MiniMax-M2.1: 强大多语言编程能力，全面升级编程体验 (输出速度约60tps)
    - MiniMax-M2.1-highspeed: M2.1 极速版，效果不变，更快更敏捷 (输出速度约100tps)
    - MiniMax-M2: 专为高效编码与Agent工作流而生
    
    API 文档: https://platform.minimaxi.com/docs/api-reference/chat-completion
    """

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
    
    def _create_http_client(self, provider_config: dict) -> httpx.AsyncClient | None:
        """创建带代理的 HTTP 客户端，重载以处理空代理字符串"""
        proxy = provider_config.get("proxy", "")
        # 确保空字符串被当作无代理处理
        if not proxy or proxy.strip() == "":
            return None
        logger.info(f"[MiniMax] 使用代理: {proxy}")
        return httpx.AsyncClient(proxy=proxy)
    
    async def get_models(self) -> list[str]:
        """返回 MiniMax 支持的模型列表
        
        MiniMax API 不支持获取模型列表，所以返回固定列表
        上下文长度均为 204800 tokens
        """
        return [
            "MiniMax-M2.5",              # 顶尖性能与极致性价比（默认）
            "MiniMax-M2.5-highspeed",    # M2.5 极速版
            "MiniMax-M2.1",              # 强大多语言编程能力
            "MiniMax-M2.1-highspeed",    # M2.1 极速版
            "MiniMax-M2",                # 专为高效编码与Agent工作流而生
        ]
