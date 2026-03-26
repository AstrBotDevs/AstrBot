from __future__ import annotations

import json
import uuid
from typing import Any

from ....errors import AstrBotError
from ..bridge_base import (
    CapabilityRouterBridgeBase,
    _clone_chain_payload,
    _clone_target_payload,
)


class SystemCapabilityMixin(CapabilityRouterBridgeBase):
    @staticmethod
    def _overlay_request_id(request_id: str, payload: dict[str, Any]) -> str:
        scope_request_id = payload.get("_request_scope_id")
        if isinstance(scope_request_id, str) and scope_request_id.strip():
            return scope_request_id
        return request_id

    def _register_system_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("system.get_data_dir", "获取插件数据目录"),
            call_handler=self._system_get_data_dir,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.text_to_image", "文本转图片"),
            call_handler=self._system_text_to_image,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.html_render", "渲染 HTML 模板"),
            call_handler=self._system_html_render,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.file.register", "注册文件令牌"),
            call_handler=self._system_file_register,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.file.handle", "解析文件令牌"),
            call_handler=self._system_file_handle,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.session_waiter.register",
                "注册会话等待器",
            ),
            call_handler=self._system_session_waiter_register,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.session_waiter.unregister",
                "注销会话等待器",
            ),
            call_handler=self._system_session_waiter_unregister,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.react", "发送事件表情回应"),
            call_handler=self._system_event_react,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.send_typing", "发送输入中状态"),
            call_handler=self._system_event_send_typing,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming",
                "发送事件流式消息",
            ),
            call_handler=self._system_event_send_streaming,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming_chunk",
                "推送事件流式消息分片",
            ),
            call_handler=self._system_event_send_streaming_chunk,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming_close",
                "关闭事件流式消息会话",
            ),
            call_handler=self._system_event_send_streaming_close,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.llm.get_state",
                "读取当前请求的默认 LLM 状态",
            ),
            call_handler=self._system_event_llm_get_state,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.llm.request",
                "请求当前事件继续进入默认 LLM 链路",
            ),
            call_handler=self._system_event_llm_request,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.result.get", "读取当前请求结果"),
            call_handler=self._system_event_result_get,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.result.set", "写入当前请求结果"),
            call_handler=self._system_event_result_set,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.result.clear", "清理当前请求结果"),
            call_handler=self._system_event_result_clear,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.handler_whitelist.get",
                "读取当前请求 handler 白名单",
            ),
            call_handler=self._system_event_handler_whitelist_get,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.handler_whitelist.set",
                "写入当前请求 handler 白名单",
            ),
            call_handler=self._system_event_handler_whitelist_set,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "registry.get_handlers_by_event_type",
                "按事件类型列出 handler 元数据",
            ),
            call_handler=self._registry_get_handlers_by_event_type,
        )
        self.register(
            self._builtin_descriptor(
                "registry.get_handler_by_full_name",
                "按 full name 查询 handler 元数据",
            ),
            call_handler=self._registry_get_handler_by_full_name,
        )
        self.register(
            self._builtin_descriptor(
                "registry.command.register",
                "注册动态命令路由",
            ),
            call_handler=self._registry_command_register,
        )

    def _ensure_request_overlay(self, request_id: str) -> dict[str, Any]:
        overlay = self._request_overlays.get(request_id)
        if overlay is None:
            overlay = {
                "should_call_llm": False,
                "requested_llm": False,
                "result": None,
                "handler_whitelist": None,
            }
            self._request_overlays[request_id] = overlay
        return overlay

    async def _system_get_data_dir(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("system.get_data_dir")
        data_dir = self._plugin_data_dir(
            plugin_id,
            capability_name="system.get_data_dir",
        )
        data_dir.mkdir(parents=True, exist_ok=True)
        return {"path": str(data_dir)}

    async def _system_text_to_image(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        text = str(payload.get("text", ""))
        if bool(payload.get("return_url", True)):
            return {"result": f"mock://text_to_image/{text}"}
        return {"result": f"<image>{text}</image>"}

    async def _system_html_render(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        tmpl = str(payload.get("tmpl", ""))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AstrBotError.invalid_input("system.html_render requires object data")
        if bool(payload.get("return_url", True)):
            return {"result": f"mock://html_render/{tmpl}"}
        return {"result": json.dumps({"tmpl": tmpl, "data": data}, ensure_ascii=False)}

    async def _system_file_register(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        path = str(payload.get("path", "")).strip()
        if not path:
            raise AstrBotError.invalid_input("system.file.register requires path")
        file_token = uuid.uuid4().hex
        self._file_token_store[file_token] = path
        return {"token": file_token, "url": f"mock://file/{file_token}"}

    async def _system_file_handle(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        file_token = str(payload.get("token", "")).strip()
        if not file_token:
            raise AstrBotError.invalid_input("system.file.handle requires token")
        path = self._file_token_store.pop(file_token, None)
        if path is None:
            raise AstrBotError.invalid_input(f"Unknown file token: {file_token}")
        return {"path": path}

    async def _system_event_llm_get_state(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay = self._ensure_request_overlay(
            self._overlay_request_id(request_id, payload)
        )
        return {
            "should_call_llm": bool(overlay["should_call_llm"]),
            "requested_llm": bool(overlay["requested_llm"]),
        }

    async def _system_event_llm_request(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay_request_id = self._overlay_request_id(request_id, payload)
        overlay = self._ensure_request_overlay(overlay_request_id)
        overlay["requested_llm"] = True
        overlay["should_call_llm"] = True
        return await self._system_event_llm_get_state(
            request_id,
            {"_request_scope_id": overlay_request_id},
            _token,
        )

    async def _system_event_result_get(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay = self._ensure_request_overlay(
            self._overlay_request_id(request_id, payload)
        )
        result = overlay.get("result")
        return {"result": dict(result) if isinstance(result, dict) else None}

    async def _system_event_result_set(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        result = payload.get("result")
        if not isinstance(result, dict):
            raise AstrBotError.invalid_input(
                "system.event.result.set 的 result 必须是 object"
            )
        overlay = self._ensure_request_overlay(
            self._overlay_request_id(request_id, payload)
        )
        overlay["result"] = dict(result)
        return {"result": dict(result)}

    async def _system_event_result_clear(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay = self._ensure_request_overlay(
            self._overlay_request_id(request_id, payload)
        )
        overlay["result"] = None
        return {}

    async def _system_event_handler_whitelist_get(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay = self._ensure_request_overlay(
            self._overlay_request_id(request_id, payload)
        )
        whitelist = overlay.get("handler_whitelist")
        if whitelist is None:
            return {"plugin_names": None}
        return {"plugin_names": sorted(str(item) for item in whitelist)}

    async def _system_event_handler_whitelist_set(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay_request_id = self._overlay_request_id(request_id, payload)
        overlay = self._ensure_request_overlay(overlay_request_id)
        plugin_names_payload = payload.get("plugin_names")
        if plugin_names_payload is None:
            overlay["handler_whitelist"] = None
        elif isinstance(plugin_names_payload, list):
            overlay["handler_whitelist"] = {
                str(item) for item in plugin_names_payload if str(item).strip()
            }
        else:
            raise AstrBotError.invalid_input(
                "system.event.handler_whitelist.set 的 plugin_names 必须是数组或 null"
            )
        return await self._system_event_handler_whitelist_get(
            request_id,
            {"_request_scope_id": overlay_request_id},
            _token,
        )

    async def _registry_get_handlers_by_event_type(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        event_type = str(payload.get("event_type", "")).strip()
        handlers: list[dict[str, Any]] = []
        for plugin in self._plugins.values():
            handlers.extend(
                [
                    dict(handler)
                    for handler in plugin.handlers
                    if event_type in handler.get("event_types", [])
                ]
            )
        if event_type == "message":
            for plugin_name, routes in self._dynamic_command_routes.items():
                for route in routes:
                    if not isinstance(route, dict):
                        continue
                    handlers.append(
                        {
                            "plugin_name": str(route.get("plugin_name", plugin_name)),
                            "handler_full_name": str(
                                route.get("handler_full_name", "")
                            ),
                            "trigger_type": (
                                "message"
                                if bool(route.get("use_regex", False))
                                else "command"
                            ),
                            "description": (
                                None
                                if route.get("desc") is None
                                else str(route.get("desc", "")).strip() or None
                            ),
                            "event_types": ["message"],
                            "enabled": True,
                            "group_path": [],
                            "priority": int(route.get("priority", 0) or 0),
                            "kind": "handler",
                            "require_admin": False,
                            "required_role": None,
                        }
                    )
        return {"handlers": handlers}

    async def _registry_get_handler_by_full_name(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        full_name = str(payload.get("full_name", "")).strip()
        for plugin in self._plugins.values():
            for handler in plugin.handlers:
                if handler.get("handler_full_name") == full_name:
                    return {"handler": dict(handler)}
        return {"handler": None}

    async def _registry_command_register(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        source_event_type = str(payload.get("source_event_type", "")).strip()
        if source_event_type not in {"astrbot_loaded", "platform_loaded"}:
            raise AstrBotError.invalid_input(
                "register_commands is only available in astrbot_loaded/platform_loaded events"
            )
        if bool(payload.get("ignore_prefix", False)):
            raise AstrBotError.invalid_input(
                "register_commands(ignore_prefix=True) is unsupported in SDK runtime"
            )
        priority_value = payload.get("priority", 0)
        if isinstance(priority_value, bool) or not isinstance(priority_value, int):
            raise AstrBotError.invalid_input(
                "registry.command.register 的 priority 必须是 integer"
            )
        plugin_id = self._require_caller_plugin_id("registry.command.register")
        self.register_dynamic_command_route(
            plugin_id=plugin_id,
            command_name=str(payload.get("command_name", "")),
            handler_full_name=str(payload.get("handler_full_name", "")),
            desc=str(payload.get("desc", "")),
            priority=priority_value,
            use_regex=bool(payload.get("use_regex", False)),
        )
        return {}

    async def _system_session_waiter_register(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("system.session_waiter.register")
        session_key = str(payload.get("session_key", "")).strip()
        if not session_key:
            raise AstrBotError.invalid_input(
                "system.session_waiter.register requires session_key"
            )
        self._session_waiters.setdefault(plugin_id, set()).add(session_key)
        return {}

    async def _system_session_waiter_unregister(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("system.session_waiter.unregister")
        session_key = str(payload.get("session_key", "")).strip()
        plugin_waiters = self._session_waiters.get(plugin_id)
        if plugin_waiters is None:
            return {}
        plugin_waiters.discard(session_key)
        if not plugin_waiters:
            self._session_waiters.pop(plugin_id, None)
        return {}

    async def _system_event_react(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self.event_actions.append(
            {
                "action": "react",
                "emoji": str(payload.get("emoji", "")),
                "target": _clone_target_payload(payload.get("target")),
            }
        )
        return {"supported": True}

    async def _system_event_send_typing(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self.event_actions.append(
            {
                "action": "send_typing",
                "target": _clone_target_payload(payload.get("target")),
            }
        )
        return {"supported": True}

    async def _system_event_send_streaming(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        stream_id = f"mock-stream-{len(self._event_streams) + 1}"
        stream_state: dict[str, Any] = {
            "target": _clone_target_payload(payload.get("target")),
            "chunks": [],
            "use_fallback": bool(payload.get("use_fallback", False)),
        }
        self._event_streams[stream_id] = stream_state
        return {"supported": True, "stream_id": stream_id}

    async def _system_event_send_streaming_chunk(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        stream = self._event_streams.get(str(payload.get("stream_id", "")))
        if stream is None:
            raise AstrBotError.invalid_input("Unknown sdk event streaming session")
        chain = payload.get("chain")
        if not isinstance(chain, list):
            raise AstrBotError.invalid_input(
                "system.event.send_streaming_chunk requires a chain array"
            )
        stream["chunks"].append({"chain": _clone_chain_payload(chain)})
        return {}

    async def _system_event_send_streaming_close(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        stream_id = str(payload.get("stream_id", ""))
        stream = self._event_streams.pop(stream_id, None)
        if stream is None:
            raise AstrBotError.invalid_input("Unknown sdk event streaming session")
        self.event_actions.append(
            {
                "action": "send_streaming",
                "target": stream["target"],
                "chunks": list(stream["chunks"]),
                "use_fallback": bool(stream["use_fallback"]),
            }
        )
        return {"supported": True}
