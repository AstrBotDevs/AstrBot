from __future__ import annotations

from typing import Any

from ....errors import AstrBotError
from ..bridge_base import CapabilityRouterBridgeBase


class PlatformCapabilityMixin(CapabilityRouterBridgeBase):
    async def _platform_send(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, target = self._resolve_target(payload)
        text = str(payload.get("text", ""))
        message_id = f"msg_{len(self.sent_messages) + 1}"
        sent: dict[str, Any] = {
            "message_id": message_id,
            "session": session,
            "text": text,
        }
        if target is not None:
            sent["target"] = target
        self.sent_messages.append(sent)
        return {"message_id": message_id}

    async def _platform_send_image(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, target = self._resolve_target(payload)
        image_url = str(payload.get("image_url", ""))
        message_id = f"img_{len(self.sent_messages) + 1}"
        sent: dict[str, Any] = {
            "message_id": message_id,
            "session": session,
            "image_url": image_url,
        }
        if target is not None:
            sent["target"] = target
        self.sent_messages.append(sent)
        return {"message_id": message_id}

    async def _platform_send_chain(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, target = self._resolve_target(payload)
        chain = payload.get("chain")
        if not isinstance(chain, list) or not all(
            isinstance(item, dict) for item in chain
        ):
            raise AstrBotError.invalid_input(
                "platform.send_chain 的 chain 必须是 object 数组"
            )
        message_id = f"chain_{len(self.sent_messages) + 1}"
        sent: dict[str, Any] = {
            "message_id": message_id,
            "session": session,
            "chain": [dict(item) for item in chain],
        }
        if target is not None:
            sent["target"] = target
        self.sent_messages.append(sent)
        return {"message_id": message_id}

    async def _platform_send_by_session(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        chain = payload.get("chain")
        if not isinstance(chain, list) or not all(
            isinstance(item, dict) for item in chain
        ):
            raise AstrBotError.invalid_input(
                "platform.send_by_session 的 chain 必须是 object 数组"
            )
        session = str(payload.get("session", ""))
        message_id = f"proactive_{len(self.sent_messages) + 1}"
        self.sent_messages.append(
            {
                "message_id": message_id,
                "session": session,
                "chain": [dict(item) for item in chain],
            }
        )
        return {"message_id": message_id}

    async def _platform_get_group(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, _target = self._resolve_target(payload)
        return {"group": self._mock_group_payload(session)}

    async def _platform_get_members(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, _target = self._resolve_target(payload)
        group = self._mock_group_payload(session)
        if group is None:
            return {"members": []}
        return {"members": list(group.get("members", []))}

    async def _platform_list_instances(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        return {
            "platforms": [
                {
                    "id": str(item.get("id", "")),
                    "name": str(item.get("name", "")),
                    "type": str(item.get("type", "")),
                    "status": str(item.get("status", "unknown")),
                }
                for item in self.get_platform_instances()
                if isinstance(item, dict)
            ]
        }

    def _register_platform_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("platform.send", "发送消息"),
            call_handler=self._platform_send,
        )
        self.register(
            self._builtin_descriptor("platform.send_image", "发送图片"),
            call_handler=self._platform_send_image,
        )
        self.register(
            self._builtin_descriptor("platform.send_chain", "发送消息链"),
            call_handler=self._platform_send_chain,
        )
        self.register(
            self._builtin_descriptor(
                "platform.send_by_session", "按会话主动发送消息链"
            ),
            call_handler=self._platform_send_by_session,
        )
        self.register(
            self._builtin_descriptor("platform.get_group", "获取当前群信息"),
            call_handler=self._platform_get_group,
        )
        self.register(
            self._builtin_descriptor("platform.get_members", "获取群成员"),
            call_handler=self._platform_get_members,
        )
        self.register(
            self._builtin_descriptor("platform.list_instances", "列出平台实例元信息"),
            call_handler=self._platform_list_instances,
        )

    async def _platform_manager_get_by_id(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("platform.manager.get_by_id")
        platform_id = str(payload.get("platform_id", "")).strip()
        platform = next(
            (
                dict(item)
                for item in self._platform_instances
                if str(item.get("id", "")) == platform_id
            ),
            None,
        )
        return {"platform": platform}

    async def _platform_manager_clear_errors(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("platform.manager.clear_errors")
        platform_id = str(payload.get("platform_id", "")).strip()
        for item in self._platform_instances:
            if str(item.get("id", "")) != platform_id:
                continue
            item["errors"] = []
            item["last_error"] = None
            if str(item.get("status", "")) == "error":
                item["status"] = "running"
            break
        return {}

    async def _platform_manager_get_stats(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("platform.manager.get_stats")
        platform_id = str(payload.get("platform_id", "")).strip()
        for item in self._platform_instances:
            if str(item.get("id", "")) != platform_id:
                continue
            stats = item.get("stats")
            if isinstance(stats, dict):
                return {"stats": dict(stats)}
            errors = item.get("errors")
            last_error = item.get("last_error")
            meta = item.get("meta")
            return {
                "stats": {
                    "id": platform_id,
                    "type": str(item.get("type", "")),
                    "display_name": str(item.get("name", platform_id)),
                    "status": str(item.get("status", "pending")),
                    "started_at": item.get("started_at"),
                    "error_count": len(errors) if isinstance(errors, list) else 0,
                    "last_error": dict(last_error)
                    if isinstance(last_error, dict)
                    else None,
                    "unified_webhook": bool(item.get("unified_webhook", False)),
                    "meta": dict(meta) if isinstance(meta, dict) else {},
                }
            }
        return {"stats": None}

    def _register_platform_manager_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor(
                "platform.manager.get_by_id",
                "按 ID 获取平台管理快照",
            ),
            call_handler=self._platform_manager_get_by_id,
        )
        self.register(
            self._builtin_descriptor(
                "platform.manager.clear_errors",
                "清除平台错误",
            ),
            call_handler=self._platform_manager_clear_errors,
        )
        self.register(
            self._builtin_descriptor(
                "platform.manager.get_stats",
                "获取平台统计信息",
            ),
            call_handler=self._platform_manager_get_stats,
        )

