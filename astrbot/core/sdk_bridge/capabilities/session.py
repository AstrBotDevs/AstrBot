from __future__ import annotations

from typing import Any

from astrbot_sdk.errors import AstrBotError

from ..bridge_base import _get_runtime_sp
from ._host import CapabilityMixinHost


class SessionCapabilityMixin(CapabilityMixinHost):
    def _register_session_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor(
                "session.plugin.is_enabled",
                "Get session plugin enabled state",
            ),
            call_handler=self._session_plugin_is_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.plugin.filter_handlers",
                "Filter handler metadata by session plugin config",
            ),
            call_handler=self._session_plugin_filter_handlers,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.is_llm_enabled",
                "Get session LLM enabled state",
            ),
            call_handler=self._session_service_is_llm_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.set_llm_status",
                "Set session LLM enabled state",
            ),
            call_handler=self._session_service_set_llm_status,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.is_tts_enabled",
                "Get session TTS enabled state",
            ),
            call_handler=self._session_service_is_tts_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.set_tts_status",
                "Set session TTS enabled state",
            ),
            call_handler=self._session_service_set_tts_status,
        )

    async def _load_session_plugin_config(self, session_id: str) -> dict[str, Any]:
        raw_config = await _get_runtime_sp().get_async(
            scope="umo",
            scope_id=session_id,
            key="session_plugin_config",
            default={},
        )
        return self._normalize_session_scoped_config(raw_config, session_id)

    async def _load_session_service_config(self, session_id: str) -> dict[str, Any]:
        raw_config = await _get_runtime_sp().get_async(
            scope="umo",
            scope_id=session_id,
            key="session_service_config",
            default={},
        )
        return self._normalize_session_scoped_config(raw_config, session_id)

    async def _session_plugin_is_enabled(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        plugin_name = str(payload.get("plugin_name", "")).strip()
        config = await self._load_session_plugin_config(session_id)
        enabled_plugins = {
            str(item) for item in config.get("enabled_plugins", []) if str(item).strip()
        }
        disabled_plugins = {
            str(item)
            for item in config.get("disabled_plugins", [])
            if str(item).strip()
        }
        if (
            plugin_name in disabled_plugins
            and plugin_name not in self._reserved_plugin_names()
        ):
            return {"enabled": False}
        if plugin_name in enabled_plugins:
            return {"enabled": True}
        return {"enabled": True}

    async def _session_plugin_filter_handlers(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        handlers = payload.get("handlers")
        if not isinstance(handlers, list):
            raise AstrBotError.invalid_input(
                "session.plugin.filter_handlers requires a handlers array"
            )
        config = await self._load_session_plugin_config(session_id)
        disabled_plugins = {
            str(item)
            for item in config.get("disabled_plugins", [])
            if str(item).strip()
        }
        reserved_plugins = self._reserved_plugin_names()
        filtered = []
        for item in handlers:
            if not isinstance(item, dict):
                continue
            plugin_name = str(item.get("plugin_name", "")).strip()
            if (
                plugin_name
                and plugin_name in disabled_plugins
                and plugin_name not in reserved_plugins
            ):
                continue
            filtered.append(dict(item))
        return {"handlers": filtered}

    async def _session_service_is_llm_enabled(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        config = await self._load_session_service_config(session_id)
        return {"enabled": bool(config.get("llm_enabled", True))}

    async def _session_service_set_llm_status(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        config = await self._load_session_service_config(session_id)
        config["llm_enabled"] = bool(payload.get("enabled", False))
        await _get_runtime_sp().put_async(
            scope="umo",
            scope_id=session_id,
            key="session_service_config",
            value=config,
        )
        return {}

    async def _session_service_is_tts_enabled(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        config = await self._load_session_service_config(session_id)
        return {"enabled": bool(config.get("tts_enabled", True))}

    async def _session_service_set_tts_status(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        config = await self._load_session_service_config(session_id)
        config["tts_enabled"] = bool(payload.get("enabled", False))
        await _get_runtime_sp().put_async(
            scope="umo",
            scope_id=session_id,
            key="session_service_config",
            value=config,
        )
        return {}
