from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from astrbot_sdk.errors import AstrBotError

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from ..bridge_base import (
    _EventStreamState,
    _get_runtime_astrbot_config,
    _get_runtime_file_token_service,
    _get_runtime_html_renderer,
)
from ._host import CapabilityMixinHost


class SystemCapabilityMixin(CapabilityMixinHost):
    def _register_system_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("system.get_data_dir", "Get plugin data dir"),
            call_handler=self._system_get_data_dir,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.text_to_image", "Render text to image"),
            call_handler=self._system_text_to_image,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.html_render", "Render html template"),
            call_handler=self._system_html_render,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.file.register", "Register file token"),
            call_handler=self._system_file_register,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.file.handle", "Resolve file token"),
            call_handler=self._system_file_handle,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.session_waiter.register",
                "Register sdk session waiter",
            ),
            call_handler=self._system_session_waiter_register,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.session_waiter.unregister",
                "Unregister sdk session waiter",
            ),
            call_handler=self._system_session_waiter_unregister,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.react", "Send sdk event reaction"),
            call_handler=self._system_event_react,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_typing",
                "Send sdk event typing state",
            ),
            call_handler=self._system_event_send_typing,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming",
                "Send sdk event streaming chunks",
            ),
            call_handler=self._system_event_send_streaming,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming_chunk",
                "Push sdk event streaming chunk",
            ),
            call_handler=self._system_event_send_streaming_chunk,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming_close",
                "Close sdk event streaming session",
            ),
            call_handler=self._system_event_send_streaming_close,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.llm.get_state",
                "Read sdk request llm state",
            ),
            call_handler=self._system_event_llm_get_state,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.llm.request",
                "Request default llm for current sdk request",
            ),
            call_handler=self._system_event_llm_request,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.result.get",
                "Read sdk request result",
            ),
            call_handler=self._system_event_result_get,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.result.set",
                "Write sdk request result",
            ),
            call_handler=self._system_event_result_set,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.result.clear",
                "Clear sdk request result",
            ),
            call_handler=self._system_event_result_clear,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.handler_whitelist.get",
                "Read sdk request handler whitelist",
            ),
            call_handler=self._system_event_handler_whitelist_get,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.handler_whitelist.set",
                "Write sdk request handler whitelist",
            ),
            call_handler=self._system_event_handler_whitelist_set,
            exposed=False,
        )

    def _register_registry_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor(
                "registry.get_handlers_by_event_type",
                "List SDK handlers by event type",
            ),
            call_handler=self._registry_get_handlers_by_event_type,
        )
        self.register(
            self._builtin_descriptor(
                "registry.get_handler_by_full_name",
                "Get SDK handler metadata by full name",
            ),
            call_handler=self._registry_get_handler_by_full_name,
        )
        self.register(
            self._builtin_descriptor(
                "registry.command.register",
                "Register dynamic command route",
            ),
            call_handler=self._registry_command_register,
        )

    async def _system_get_data_dir(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        data_dir = Path(get_astrbot_data_path()) / "plugin_data" / plugin_id
        data_dir.mkdir(parents=True, exist_ok=True)
        return {"path": str(data_dir.resolve())}

    async def _system_text_to_image(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        config_obj = self._star_context.get_config()
        template_name = None
        if hasattr(config_obj, "get"):
            try:
                template_name = config_obj.get("t2i_active_template")
            except Exception:
                template_name = None
        result = await _get_runtime_html_renderer().render_t2i(
            str(payload.get("text", "")),
            return_url=bool(payload.get("return_url", True)),
            template_name=template_name,
        )
        return {"result": result}

    async def _system_html_render(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AstrBotError.invalid_input("system.html_render requires object data")
        options = payload.get("options")
        if options is not None and not isinstance(options, dict):
            raise AstrBotError.invalid_input(
                "system.html_render options must be an object or null"
            )
        result = await _get_runtime_html_renderer().render_custom_template(
            str(payload.get("tmpl", "")),
            data,
            return_url=bool(payload.get("return_url", True)),
            options=options,
        )
        return {"result": result}

    async def _system_file_register(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        path = str(payload.get("path", "")).strip()
        if not path:
            raise AstrBotError.invalid_input("system.file.register requires path")
        raw_timeout = payload.get("timeout")
        timeout: float | None
        if raw_timeout is None:
            timeout = None
        else:
            try:
                timeout = float(raw_timeout)
            except (TypeError, ValueError) as exc:
                raise AstrBotError.invalid_input(
                    "system.file.register timeout must be a number or null"
                ) from exc
        file_token = await _get_runtime_file_token_service().register_file(
            path, timeout
        )
        callback_host = _get_runtime_astrbot_config().get("callback_api_base")
        if not callback_host:
            raise AstrBotError.invalid_input(
                "callback_api_base is required for system.file.register"
            )
        base_url = str(callback_host).rstrip("/")
        return {"token": file_token, "url": f"{base_url}/api/file/{file_token}"}

    async def _system_file_handle(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        file_token = str(payload.get("token", "")).strip()
        if not file_token:
            raise AstrBotError.invalid_input("system.file.handle requires token")
        path = await _get_runtime_file_token_service().handle_file(file_token)
        return {"path": str(path)}

    async def _system_session_waiter_register(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        self._plugin_bridge.register_session_waiter(
            plugin_id=plugin_id,
            session_key=str(payload.get("session_key", "")),
        )
        return {}

    async def _system_session_waiter_unregister(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        self._plugin_bridge.unregister_session_waiter(
            plugin_id=plugin_id,
            session_key=str(payload.get("session_key", "")),
        )
        return {}

    async def _system_event_react(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        request_context = self._resolve_event_request_context(request_id, payload)
        if request_context is None or request_context.cancelled:
            return {"supported": False}
        self._plugin_bridge.before_platform_send(request_context.dispatch_token)
        await request_context.event.react(str(payload.get("emoji", "")))
        return {
            "supported": bool(
                self._plugin_bridge.mark_platform_send(request_context.dispatch_token)
            )
        }

    async def _system_event_send_typing(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        request_context = self._resolve_event_request_context(request_id, payload)
        if request_context is None or request_context.cancelled:
            return {"supported": False}
        if type(request_context.event).send_typing is AstrMessageEvent.send_typing:
            return {"supported": False}
        await request_context.event.send_typing()
        return {"supported": True}

    async def _system_event_send_streaming(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        request_context = self._resolve_event_request_context(request_id, payload)
        if request_context is None or request_context.cancelled:
            return {"supported": False}
        if (
            type(request_context.event).send_streaming
            is AstrMessageEvent.send_streaming
        ):
            return {"supported": False}
        self._plugin_bridge.before_platform_send(request_context.dispatch_token)
        queue: asyncio.Queue[MessageChain | None] = asyncio.Queue()

        async def iterator() -> AsyncIterator[MessageChain]:
            while True:
                chunk = await queue.get()
                if chunk is None or request_context.cancelled:
                    return
                yield chunk
                await asyncio.sleep(0)

        stream_id = uuid.uuid4().hex
        task = asyncio.create_task(
            request_context.event.send_streaming(
                iterator(),
                use_fallback=bool(payload.get("use_fallback", False)),
            )
        )
        self._event_streams[stream_id] = _EventStreamState(
            request_context=request_context,
            queue=queue,
            task=task,
        )
        return {"supported": True, "stream_id": stream_id}

    async def _system_event_send_streaming_chunk(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        stream_state = self._event_streams.get(str(payload.get("stream_id", "")))
        if stream_state is None:
            raise AstrBotError.invalid_input("Unknown sdk event streaming session")
        if stream_state.request_context.cancelled:
            raise AstrBotError.cancelled("The SDK request has been cancelled")
        chain_payload = payload.get("chain")
        if not isinstance(chain_payload, list):
            raise AstrBotError.invalid_input(
                "system.event.send_streaming_chunk requires a chain array"
            )
        await stream_state.queue.put(self._build_core_message_chain(chain_payload))
        return {}

    async def _system_event_send_streaming_close(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        stream_id = str(payload.get("stream_id", ""))
        stream_state = self._event_streams.pop(stream_id, None)
        if stream_state is None:
            raise AstrBotError.invalid_input("Unknown sdk event streaming session")
        await stream_state.queue.put(None)
        try:
            await stream_state.task
        finally:
            self._event_streams.pop(stream_id, None)
        return {
            "supported": bool(
                self._plugin_bridge.mark_platform_send(
                    stream_state.request_context.dispatch_token
                )
            )
        }

    async def _system_event_llm_get_state(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        overlay = self._plugin_bridge.get_request_overlay_by_request_id(request_id)
        should_call_llm = self._plugin_bridge.get_should_call_llm_for_request(
            request_id
        )
        return {
            "should_call_llm": bool(should_call_llm),
            "requested_llm": bool(overlay.requested_llm)
            if overlay is not None
            else False,
        }

    async def _system_event_llm_request(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._plugin_bridge.request_llm_for_request(request_id)
        return await self._system_event_llm_get_state(request_id, {}, _token)

    async def _system_event_result_get(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        return {
            "result": self._plugin_bridge.get_result_payload_for_request(request_id)
        }

    async def _system_event_result_set(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        result_payload = payload.get("result")
        if not isinstance(result_payload, dict):
            raise AstrBotError.invalid_input(
                "system.event.result.set requires an object result payload"
            )
        if not self._plugin_bridge.set_result_for_request(request_id, result_payload):
            raise AstrBotError.cancelled("The SDK request overlay has been closed")
        return {
            "result": self._plugin_bridge.get_result_payload_for_request(request_id)
        }

    async def _system_event_result_clear(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._plugin_bridge.clear_result_for_request(request_id)
        return {}

    async def _system_event_handler_whitelist_get(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_names = self._plugin_bridge.get_handler_whitelist_for_request(request_id)
        if plugin_names is None:
            return {"plugin_names": None}
        return {"plugin_names": sorted(plugin_names)}

    async def _system_event_handler_whitelist_set(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_names_payload = payload.get("plugin_names")
        plugin_names: set[str] | None
        if plugin_names_payload is None:
            plugin_names = None
        elif isinstance(plugin_names_payload, list):
            plugin_names = {
                str(item) for item in plugin_names_payload if str(item).strip()
            }
        else:
            raise AstrBotError.invalid_input(
                "system.event.handler_whitelist.set requires a string array or null"
            )
        if not self._plugin_bridge.set_handler_whitelist_for_request(
            request_id, plugin_names
        ):
            raise AstrBotError.cancelled("The SDK request overlay has been closed")
        return await self._system_event_handler_whitelist_get(request_id, {}, _token)

    async def _registry_get_handlers_by_event_type(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        event_type = str(payload.get("event_type", "")).strip()
        return {"handlers": self._plugin_bridge.get_handlers_by_event_type(event_type)}

    async def _registry_get_handler_by_full_name(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        full_name = str(payload.get("full_name", "")).strip()
        return {"handler": self._plugin_bridge.get_handler_by_full_name(full_name)}

    async def _registry_command_register(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
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
                "registry.command.register priority must be an integer"
            )
        plugin_id = self._resolve_plugin_id(request_id)
        self._plugin_bridge.register_dynamic_command_route(
            plugin_id=plugin_id,
            command_name=str(payload.get("command_name", "")),
            handler_full_name=str(payload.get("handler_full_name", "")),
            desc=str(payload.get("desc", "")),
            priority=priority_value,
            use_regex=bool(payload.get("use_regex", False)),
        )
        return {}
