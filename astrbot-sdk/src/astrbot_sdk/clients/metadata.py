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

from ._errors import wrap_client_exception
from ._proxy import CapabilityProxy


@dataclass
class StarMetadata:
    """插件元数据。"""

    name: str
    display_name: str
    description: str
    repo: str
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
            repo=str(data.get("repo", "")),
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
        try:
            output = await self._proxy.call(
                "metadata.get_plugin",
                {"name": name},
            )
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MetadataClient",
                method_name="get_plugin",
                details=f"name={name!r}",
                exc=exc,
            ) from exc
        data = output.get("plugin")
        if data is None:
            return None
        return StarMetadata.from_dict(data)

    async def list_plugins(self) -> list[StarMetadata]:
        try:
            output = await self._proxy.call("metadata.list_plugins", {})
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MetadataClient",
                method_name="list_plugins",
                exc=exc,
            ) from exc
        items = output.get("plugins", [])
        return [
            StarMetadata.from_dict(item) for item in items if isinstance(item, dict)
        ]

    async def get_current_plugin(self) -> StarMetadata | None:
        return await self.get_plugin(self._plugin_id)

    async def get_plugin_config(self, name: str | None = None) -> dict[str, Any] | None:
        target = name or self._plugin_id
        if target != self._plugin_id:
            raise PermissionError(
                "get_plugin_config 只允许访问当前插件自己的配置，"
                f"请求的插件 '{target}' 不是当前插件 '{self._plugin_id}'"
            )
        try:
            output = await self._proxy.call(
                "metadata.get_plugin_config",
                {"name": target},
            )
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MetadataClient",
                method_name="get_plugin_config",
                details=f"name={target!r}",
                exc=exc,
            ) from exc
        config = output.get("config")
        return dict(config) if isinstance(config, dict) else None

    async def save_plugin_config(self, config: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(config, dict):
            raise TypeError("save_plugin_config requires a dict payload")
        try:
            output = await self._proxy.call(
                "metadata.save_plugin_config",
                {"config": dict(config)},
            )
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MetadataClient",
                method_name="save_plugin_config",
                details=f"keys={sorted(str(key) for key in config)!r}",
                exc=exc,
            ) from exc
        saved = output.get("config")
        return dict(saved) if isinstance(saved, dict) else {}
