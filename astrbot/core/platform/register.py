from astrbot.core import logger

from .platform_metadata import PlatformMetadata

platform_registry: list[PlatformMetadata] = []
"""维护了通过装饰器注册的平台适配器"""
platform_cls_map: dict[str, type] = {}
"""维护了平台适配器名称和适配器类的映射"""


def register_platform_adapter(
    adapter_name: str,
    desc: str,
    default_config_tmpl: dict | None = None,
    adapter_display_name: str | None = None,
    logo_path: str | None = None,
    support_streaming_message: bool = True,
):
    """用于注册平台适配器的带参装饰器。

    default_config_tmpl 指定了平台适配器的默认配置模板。用户填写好后将会作为 platform_config 传入你的 Platform 类的实现类。
    logo_path 指定了平台适配器的 logo 文件路径，是相对于插件目录的路径。
    """

    def decorator(cls):
        if adapter_name in platform_cls_map:
            raise ValueError(
                f"平台适配器 {adapter_name} 已经注册过了，可能发生了适配器命名冲突。",
            )

        # 添加必备选项
        if default_config_tmpl:
            if "type" not in default_config_tmpl:
                default_config_tmpl["type"] = adapter_name
            if "enable" not in default_config_tmpl:
                default_config_tmpl["enable"] = False
            if "id" not in default_config_tmpl:
                default_config_tmpl["id"] = adapter_name

        # Get the module path of the class being decorated
        module_path = cls.__module__

        pm = PlatformMetadata(
            name=adapter_name,
            description=desc,
            id=adapter_name,
            default_config_tmpl=default_config_tmpl,
            adapter_display_name=adapter_display_name,
            logo_path=logo_path,
            support_streaming_message=support_streaming_message,
            module_path=module_path,
        )
        platform_registry.append(pm)
        platform_cls_map[adapter_name] = cls
        logger.debug(f"平台适配器 {adapter_name} 已注册")
        return cls

    return decorator


def unregister_platform_adapters_by_module(module_path_prefix: str) -> list[str]:
    """根据模块路径前缀注销平台适配器。

    在插件热重载时调用，用于清理该插件注册的所有平台适配器。

    Args:
        module_path_prefix: 模块路径前缀，如 "data.plugins.my_plugin"

    Returns:
        被注销的平台适配器名称列表
    """
    unregistered = []
    to_remove = []

    for pm in platform_registry:
        if pm.module_path and pm.module_path.startswith(module_path_prefix):
            to_remove.append(pm)
            unregistered.append(pm.name)

    for pm in to_remove:
        platform_registry.remove(pm)
        if pm.name in platform_cls_map:
            del platform_cls_map[pm.name]
        logger.debug(f"平台适配器 {pm.name} 已注销 (来自模块 {pm.module_path})")

    return unregistered
