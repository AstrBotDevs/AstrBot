from __future__ import annotations

import asyncio
import copy
import json
import uuid
from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.message.components import component_to_payload_sync

from astrbot.core import logger
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse as CoreLLMResponse
from astrbot.core.provider.entities import ProviderRequest as CoreProviderRequest

from .bridge_base import _build_message_chain_from_payload
from .event_payload import (
    InboundEventSnapshot,
    build_inbound_event_snapshot,
    normalize_sdk_local_extras,
    sanitize_sdk_extras,
)
from .runtime_store import (
    SdkRuntimeStore,
    _RequestContext,
    _RequestOverlayState,
)

if TYPE_CHECKING:
    from .plugin_bridge import SdkPluginBridge


class _EventResultBinding:
    def __init__(self, *, runtime: SdkRequestRuntime, dispatch_token: str) -> None:
        self.runtime = runtime
        self.dispatch_token = dispatch_token

    def is_active(self) -> bool:
        return (
            self.runtime.get_request_overlay_by_token(self.dispatch_token) is not None
        )

    def has_result_state(self) -> bool:
        overlay = self.runtime.get_request_overlay_by_token(self.dispatch_token)
        return bool(overlay is not None and overlay.result_is_set)

    def get_result(self) -> MessageEventResult | None:
        return self.runtime.get_effective_result_for_token(self.dispatch_token)

    def set_result(self, result: MessageEventResult) -> None:
        self.runtime.set_result_for_dispatch_token(self.dispatch_token, result)

    def clear_result(self) -> None:
        self.runtime.clear_result_for_dispatch_token(self.dispatch_token)

    def stop_event(self) -> None:
        self.runtime.stop_event_for_dispatch_token(self.dispatch_token)

    def continue_event(self) -> None:
        self.runtime.continue_event_for_dispatch_token(self.dispatch_token)

    def is_stopped(self) -> bool:
        return self.runtime.is_stopped_for_dispatch_token(self.dispatch_token)


