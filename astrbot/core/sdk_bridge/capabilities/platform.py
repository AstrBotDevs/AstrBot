from __future__ import annotations

import uuid
from typing import Any

from astrbot_sdk.errors import AstrBotError

from astrbot.core.message.components import Image, Plain
from astrbot.core.message.message_event_result import MessageChain

from ._host import CapabilityMixinHost


class PlatformCapabilityMixin(CapabilityMixinHost):
    def _register_platform_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("platform.send", "Send plain text"),
            call_handler=self._platform_send,
        )
        self.register(
            self._builtin_descriptor("platform.send_image", "Send image"),
            call_handler=self._platform_send_image,
        )
        self.register(
            self._builtin_descriptor("platform.send_chain", "Send message chain"),
            call_handler=self._platform_send_chain,
        )
        self.register(
            self._builtin_descriptor(
                "platform.send_by_session",
                "Send message chain to a specific session",
            ),
            call_handler=self._platform_send_by_session,
        )
        self.register(
            self._builtin_descriptor("platform.get_group", "Get current group data"),
            call_handler=self._platform_get_group,
        )
        self.register(
            self._builtin_descriptor("platform.get_members", "Get group members"),
            call_handler=self._platform_get_members,
        )
        self.register(
            self._builtin_descriptor(
                "platform.list_instances",
                "List available platform instances",
            ),
            call_handler=self._platform_list_instances,
        )

    def _register_platform_manager_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor(
                "platform.manager.get_by_id",
                "Get platform management snapshot by id",
            ),
            call_handler=self._platform_manager_get_by_id,
        )
        self.register(
            self._builtin_descriptor(
                "platform.manager.clear_errors",
                "Clear platform error records",
            ),
            call_handler=self._platform_manager_clear_errors,
        )
        self.register(
            self._builtin_descriptor(
                "platform.manager.get_stats",
                "Get platform stats by id",
            ),
            call_handler=self._platform_manager_get_stats,
        )

    async def _platform_send(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session, dispatch_token = self._resolve_dispatch_target(request_id, payload)
        self._plugin_bridge.before_platform_send(dispatch_token)
        await self._star_context.send_message(
            session,
            MessageChain([Plain(str(payload.get("text", "")), convert=False)]),
        )
        return {"message_id": self._plugin_bridge.mark_platform_send(dispatch_token)}

    async def _platform_send_image(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session, dispatch_token = self._resolve_dispatch_target(request_id, payload)
        self._plugin_bridge.before_platform_send(dispatch_token)
        image_url = str(payload.get("image_url", ""))
        component = (
            Image.fromURL(image_url)
            if image_url.startswith(("http://", "https://"))
            else Image.fromFileSystem(image_url)
        )
        await self._star_context.send_message(session, MessageChain([component]))
        return {"message_id": self._plugin_bridge.mark_platform_send(dispatch_token)}

    async def _platform_send_chain(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session, dispatch_token = self._resolve_dispatch_target(request_id, payload)
        self._plugin_bridge.before_platform_send(dispatch_token)
        chain_payload = payload.get("chain")
        if not isinstance(chain_payload, list):
            raise AstrBotError.invalid_input(
                "platform.send_chain requires a chain array"
            )
        await self._star_context.send_message(
            session,
            self._build_core_message_chain(chain_payload),
        )
        return {"message_id": self._plugin_bridge.mark_platform_send(dispatch_token)}

    async def _platform_send_by_session(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        chain_payload = payload.get("chain")
        if not isinstance(chain_payload, list):
            raise AstrBotError.invalid_input(
                "platform.send_by_session requires a chain array"
            )
        session = str(payload.get("session", ""))
        if not session:
            raise AstrBotError.invalid_input(
                "platform.send_by_session requires a session"
            )
        request_context = self._resolve_event_request_context(request_id, payload)
        dispatch_token = None
        if request_context is not None and not request_context.cancelled:
            dispatch_token = request_context.dispatch_token
            self._plugin_bridge.before_platform_send(dispatch_token)
        await self._star_context.send_message(
            session,
            self._build_core_message_chain(chain_payload),
        )
        if dispatch_token is not None:
            return {
                "message_id": self._plugin_bridge.mark_platform_send(dispatch_token)
            }
        return {"message_id": f"sdk_proactive_{uuid.uuid4().hex}"}

    async def _platform_get_group(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        request_context = self._resolve_current_group_request_context(
            request_id, payload
        )
        if request_context is None:
            return {"group": None}
        group = await request_context.event.get_group()
        return {"group": self._serialize_group(group)}

    async def _platform_get_members(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        request_context = self._resolve_current_group_request_context(
            request_id, payload
        )
        if request_context is None:
            return {"members": []}
        group = await request_context.event.get_group()
        serialized_group = self._serialize_group(group)
        if serialized_group is None:
            return {"members": []}
        members = serialized_group.get("members")
        return {"members": list(members) if isinstance(members, list) else []}

    async def _platform_list_instances(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        platform_manager = getattr(self._star_context, "platform_manager", None)
        if platform_manager is None or not hasattr(platform_manager, "get_insts"):
            return {"platforms": []}
        platforms_payload: list[dict[str, Any]] = []
        for platform in list(platform_manager.get_insts()):
            meta = None
            try:
                meta = platform.meta()
            except Exception:
                continue
            platform_id = str(getattr(meta, "id", "")).strip()
            platform_type = str(getattr(meta, "name", "")).strip()
            if not platform_id or not platform_type:
                continue
            status = getattr(platform, "status", None)
            status_value = getattr(status, "value", status)
            display_name = str(
                getattr(meta, "adapter_display_name", None) or platform_type
            )
            platforms_payload.append(
                {
                    "id": platform_id,
                    "name": display_name,
                    "type": platform_type,
                    "status": str(status_value or "unknown"),
                }
            )
        return {"platforms": platforms_payload}

    async def _platform_manager_get_by_id(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(
            request_id,
            "platform.manager.get_by_id",
        )
        platform = self._get_platform_inst_by_id(str(payload.get("platform_id", "")))
        return {"platform": self._serialize_platform_snapshot(platform)}

    async def _platform_manager_clear_errors(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(
            request_id,
            "platform.manager.clear_errors",
        )
        platform = self._get_platform_inst_by_id(str(payload.get("platform_id", "")))
        if platform is None:
            raise AstrBotError.invalid_input("Unknown platform_id")
        clear_errors = getattr(platform, "clear_errors", None)
        if callable(clear_errors):
            clear_errors()
        return {}

    async def _platform_manager_get_stats(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(
            request_id,
            "platform.manager.get_stats",
        )
        platform = self._get_platform_inst_by_id(str(payload.get("platform_id", "")))
        if platform is None:
            return {"stats": None}
        get_stats = getattr(platform, "get_stats", None)
        if not callable(get_stats):
            return {"stats": None}
        return {"stats": self._serialize_platform_stats(get_stats())}
