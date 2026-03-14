"""元数据客户端模块。

提供插件元数据查询能力。

功能说明：
    - 查询已加载插件信息
    - 获取插件列表
    - 访问当前插件配置

安全边界：
    插件身份由运行时透传到协议层；客户端只暴露业务参数，不接受外部指定调用者。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._proxy import CapabilityProxy


@dataclass
class PluginMetadata:
    """插件元数据。"""

    name: str
    display_name: str
    description: str
    author: str
    version: str
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginMetadata":
        """从字典创建元数据实例。"""
        return cls(
            name=data.get("name", ""),
            display_name=data.get("display_name", data.get("name", "")),
            description=data.get("desc", data.get("description", "")),
            author=data.get("author", ""),
            version=data.get("version", "0.0.0"),
            enabled=data.get("enabled", True),
        )


class MetadataClient:
    """元数据能力客户端。

    提供插件元数据查询能力。

    Attributes:
        _proxy: CapabilityProxy 实例，用于远程能力调用
        _plugin_id: 当前插件 ID
    """

    def __init__(self, proxy: CapabilityProxy, plugin_id: str) -> None:
        """初始化元数据客户端。

        Args:
            proxy: CapabilityProxy 实例
            plugin_id: 当前插件 ID
        """
        self._proxy = proxy
        self._plugin_id = plugin_id

    async def get_plugin(self, name: str) -> PluginMetadata | None:
        """获取指定插件的元数据。

        Args:
            name: 插件名称

        Returns:
            插件元数据，不存在则返回 None

        示例:
            meta = await ctx.metadata.get_plugin("my_plugin")
            if meta:
                print(f"{meta.display_name} v{meta.version}")
        """
        output = await self._proxy.call(
            "metadata.get_plugin",
            {"name": name},
        )
        data = output.get("plugin")
        if data is None:
            return None
        return PluginMetadata.from_dict(data)

    async def list_plugins(self) -> list[PluginMetadata]:
        """获取所有已加载插件的元数据列表。

        Returns:
            插件元数据列表

        示例:
            plugins = await ctx.metadata.list_plugins()
            for p in plugins:
                print(f"- {p.display_name} ({p.name})")
        """
        output = await self._proxy.call("metadata.list_plugins", {})
        items = output.get("plugins", [])
        return [
            PluginMetadata.from_dict(item) for item in items if isinstance(item, dict)
        ]

    async def get_current_plugin(self) -> PluginMetadata | None:
        """获取当前插件的元数据。

        Returns:
            当前插件元数据

        示例:
            me = await ctx.metadata.get_current_plugin()
            print(f"我是 {me.display_name}")
        """
        return await self.get_plugin(self._plugin_id)

    async def get_plugin_config(self, name: str | None = None) -> dict[str, Any] | None:
        """获取插件配置。

        注意：出于安全考虑，只能查询当前插件自己的配置。
        尝试查询其他插件的配置会返回 None 并记录警告日志。

        Args:
            name: 插件名称，None 表示当前插件

        Returns:
            插件配置字典，权限拒绝时返回 None

        示例:
            config = await ctx.metadata.get_plugin_config()
            theme = config.get("theme", "default")
        """
        target = name or self._plugin_id
        if target != self._plugin_id:
            # SDK 侧直接拒绝，不发无意义的 RPC
            # 行为更确定：调用方明确知道返回 None 是"权限被拒"而非"插件不存在"
            import logging

            logging.getLogger(__name__).warning(
                "get_plugin_config 只支持查询当前插件自己的配置，"
                f"请求的插件 '{target}' 不是当前插件 '{self._plugin_id}'"
            )
            return None
        output = await self._proxy.call(
            "metadata.get_plugin_config",
            {"name": target},
        )
        return output.get("config")
