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

from dataclasses import dataclass, field
from typing import Any

from ._proxy import CapabilityProxy


@dataclass
class StarMetadata:
    """插件元数据。"""

    name: str
    display_name: str
    description: str
    author: str
    version: str
    enabled: bool = True
    support_platforms: list[str] = field(default_factory=list)
    astrbot_version: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StarMetadata:
        raw_support_platforms = data.get("support_platforms")
        support_platforms = (
            [str(item) for item in raw_support_platforms if isinstance(item, str)]
            if isinstance(raw_support_platforms, list)
            else []
        )
        return cls(
            name=str(data.get("name", "")),
            display_name=str(data.get("display_name", data.get("name", ""))),
            description=str(data.get("desc", data.get("description", ""))),
            author=str(data.get("author", "")),
            version=str(data.get("version", "0.0.0")),
            enabled=bool(data.get("enabled", True)),
            support_platforms=support_platforms,
            astrbot_version=(
                str(data.get("astrbot_version"))
                if data.get("astrbot_version") is not None
                else None
            ),
        )


PluginMetadata = StarMetadata


class MetadataClient:
    """元数据能力客户端。"""

    def __init__(self, proxy: CapabilityProxy, plugin_id: str) -> None:
        self._proxy = proxy
        self._plugin_id = plugin_id

    async def get_plugin(self, name: str) -> StarMetadata | None:
        output = await self._proxy.call(
            "metadata.get_plugin",
            {"name": name},
        )
        data = output.get("plugin")
        if data is None:
            return None
        return StarMetadata.from_dict(data)

    async def list_plugins(self) -> list[StarMetadata]:
        output = await self._proxy.call("metadata.list_plugins", {})
        items = output.get("plugins", [])
        return [
            StarMetadata.from_dict(item) for item in items if isinstance(item, dict)
        ]

    async def get_current_plugin(self) -> StarMetadata | None:
        return await self.get_plugin(self._plugin_id)

    async def get_plugin_config(self, name: str | None = None) -> dict[str, Any] | None:
        target = name or self._plugin_id
        if target != self._plugin_id:
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
