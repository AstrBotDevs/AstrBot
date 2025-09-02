from dataclasses import dataclass


@dataclass
class PlatformMetadata:
    name: str
    """平台的名称"""
    description: str
    """平台的描述"""
    id: str = None
    """平台的唯一标识符，用于配置中识别特定平台"""

    default_config_tmpl: dict = None
    """平台的默认配置模板"""
    adapter_display_name: str = None
    """显示在 WebUI 配置页中的平台名称，如空则是 name"""
