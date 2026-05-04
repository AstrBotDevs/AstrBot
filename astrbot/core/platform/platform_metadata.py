from dataclasses import dataclass


@dataclass
class PlatformMetadata:
    name: str
    """平台的名称，即平台的类型，如 aiocqhttp, discord, slack"""
    description: str
    """平台的描述"""
    id: str
    """平台的唯一标识符，用于配置中识别特定平台"""

    default_config_tmpl: dict | None = None
    """平台的默认配置模板"""
    adapter_display_name: str | None = None
    """显示在 WebUI 配置页中的平台名称，如空则是 name"""
    logo_path: str | None = None
    """平台适配器的 logo 文件路径（相对于插件目录）"""

    support_streaming_message: bool = True
    """平台是否支持真实流式传输"""
    support_proactive_message: bool = True
    """平台是否支持主动消息推送（非用户触发）"""

    module_path: str | None = None
    """注册该适配器的模块路径，用于插件热重载时清理"""
    i18n_resources: dict[str, dict] | None = None
    """国际化资源数据，如 {"zh-CN": {...}, "en-US": {...}}

    参考 https://github.com/AstrBotDevs/AstrBot/pull/5045
    """

    config_metadata: dict | None = None
    """配置项元数据，用于 WebUI 生成表单。对应 config_metadata.json 的内容

    参考 https://github.com/AstrBotDevs/AstrBot/pull/5045
    """
