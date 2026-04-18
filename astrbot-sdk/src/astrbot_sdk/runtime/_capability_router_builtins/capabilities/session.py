from __future__ import annotations

from typing import Any

from ....errors import AstrBotError
from ..bridge_base import CapabilityRouterBridgeBase


class SessionCapabilityMixin(CapabilityRouterBridgeBase):
    async def _session_plugin_is_enabled(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        plugin_name = str(payload.get("plugin_name", ""))
        config = self._session_plugin_config(session)
        enabled_plugins = {
            str(item) for item in config.get("enabled_plugins", []) if str(item).strip()
        }
        disabled_plugins = {
            str(item)
            for item in config.get("disabled_plugins", [])
            if str(item).strip()
        }
        if plugin_name in enabled_plugins:
            return {"enabled": True}
        return {"enabled": plugin_name not in disabled_plugins}

    async def _session_plugin_filter_handlers(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        handlers = payload.get("handlers")
        if not isinstance(handlers, list):
            raise AstrBotError.invalid_input(
                "session.plugin.filter_handlers 的 handlers 必须是 object 数组"
            )
        disabled_plugins = {
            str(item)
            for item in self._session_plugin_config(session).get("disabled_plugins", [])
            if str(item).strip()
        }
        reserved_plugins = {
            str(plugin.metadata.get("name", ""))
            for plugin in self._plugins.values()
            if bool(plugin.metadata.get("reserved", False))
        }
        filtered = []
        for item in handlers:
            if not isinstance(item, dict):
                continue
            plugin_name = str(item.get("plugin_name", ""))
            if (
                plugin_name
                and plugin_name in disabled_plugins
                and plugin_name not in reserved_plugins
            ):
                continue
            filtered.append(dict(item))
        return {"handlers": filtered}

    async def _session_service_is_llm_enabled(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        config = self._session_service_config(session)
        return {"enabled": bool(config.get("llm_enabled", True))}

    async def _session_service_set_llm_status(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        config = self._session_service_config(session)
        config["llm_enabled"] = bool(payload.get("enabled", False))
        self._session_service_configs[session] = config
        return {}

    async def _session_service_is_tts_enabled(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        config = self._session_service_config(session)
        return {"enabled": bool(config.get("tts_enabled", True))}

    async def _session_service_set_tts_status(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        config = self._session_service_config(session)
        config["tts_enabled"] = bool(payload.get("enabled", False))
        self._session_service_configs[session] = config
        return {}

    def _register_session_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("session.plugin.is_enabled", "获取会话级插件开关"),
            call_handler=self._session_plugin_is_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.plugin.filter_handlers",
                "按会话过滤 handler 元数据",
            ),
            call_handler=self._session_plugin_filter_handlers,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.is_llm_enabled",
                "获取会话级 LLM 开关",
            ),
            call_handler=self._session_service_is_llm_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.set_llm_status",
                "写入会话级 LLM 开关",
            ),
            call_handler=self._session_service_set_llm_status,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.is_tts_enabled",
                "获取会话级 TTS 开关",
            ),
            call_handler=self._session_service_is_tts_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.set_tts_status",
                "写入会话级 TTS 开关",
            ),
            call_handler=self._session_service_set_tts_status,
        )