class SdkRequestRuntime:
    def __init__(
        self,
        *,
        bridge: SdkPluginBridge,
        store: SdkRuntimeStore,
        overlay_timeout_seconds: int,
    ) -> None:
        self.bridge = bridge
        self.store = store
        self.overlay_timeout_seconds = overlay_timeout_seconds

    def get_or_bind_dispatch_token(self, event: AstrMessageEvent) -> str:
        dispatch_token = self.get_dispatch_token(event) or uuid.uuid4().hex
        self.bind_dispatch_token(event, dispatch_token)
        return dispatch_token

    def bind_dispatch_token(self, event: AstrMessageEvent, dispatch_token: str) -> None:
        setattr(event, "_sdk_dispatch_token", dispatch_token)
        setattr(
            event,
            "_sdk_result_binding",
            _EventResultBinding(runtime=self, dispatch_token=dispatch_token),
        )

    def get_dispatch_token(self, event: AstrMessageEvent) -> str | None:
        token = getattr(event, "_sdk_dispatch_token", None)
        return str(token) if token else None

    def schedule_overlay_cleanup(
        self, dispatch_token: str
    ) -> asyncio.Task[None] | None:
        async def _cleanup_later() -> None:
            try:
                await asyncio.sleep(self.overlay_timeout_seconds)
            except asyncio.CancelledError:
                return
            self.close_request_overlay(dispatch_token)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        return loop.create_task(_cleanup_later())

    def ensure_request_overlay(
        self,
        dispatch_token: str,
        *,
        should_call_llm: bool,
    ) -> _RequestOverlayState:
        overlay = self.store.request_overlays.get(dispatch_token)
        if overlay is not None:
            if overlay.closed:
                overlay.closed = False
            if overlay.cleanup_task is None or overlay.cleanup_task.done():
                overlay.cleanup_task = self.schedule_overlay_cleanup(dispatch_token)
            return overlay
        overlay = _RequestOverlayState(
            dispatch_token=dispatch_token,
            should_call_llm=should_call_llm,
            cleanup_task=self.schedule_overlay_cleanup(dispatch_token),
        )
        self.store.request_overlays[dispatch_token] = overlay
        return overlay

    def track_request_scope(
        self,
        *,
        dispatch_token: str,
        request_id: str,
        plugin_id: str,
    ) -> None:
        self.store.request_id_to_token[request_id] = dispatch_token
        self.store.request_plugin_ids[request_id] = plugin_id
        overlay = self.store.request_overlays.get(dispatch_token)
        if overlay is not None:
            overlay.request_scope_ids.add(request_id)

    def close_request_overlay(self, dispatch_token: str) -> None:
        request_context = self.store.request_contexts.get(dispatch_token)
        bound_event = None
        dispatch_state = (
            getattr(request_context, "dispatch_state", None)
            if request_context is not None
            else None
        )
        if dispatch_state is not None:
            bound_event = dispatch_state.event
            bound_event._result = self.get_effective_result_for_token(dispatch_token)
            bound_event.call_llm = not self.get_effective_should_call_llm(bound_event)
            if hasattr(bound_event, "_sdk_result_binding"):
                delattr(bound_event, "_sdk_result_binding")
        overlay = self.store.request_overlays.pop(dispatch_token, None)
        if overlay is not None:
            overlay.closed = True
            if overlay.cleanup_task is not None:
                overlay.cleanup_task.cancel()
            for request_id in overlay.request_scope_ids:
                self.store.request_id_to_token.pop(request_id, None)
                self.store.request_plugin_ids.pop(request_id, None)
        request_context = self.store.request_contexts.pop(dispatch_token, None)
        if request_context is not None:
            request_context.cancelled = True

    def close_request_overlay_for_event(self, event: AstrMessageEvent) -> None:
        dispatch_token = self.get_dispatch_token(event)
        if dispatch_token:
            self.close_request_overlay(dispatch_token)

    def resolve_request_plugin_id(self, request_id: str) -> str:
        plugin_id = self.store.request_plugin_ids.get(request_id)
        if plugin_id is not None:
            return plugin_id
        token = self.store.request_id_to_token.get(request_id)
        if token is not None and token in self.store.request_contexts:
            return self.store.request_contexts[token].plugin_id
        raise AstrBotError.invalid_input(f"Unknown SDK request id: {request_id}")

    def resolve_request_session(self, request_id: str) -> _RequestContext | None:
        token = self.store.request_id_to_token.get(request_id)
        if token is None:
            return None
        return self.store.request_contexts.get(token)

    def get_request_context_by_token(
        self, dispatch_token: str
    ) -> _RequestContext | None:
        return self.store.request_contexts.get(dispatch_token)

    def get_request_overlay_by_token(
        self, dispatch_token: str
    ) -> _RequestOverlayState | None:
        overlay = self.store.request_overlays.get(dispatch_token)
        if overlay is None or overlay.closed:
            return None
        return overlay

    def get_request_overlay_by_request_id(
        self, request_id: str
    ) -> _RequestOverlayState | None:
        token = self.store.request_id_to_token.get(request_id)
        if not token:
            return None
        return self.get_request_overlay_by_token(token)

    def request_llm_for_request(self, request_id: str) -> bool:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return False
        overlay.requested_llm = True
        if not overlay.result_stopped:
            overlay.should_call_llm = True
        return True

    def get_effective_should_call_llm(self, event: AstrMessageEvent) -> bool:
        dispatch_token = self.get_dispatch_token(event)
        if dispatch_token:
            overlay = self.get_request_overlay_by_token(dispatch_token)
            if overlay is not None:
                return overlay.should_call_llm
        return not bool(getattr(event, "call_llm", False))

    def get_should_call_llm_for_request(self, request_id: str) -> bool | None:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return None
        return overlay.should_call_llm

    @staticmethod
    def set_overlay_stop_state(
        overlay: _RequestOverlayState,
        *,
        stopped: bool,
    ) -> None:
        overlay.result_stopped = stopped
        if stopped:
            overlay.should_call_llm = False

    def set_result_from_object(
        self,
        overlay: _RequestOverlayState,
        result: MessageEventResult | None,
    ) -> None:
        overlay.result_object = result
        overlay.result_is_set = True
        self.set_overlay_stop_state(
            overlay,
            stopped=bool(result is not None and result.is_stopped()),
        )
        self.sync_overlay_payload_from_result_object(overlay)

    def bind_result_object(
        self,
        overlay: _RequestOverlayState,
        result: MessageEventResult | None,
    ) -> None:
        overlay.result_object = result
        overlay.result_is_set = True
        self.set_overlay_stop_state(
            overlay,
            stopped=bool(result is not None and result.is_stopped()),
        )

    def set_result_payload_on_overlay(
        self,
        overlay: _RequestOverlayState,
        result_payload: dict[str, Any] | None,
    ) -> None:
        if result_payload is None:
            overlay.result_payload = None
            overlay.result_object = None
            overlay.result_is_set = True
            self.set_overlay_stop_state(overlay, stopped=False)
            return
        normalized_payload = json.loads(json.dumps(result_payload))
        overlay.result_payload = normalized_payload
        chain_payload = normalized_payload.get("chain")
        overlay.result_object = (
            self.build_core_result_from_chain_payload(chain_payload)
            if isinstance(chain_payload, list)
            else None
        )
        overlay.result_is_set = True
        self.set_overlay_stop_state(
            overlay,
            stopped=bool(normalized_payload.get("stop", False)),
        )

    def sync_overlay_payload_from_result_object(
        self,
        overlay: _RequestOverlayState,
    ) -> None:
        overlay.result_payload = self.bridge._legacy_result_to_sdk_payload(
            overlay.result_object
        )
        self.set_overlay_stop_state(
            overlay,
            stopped=bool(
                overlay.result_object is not None and overlay.result_object.is_stopped()
            ),
        )

    def get_effective_result_for_token(
        self,
        dispatch_token: str,
    ) -> MessageEventResult | None:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None or not overlay.result_is_set:
            request_context = self.store.request_contexts.get(dispatch_token)
            if (
                request_context is not None
                and request_context.dispatch_state is not None
            ):
                return request_context.dispatch_state.event._result
            return None
        if overlay.result_object is None and overlay.result_payload is not None:
            chain_payload = overlay.result_payload.get("chain")
            if isinstance(chain_payload, list):
                overlay.result_object = self.build_core_result_from_chain_payload(
                    chain_payload
                )
        if overlay.result_object is None:
            if overlay.result_stopped:
                stopped_result = MessageEventResult()
                stopped_result.stop_event()
                overlay.result_object = stopped_result
            else:
                return None
        if overlay.result_stopped and not overlay.result_object.is_stopped():
            overlay.result_object.stop_event()
        elif not overlay.result_stopped and overlay.result_object.is_stopped():
            overlay.result_object.continue_event()
        return overlay.result_object

    def set_result_for_dispatch_token(
        self,
        dispatch_token: str,
        result: MessageEventResult | None,
    ) -> None:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is not None:
            self.set_result_from_object(overlay, result)

    def clear_result_for_dispatch_token(self, dispatch_token: str) -> None:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return
        overlay.result_payload = None
        overlay.result_object = None
        overlay.result_is_set = True
        self.set_overlay_stop_state(overlay, stopped=False)

    def stop_event_for_dispatch_token(self, dispatch_token: str) -> None:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return
        self.set_overlay_stop_state(overlay, stopped=True)
        overlay.result_is_set = True
        if overlay.result_object is not None and not overlay.result_object.is_stopped():
            overlay.result_object.stop_event()

    def continue_event_for_dispatch_token(self, dispatch_token: str) -> None:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return
        overlay.result_is_set = True
        self.set_overlay_stop_state(overlay, stopped=False)
        if overlay.result_object is not None and overlay.result_object.is_stopped():
            overlay.result_object.continue_event()

    def is_stopped_for_dispatch_token(self, dispatch_token: str) -> bool:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is not None and overlay.result_is_set:
            return overlay.result_stopped
        request_context = self.store.request_contexts.get(dispatch_token)
        if request_context is not None and request_context.dispatch_state is not None:
            result = request_context.dispatch_state.event._result
            return bool(result is not None and result.is_stopped())
        return False

    def set_result_for_request(
        self,
        request_id: str,
        result_payload: dict[str, Any] | None,
    ) -> bool:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return False
        self.set_result_payload_on_overlay(overlay, result_payload)
        return True

    def clear_result_for_request(self, request_id: str) -> bool:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return False
        overlay.result_payload = None
        overlay.result_object = None
        overlay.result_is_set = True
        self.set_overlay_stop_state(overlay, stopped=False)
        return True

    def get_result_payload_for_request(self, request_id: str) -> dict[str, Any] | None:
        overlay = self.get_request_overlay_by_request_id(request_id)
        request_context = self.resolve_request_session(request_id)
        request_context_has_event = False
        if request_context is not None:
            has_event = getattr(request_context, "has_event", None)
            request_context_has_event = (
                bool(has_event)
                if has_event is not None
                else hasattr(request_context, "event")
            )
        if overlay is not None and overlay.result_is_set:
            if overlay.result_object is not None:
                self.sync_overlay_payload_from_result_object(overlay)
            return (
                copy.deepcopy(overlay.result_payload)
                if overlay.result_payload is not None
                else None
            )
        if request_context is None or not request_context_has_event:
            return None
        return self.bridge._legacy_result_to_sdk_payload(
            request_context.event.get_result()
        )

    def set_handler_whitelist_for_request(
        self,
        request_id: str,
        plugin_names: set[str] | None,
    ) -> bool:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return False
        overlay.handler_whitelist = None if plugin_names is None else set(plugin_names)
        return True

    def get_handler_whitelist_for_request(self, request_id: str) -> set[str] | None:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return None
        return (
            None
            if overlay.handler_whitelist is None
            else set(overlay.handler_whitelist)
        )

    def get_handler_whitelist_for_event(
        self, event: AstrMessageEvent
    ) -> set[str] | None:
        dispatch_token = self.get_dispatch_token(event)
        if not dispatch_token:
            return None
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return None
        return (
            None
            if overlay.handler_whitelist is None
            else set(overlay.handler_whitelist)
        )

    @staticmethod
    def build_core_message_chain_from_payload(
        chain_payload: list[dict[str, Any]],
    ) -> MessageChain:
        return _build_message_chain_from_payload(chain_payload)

    @classmethod
    def build_core_result_from_chain_payload(
        cls,
        chain_payload: list[dict[str, Any]],
    ) -> MessageEventResult:
        chain = cls.build_core_message_chain_from_payload(chain_payload)
        result = MessageEventResult()
        setattr(result, "chain", chain)
        result.use_t2i_ = chain.use_t2i_
        result.type = chain.type
        return result

    @staticmethod
    def legacy_result_to_sdk_payload(
        result: MessageEventResult | None,
    ) -> dict[str, Any] | None:
        if result is None:
            return None
        chain = (
            result.chain.chain
            if isinstance(result.chain, MessageChain)
            else result.chain
        )
        payload = {
            "type": "chain" if chain else "empty",
            "chain": SdkRequestRuntime.components_to_sdk_payload(chain),
        }
        if result.is_stopped():
            payload["stop"] = True
        return payload

    @staticmethod
    def components_to_sdk_payload(
        components: list[Any] | tuple[Any, ...] | None,
    ) -> list[dict[str, Any]]:
        return [
            component_to_payload_sync(component) for component in (components or [])
        ]

    def persist_sdk_local_extras_from_handler(
        self,
        overlay: _RequestOverlayState,
        payload: Any,
        *,
        plugin_id: str,
        handler_id: str,
    ) -> None:
        if payload is None:
            overlay.sdk_local_extras = {}
            return
        if not isinstance(payload, dict):
            logger.warning(
                "SDK event handler returned invalid sdk_local_extras: plugin=%s handler=%s payload_type=%s",
                plugin_id,
                handler_id,
                type(payload).__name__,
            )
            return
        normalized, dropped_keys = normalize_sdk_local_extras(payload)
        overlay.sdk_local_extras = normalized
        for key in dropped_keys:
            value = payload.get(key)
            logger.warning(
                "Dropped sdk_local_extras entry during SDK bridge serialization: "
                "plugin=%s handler=%s key=%s value_type=%s reason=%s "
                "recommended_fix=%s",
                plugin_id,
                handler_id,
                key,
                type(value).__name__,
                "sdk_local_extras only preserves JSON-serializable values across "
                "handler and lifecycle boundaries",
                "store plain dict/list/scalar payloads, or serialize framework "
                "objects such as message components before calling set_extra()",
            )

    @staticmethod
    def sanitize_host_extras(event: AstrMessageEvent) -> dict[str, Any]:
        extras = event.get_extra()
        if not isinstance(extras, dict) or not extras:
            return {}
        return sanitize_sdk_extras(extras)

    @staticmethod
    def set_sdk_origin_plugin_id(
        event: AstrMessageEvent,
        plugin_id: str,
    ) -> None:
        setter = getattr(event, "set_extra", None)
        if callable(setter):
            setter("_sdk_origin_plugin_id", plugin_id)
            return
        setattr(event, "_sdk_origin_plugin_id", plugin_id)

    def get_or_build_inbound_snapshot(
        self,
        event: AstrMessageEvent,
        overlay: _RequestOverlayState | None,
    ) -> InboundEventSnapshot:
        if overlay is not None and overlay.inbound_snapshot is not None:
            return overlay.inbound_snapshot
        snapshot = build_inbound_event_snapshot(event)
        if overlay is not None:
            overlay.inbound_snapshot = snapshot
        return snapshot

    def build_sdk_event_payload(
        self,
        event: AstrMessageEvent,
        *,
        dispatch_token: str,
        plugin_id: str,
        request_id: str,
        overlay: _RequestOverlayState | None,
        raw_updates: dict[str, Any] | None = None,
        field_updates: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot = self.get_or_build_inbound_snapshot(event, overlay)
        sdk_local_extras = dict(overlay.sdk_local_extras) if overlay is not None else {}
        return snapshot.to_payload(
            dispatch_token=dispatch_token,
            plugin_id=plugin_id,
            request_id=request_id,
            host_extras=self.sanitize_host_extras(event),
            sdk_local_extras=sdk_local_extras,
            raw_updates=raw_updates,
            field_updates=field_updates,
        )

    @staticmethod
    def core_provider_request_to_sdk_payload(
        request: CoreProviderRequest,
    ) -> dict[str, Any]:
        tool_calls_result: list[dict[str, Any]] = []
        raw_results = request.tool_calls_result
        if raw_results is not None:
            if not isinstance(raw_results, list):
                raw_results = [raw_results]
            for item in raw_results:
                if not getattr(item, "tool_calls_result", None):
                    continue
                tool_name_by_id: dict[str, str] = {}
                tool_calls_info = getattr(item, "tool_calls_info", None)
                raw_tool_calls = getattr(tool_calls_info, "tool_calls", None)
                if isinstance(raw_tool_calls, list):
                    for tool_call in raw_tool_calls:
                        if isinstance(tool_call, dict):
                            tool_call_id = tool_call.get("id")
                            function_payload = tool_call.get("function")
                            tool_name = (
                                function_payload.get("name")
                                if isinstance(function_payload, dict)
                                else None
                            )
                        else:
                            tool_call_id = getattr(tool_call, "id", None)
                            function_payload = getattr(tool_call, "function", None)
                            tool_name = getattr(function_payload, "name", None)
                        if tool_call_id is None or tool_name is None:
                            continue
                        tool_name_by_id[str(tool_call_id)] = str(tool_name)
                for tool_result in item.tool_calls_result:
                    tool_call_id = getattr(tool_result, "tool_call_id", None)
                    content = getattr(tool_result, "content", "")
                    tool_calls_result.append(
                        {
                            "tool_call_id": str(tool_call_id)
                            if tool_call_id is not None
                            else None,
                            "tool_name": tool_name_by_id.get(str(tool_call_id), "")
                            if tool_call_id is not None
                            else "",
                            "content": str(content or ""),
                            "success": True,
                        }
                    )
        return {
            "prompt": request.prompt,
            "system_prompt": request.system_prompt or None,
            "session_id": request.session_id or None,
            "contexts": copy.deepcopy(request.contexts or []),
            "image_urls": list(request.image_urls or []),
            "tool_calls_result": tool_calls_result,
            "model": request.model,
        }

    @staticmethod
    def apply_sdk_provider_request_payload(
        request: CoreProviderRequest,
        payload: dict[str, Any],
    ) -> None:
        prompt = payload.get("prompt")
        request.prompt = None if prompt is None else str(prompt)
        system_prompt = payload.get("system_prompt")
        request.system_prompt = "" if system_prompt is None else str(system_prompt)
        session_id = payload.get("session_id")
        request.session_id = None if session_id is None else str(session_id)

        contexts = payload.get("contexts")
        if isinstance(contexts, list):
            request.contexts = copy.deepcopy(contexts)

        image_urls = payload.get("image_urls")
        if isinstance(image_urls, list):
            request.image_urls = [str(item) for item in image_urls]

        model = payload.get("model")
        request.model = None if model is None else str(model)

    @staticmethod
    def core_llm_response_to_sdk_payload(
        response: CoreLLMResponse,
    ) -> dict[str, Any]:
        usage_payload = None
        if response.usage is not None:
            usage_payload = {
                "input_tokens": response.usage.input,
                "output_tokens": response.usage.output,
                "total_tokens": response.usage.total,
                "input_cached_tokens": response.usage.input_cached,
            }
        tool_calls: list[dict[str, Any]] = []
        for idx, tool_name in enumerate(response.tools_call_name):
            tool_calls.append(
                {
                    "id": (
                        response.tools_call_ids[idx]
                        if idx < len(response.tools_call_ids)
                        else None
                    ),
                    "name": tool_name,
                    "arguments": (
                        response.tools_call_args[idx]
                        if idx < len(response.tools_call_args)
                        else {}
                    ),
                    "extra_content": (
                        response.tools_call_extra_content.get(
                            response.tools_call_ids[idx]
                        )
                        if idx < len(response.tools_call_ids)
                        else None
                    ),
                }
            )
        return {
            "text": response.completion_text or "",
            "usage": usage_payload,
            "finish_reason": "tool_calls" if tool_calls else "stop",
            "tool_calls": tool_calls,
            "role": response.role,
            "reasoning_content": response.reasoning_content or None,
            "reasoning_signature": response.reasoning_signature,
        }

    @classmethod
    def apply_sdk_result_payload(
        cls,
        result: MessageEventResult,
        payload: dict[str, Any],
    ) -> MessageEventResult:
        chain_payload = payload.get("chain")
        updated = (
            cls.build_core_result_from_chain_payload(chain_payload)
            if isinstance(chain_payload, list)
            else MessageEventResult()
        )
        result.chain = updated.chain
        result.use_t2i_ = updated.use_t2i_
        result.type = updated.type
        if bool(payload.get("stop", False)):
            result.stop_event()
        else:
            result.continue_event()
        return result

    def get_effective_result(
        self, event: AstrMessageEvent
    ) -> MessageEventResult | None:
        dispatch_token = self.get_dispatch_token(event)
        if dispatch_token:
            return self.get_effective_result_for_token(dispatch_token)
        return event._result

    def before_platform_send(self, dispatch_token: str) -> None:
        request_context = self.store.request_contexts.get(dispatch_token)
        if request_context is None:
            raise AstrBotError.invalid_input(
                "Unknown SDK dispatch token for platform send"
            )
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            raise AstrBotError.cancelled("The SDK request overlay has been closed")
        if request_context.cancelled:
            raise AstrBotError.cancelled("The SDK request has been cancelled")

    def mark_platform_send(self, dispatch_token: str) -> str:
        request_context = self.store.request_contexts.get(dispatch_token)
        if request_context is None:
            raise AstrBotError.invalid_input(
                "Unknown SDK dispatch token for platform send"
            )
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            raise AstrBotError.cancelled("The SDK request overlay has been closed")
        if request_context.cancelled:
            raise AstrBotError.cancelled("The SDK request has been cancelled")
        if request_context.dispatch_state is not None:
            request_context.dispatch_state.sent_message = True
        overlay.should_call_llm = False
        if request_context.has_event:
            request_context.event._has_send_oper = True
        return f"sdk_{dispatch_token}"
