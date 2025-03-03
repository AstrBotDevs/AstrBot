from typing import List, Dict, Type
from .platform_metadata import PlatformMetadata
from astrbot.core import logger

platform_registry: List[PlatformMetadata] = []
"""维护了通过装饰器注册的平台适配器"""
platform_cls_map: Dict[str, Type] = {}
"""维护了平台适配器名称和适配器类的映射"""


def register_platform_adapter(
    adapter_name: str,
    desc: str,
    default_config_tmpl: dict = None,
    adapter_display_name: str = None,
):
    """用于注册平台适配器的带参装饰器。

    default_config_tmpl 指定了平台适配器的默认配置模板。用户填写好后将会作为 platform_config 传入你的 Platform 类的实现类。
    """

    def decorator(cls):
        if adapter_name in platform_cls_map:
            raise ValueError(
                f"平台适配器 {adapter_name} 已经注册过了，可能发生了适配器命名冲突。"
            )

        # 添加必备选项
        if default_config_tmpl:
            if "type" not in default_config_tmpl:
                default_config_tmpl["type"] = adapter_name
            if "enable" not in default_config_tmpl:
                default_config_tmpl["enable"] = False
            if "id" not in default_config_tmpl:
                default_config_tmpl["id"] = adapter_name

        pm = PlatformMetadata(
            name=adapter_name,
            description=desc,
            default_config_tmpl=default_config_tmpl,
            adapter_display_name=adapter_display_name,
        )
        platform_registry.append(pm)
        platform_cls_map[adapter_name] = cls
        logger.debug(f"平台适配器 {adapter_name} 已注册")
        return cls

    return decorator
