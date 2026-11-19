from functools import wraps

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
    i18n_resources: dict[str, dict] | None = None,
    config_metadata: dict | None = None,
    support_ui_interaction: bool = False,
):
    """Register a platform adapter and its metadata.

    Args:
        adapter_name: Unique platform type name.
        desc: Adapter description.
        default_config_tmpl: Default configuration passed to adapter instances.
        adapter_display_name: Name shown in dashboard configuration.
        logo_path: Logo path relative to the plugin directory.
        support_streaming_message: Whether the adapter supports true streaming.
        i18n_resources: Localized adapter resources.
        config_metadata: Schema used to render dashboard configuration fields.
        support_ui_interaction: Whether the adapter supports UI views and their
            interaction callbacks. Event metadata must declare it too.

    Returns:
        A decorator that registers and returns the adapter class.
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
        support_proxy = bool(getattr(cls, "supports_proxy", False))

        # Adapter implementations often create fresh metadata instances in
        # meta(), so keep the registered capability visible at runtime too.
        original_meta = cls.meta

        @wraps(original_meta)
        def meta_with_capabilities(self, *args, **kwargs):
            metadata = original_meta(self, *args, **kwargs)
            if isinstance(metadata, PlatformMetadata):
                metadata.support_proxy = support_proxy
            return metadata

        cls.meta = meta_with_capabilities

        pm = PlatformMetadata(
            name=adapter_name,
            description=desc,
            id=adapter_name,
            default_config_tmpl=default_config_tmpl,
            adapter_display_name=adapter_display_name,
            logo_path=logo_path,
            support_streaming_message=support_streaming_message,
            support_proxy=support_proxy,
            module_path=module_path,
            i18n_resources=i18n_resources,
            config_metadata=config_metadata,
            support_ui_interaction=support_ui_interaction,
        )
        platform_registry.append(pm)
        platform_cls_map[adapter_name] = cls
        logger.debug("Platform adapter registered: %s", adapter_name)
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
