from typing import List, Dict
from .entities import ProviderMetaData, ProviderType
from astrbot.core import logger
from .func_tool_manager import FuncCall

provider_registry: List[ProviderMetaData] = []
"""维护了通过装饰器注册的 Provider"""
provider_cls_map: Dict[str, ProviderMetaData] = {}
"""维护了 Provider 类型名称和 ProviderMetadata 的映射"""

llm_tools = FuncCall()


def register_provider_adapter(
    provider_type_name: str,
    desc: str,
    provider_type: ProviderType = ProviderType.CHAT_COMPLETION,
    default_config_tmpl: dict = None,
    provider_display_name: str = None,
):
    """用于注册平台适配器的带参装饰器"""

    def decorator(cls):
        if provider_type_name in provider_cls_map:
            raise ValueError(
                f"检测到大模型提供商适配器 {provider_type_name} 已经注册，可能发生了大模型提供商适配器类型命名冲突。"
            )

        # 添加必备选项
        if default_config_tmpl:
            if "type" not in default_config_tmpl:
                default_config_tmpl["type"] = provider_type_name
            if "enable" not in default_config_tmpl:
                default_config_tmpl["enable"] = False
            if "id" not in default_config_tmpl:
                default_config_tmpl["id"] = provider_type_name

        pm = ProviderMetaData(
            type=provider_type_name,
            desc=desc,
            provider_type=provider_type,
            cls_type=cls,
            default_config_tmpl=default_config_tmpl,
            provider_display_name=provider_display_name,
        )
        provider_registry.append(pm)
        provider_cls_map[provider_type_name] = pm
        logger.debug(f"服务提供商 Provider {provider_type_name} 已注册")
        return cls

    return decorator
