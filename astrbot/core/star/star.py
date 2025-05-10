from __future__ import annotations

from types import ModuleType
from typing import List, Dict
from dataclasses import dataclass, field
from astrbot.core.config import AstrBotConfig
from astrbot.core import logger

star_registry: List[StarMetadata] = []
star_map: Dict[str, StarMetadata] = {}
"""key 是模块路径，__module__"""


@dataclass
class StarMetadata:
    """
    插件的元数据。

    当 activated 为 False 时，star_cls 可能为 None，请不要在插件未激活时调用 star_cls 的方法。
    """

    name: str
    author: str  # 插件作者
    desc: str  # 插件简介
    version: str  # 插件版本
    repo: str = None  # 插件仓库地址

    star_cls_type: type = None
    """插件的类对象的类型"""
    module_path: str = None
    """插件的模块路径"""

    star_cls: object = None
    """插件的类对象"""
    module: ModuleType = None
    """插件的模块对象"""
    root_dir_name: str = None
    """插件的目录名称"""
    reserved: bool = False
    """是否是 AstrBot 的保留插件"""

    activated: bool = True
    """是否被激活"""

    config: AstrBotConfig = None
    """插件配置"""

    star_handler_full_names: List[str] = field(default_factory=list)
    """注册的 Handler 的全名列表"""

    supported_platforms: Dict[str, bool] = field(default_factory=dict)
    """插件支持的平台ID字典，key为平台ID，value为是否支持"""

    group_permissions: Dict[str, bool] = field(default_factory=dict)
    """插件在群聊中的权限缓存，key为群聊ID，value为插件是否启用"""

    def __str__(self) -> str:
        return f"StarMetadata({self.name}, {self.desc}, {self.version}, {self.repo})"

    def update_plugin_compatibility(self, plugin_enable_config: dict) -> None:
        """更新插件支持的平台列表

        Args:
            plugin_enable_config: 平台插件启用配置，即platform_settings.plugin_enable配置项
        """
        self.update_platform_config(plugin_enable_config)
        self.update_group_permissions()

        logger.debug(
            f"[权限调试] 插件 {self.name} 最终兼容性配置: {self.supported_platforms}"
        )
        logger.debug(
            f"[权限调试] 插件 {self.name} 群聊黑名单: {self.group_permissions}"
        )

    def update_platform_config(self, plugin_enable_config: dict) -> None:
        if not plugin_enable_config:
            return

        # 清空之前的配置
        self.supported_platforms.clear()

        # 处理平台配置
        if plugin_enable_config:
            # 遍历所有平台配置
            for platform_id, plugins in plugin_enable_config.items():
                # 检查该插件在当前平台的配置
                if self.name in plugins:
                    self.supported_platforms[platform_id] = plugins[self.name]
                    logger.debug(
                        f"[权限调试] 设置平台配置: {platform_id} = {plugins[self.name]}"
                    )
                else:
                    # 如果没有明确配置，默认为启用
                    self.supported_platforms[platform_id] = True
                    logger.debug(f"[权限调试] 默认启用平台: {platform_id}")

    def update_group_permissions(self) -> None:
        from astrbot.core import astrbot_config

        # 清空并更新群聊权限缓存
        self.group_permissions.clear()

        group_settings = astrbot_config.get("group_settings", {})
        plugin_enable = group_settings.get("plugin_enable", {})

        # 遍历所有群聊配置，只缓存被禁用的（黑名单方式）
        for group_id, plugins in plugin_enable.items():
            logger.debug(f"[权限调试] 处理群聊 {group_id} 的插件配置: {plugins}")
            if self.name in plugins:
                is_enabled = plugins[self.name]
                # 只缓存被禁用的群聊（黑名单方式）
                if not is_enabled:
                    self.group_permissions[group_id] = False
                    logger.debug(
                        f"[权限调试] 缓存禁用的群聊 {group_id} 配置: {is_enabled}"
                    )
                logger.debug(f"[权限调试] 设置群聊配置: {group_id} = {is_enabled}")
