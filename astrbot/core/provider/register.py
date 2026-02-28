from astrbot.core.lang import t
from astrbot.core import logger

from .entities import ProviderMetaData, ProviderType
from .func_tool_manager import FuncCall

provider_registry: list[ProviderMetaData] = []
"""维护了通过装饰器注册的 Provider"""
provider_cls_map: dict[str, ProviderMetaData] = {}
"""维护了 Provider 类型名称和 ProviderMetadata 的映射"""

llm_tools = FuncCall()


def register_provider_adapter(
    provider_type_name: str,
    desc: str,
    provider_type: ProviderType = ProviderType.CHAT_COMPLETION,
    default_config_tmpl: dict | None = None,
    provider_display_name: str | None = None,
):
    """用于注册平台适配器的带参装饰器"""

    def decorator(cls):
        if provider_type_name in provider_cls_map:
            raise ValueError(
                t("msg-19ddffc0", provider_type_name=provider_type_name),
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
            id="default",  # will be replaced when instantiated
            model=None,
            type=provider_type_name,
            desc=desc,
            provider_type=provider_type,
            cls_type=cls,
            default_config_tmpl=default_config_tmpl,
            provider_display_name=provider_display_name,
        )
        provider_registry.append(pm)
        provider_cls_map[provider_type_name] = pm
        logger.debug(t("msg-7e134b0d", provider_type_name=provider_type_name))
        return cls

    return decorator
