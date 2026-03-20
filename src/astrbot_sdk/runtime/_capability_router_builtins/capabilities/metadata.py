from __future__ import annotations

from typing import Any

from ..bridge_base import CapabilityRouterBridgeBase


class MetadataCapabilityMixin(CapabilityRouterBridgeBase):
    async def _metadata_get_plugin(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        plugin = self._plugins.get(name)
        if plugin is None:
            return {"plugin": None}
        return {"plugin": dict(plugin.metadata)}

    async def _metadata_list_plugins(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugins = [
            dict(self._plugins[name].metadata) for name in sorted(self._plugins.keys())
        ]
        return {"plugins": plugins}

    async def _metadata_get_plugin_config(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        caller_plugin_id = self._require_caller_plugin_id("metadata.get_plugin_config")
        if name != caller_plugin_id:
            return {"config": None}
        plugin = self._plugins.get(name)
        if plugin is None:
            return {"config": None}
        return {"config": dict(plugin.config)}

    async def _metadata_save_plugin_config(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        caller_plugin_id = self._require_caller_plugin_id(
            "metadata.save_plugin_config"
        )
        plugin = self._plugins.get(caller_plugin_id)
        if plugin is None:
            return {"config": None}
        config = payload.get("config")
        if not isinstance(config, dict):
            return {"config": dict(plugin.config)}
        plugin.config = dict(config)
        return {"config": dict(plugin.config)}

    def _register_metadata_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("metadata.get_plugin", "获取单个插件元数据"),
            call_handler=self._metadata_get_plugin,
        )
        self.register(
            self._builtin_descriptor("metadata.list_plugins", "列出插件元数据"),
            call_handler=self._metadata_list_plugins,
        )
        self.register(
            self._builtin_descriptor(
                "metadata.get_plugin_config",
                "获取插件配置",
            ),
            call_handler=self._metadata_get_plugin_config,
        )
        self.register(
            self._builtin_descriptor(
                "metadata.save_plugin_config",
                "保存当前插件配置",
            ),
            call_handler=self._metadata_save_plugin_config,
        )
