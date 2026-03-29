from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from astrbot.core import logger
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.message.message_types import sdk_message_type
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse as CoreLLMResponse
from astrbot.core.provider.entities import ProviderRequest as CoreProviderRequest

from .event_payload import extract_sdk_handler_result
from .runtime_store import (
    SdkDispatchResult,
    SdkPluginRecord,
    _DispatchState,
    _InFlightRequest,
    _RequestContext,
)

if TYPE_CHECKING:
    from .plugin_bridge import SdkPluginBridge


class SdkDispatchEngine:
    def __init__(self, *, bridge: SdkPluginBridge) -> None:
        self.bridge = bridge

    async def dispatch_message(self, event: AstrMessageEvent) -> SdkDispatchResult:
        result = SdkDispatchResult()
        if event.is_stopped():
            result.skipped_reason = self.bridge.SKIP_LEGACY_STOPPED
            return result
        if self.bridge._legacy_has_replied(event):
            result.skipped_reason = self.bridge.SKIP_LEGACY_REPLIED
            return result

        waiter_plugins = self.bridge._match_waiter_plugins(event.unified_msg_origin)
        if waiter_plugins:
            return await self.dispatch_waiter_event(event, waiter_plugins)

        dispatch_token = self.bridge.get_or_bind_dispatch_token(event)
        overlay = self.bridge._ensure_request_overlay(
            dispatch_token,
            # 使用统一方法获取 LLM 意愿，避免到处重复 not event.call_llm 的反转逻辑
            should_call_llm=self.bridge.get_effective_should_call_llm(event),
        )
        matches = self.bridge._match_handlers(event)
        permission_denied = self.bridge._resolve_command_permission_denied(event)
        if permission_denied is not None and not self.bridge._has_command_trigger_match(
            matches
        ):
            dispatch_state = _DispatchState(event=event)
            request_context = self.bridge._request_contexts.get(dispatch_token)
            if request_context is None:
                request_context = _RequestContext(
                    plugin_id=permission_denied["plugin_id"],
                    request_id="",
                    dispatch_token=dispatch_token,
                    dispatch_state=dispatch_state,
                )
                self.bridge._request_contexts[dispatch_token] = request_context
            else:
                request_context.plugin_id = permission_denied["plugin_id"]
                request_context.dispatch_state = dispatch_state
            self.bridge._set_sdk_origin_plugin_id(event, permission_denied["plugin_id"])
            event.set_result(MessageEventResult().message(permission_denied["message"]))
            event.stop_event()
            self.bridge.request_runtime._set_event_default_llm_blocked(
                event,
                blocked=True,
            )
            overlay.should_call_llm = False
            result.stopped = True
            return result
        group_fallback = self.bridge._resolve_group_root_fallback(event)
        if group_fallback is not None and not self.bridge._has_command_trigger_match(
            matches
        ):
            dispatch_state = _DispatchState(event=event)
            request_context = self.bridge._request_contexts.get(dispatch_token)
            if request_context is None:
                request_context = _RequestContext(
                    plugin_id=group_fallback["plugin_id"],
                    request_id="",
                    dispatch_token=dispatch_token,
                    dispatch_state=dispatch_state,
                )
                self.bridge._request_contexts[dispatch_token] = request_context
            else:
                request_context.plugin_id = group_fallback["plugin_id"]
                request_context.dispatch_state = dispatch_state
            self.bridge._set_sdk_origin_plugin_id(event, group_fallback["plugin_id"])
            event.set_result(MessageEventResult().message(group_fallback["help_text"]))
            event.stop_event()
            # 群组 fallback（如帮助文本）不应触发 LLM，直接阻止
            self.bridge.request_runtime._set_event_default_llm_blocked(
                event,
                blocked=True,
            )
            overlay.should_call_llm = False
            result.stopped = True
            return result
        if not matches:
            result.skipped_reason = self.bridge.SKIP_NO_MATCH
            return result
        result.matched_handlers = [
            {"plugin_id": match.plugin_id, "handler_id": match.handler_id}
            for match in matches
        ]

        dispatch_state = _DispatchState(event=event)
        request_context = self.bridge._request_contexts.get(dispatch_token)
        if request_context is None:
            request_context = _RequestContext(
                plugin_id="",
                request_id="",
                dispatch_token=dispatch_token,
                dispatch_state=dispatch_state,
            )
            self.bridge._request_contexts[dispatch_token] = request_context
        else:
            request_context.dispatch_state = dispatch_state
        skipped_reason = None
        for match in matches:
            whitelist = (
                None
                if overlay.handler_whitelist is None
                else set(overlay.handler_whitelist)
            )
            if whitelist is not None and match.plugin_id not in whitelist:
                continue
            record = self.bridge._records.get(match.plugin_id)
            if record is None:
                continue
            if record.state == self.bridge.SDK_STATE_RELOADING:
                skipped_reason = skipped_reason or self.bridge.SKIP_SDK_RELOADING
                continue
            if (
                record.state
                in {self.bridge.SDK_STATE_FAILED, self.bridge.SDK_STATE_DISABLED}
                or record.session is None
            ):
                skipped_reason = skipped_reason or self.bridge.SKIP_WORKER_FAILED
                continue

            request_id = f"sdk_{record.plugin_id}_{uuid.uuid4().hex}"
            request_context.plugin_id = record.plugin_id
            request_context.request_id = request_id
            request_context.cancelled = False
            self.bridge._set_sdk_origin_plugin_id(event, record.plugin_id)
            setattr(event, "_sdk_last_request_id", request_id)
            payload = self.bridge.build_sdk_event_payload(
                event,
                dispatch_token=dispatch_token,
                plugin_id=record.plugin_id,
                request_id=request_id,
                overlay=overlay,
            )
            task = asyncio.create_task(
                record.session.invoke_handler(
                    match.handler_id,
                    payload,
                    request_id=request_id,
                    args=match.args,
                )
            )
            self.bridge._track_request_scope(
                dispatch_token=dispatch_token,
                request_id=request_id,
                plugin_id=record.plugin_id,
            )
            self.bridge._plugin_requests.setdefault(record.plugin_id, {})[
                request_id
            ] = _InFlightRequest(
                request_id=request_id,
                dispatch_token=dispatch_token,
                task=task,
            )
            try:
                output = await task
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "SDK handler failed: plugin=%s handler=%s error=%s",
                    record.plugin_id,
                    match.handler_id,
                    exc,
                )
                skipped_reason = skipped_reason or self.bridge.SKIP_WORKER_FAILED
                output = {}
            finally:
                inflight = self.bridge._plugin_requests.get(record.plugin_id, {}).pop(
                    request_id,
                    None,
                )

            if inflight is not None and inflight.logical_cancelled:
                continue

            handler_result = extract_sdk_handler_result(
                output if isinstance(output, dict) else {}
            )
            if isinstance(output, dict) and "sdk_local_extras" in output:
                self.bridge._persist_sdk_local_extras_from_handler(
                    overlay,
                    output.get("sdk_local_extras"),
                    plugin_id=record.plugin_id,
                    handler_id=match.handler_id,
                )
            result.executed_handlers.append(
                {"plugin_id": record.plugin_id, "handler_id": match.handler_id}
            )
            dispatch_state.sent_message = (
                dispatch_state.sent_message or handler_result["sent_message"]
            )
            dispatch_state.stopped = dispatch_state.stopped or handler_result["stop"]
            if handler_result["call_llm"]:
                overlay.requested_llm = True
                overlay.should_call_llm = True
            if handler_result["sent_message"] or handler_result["stop"]:
                overlay.should_call_llm = False
            if handler_result["stop"]:
                break

        result.sent_message = dispatch_state.sent_message
        result.stopped = dispatch_state.stopped
        if not result.executed_handlers:
            result.skipped_reason = skipped_reason or self.bridge.SKIP_NO_MATCH
        if result.sent_message:
            # 已发送消息：同步标记 event 和 overlay 的发送状态，防止 LLM 重复回复
            self.bridge.request_runtime._mark_event_send_operation(event)
            overlay.should_call_llm = False
            self.bridge.request_runtime._set_event_default_llm_blocked(
                event,
                blocked=True,
            )
        if result.stopped:
            event.stop_event()
            # 事件被 stop 后 LLM 不应再处理，双重写入 overlay 和 event
            overlay.should_call_llm = False
            self.bridge.request_runtime._set_event_default_llm_blocked(
                event,
                blocked=True,
            )
        return result

    async def dispatch_system_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        normalized_platform = self.bridge._normalize_platform_name(
            (payload or {}).get("platform")
        )
        event_payload = {
            "type": event_type,
            "event_type": event_type,
            "text": str((payload or {}).get("message_outline", "")),
            "session_id": str((payload or {}).get("session_id", "")),
            "platform": str((payload or {}).get("platform", "")),
            "platform_id": str((payload or {}).get("platform_id", "")),
            "message_type": sdk_message_type((payload or {}).get("message_type", "")),
            "sender_name": str((payload or {}).get("sender_name", "")),
            "self_id": str((payload or {}).get("self_id", "")),
            "raw": {"event_type": event_type, **(payload or {})},
        }
        for key, value in (payload or {}).items():
            event_payload[key] = value
        matches = self.bridge._match_event_handlers(
            event_type,
            platform_name=normalized_platform,
        )
        for record, descriptor in matches:
            if record.session is None:
                continue
            try:
                await record.session.invoke_handler(
                    descriptor.id,
                    event_payload,
                    request_id=f"sdk_event_{record.plugin_id}_{uuid.uuid4().hex}",
                    args={},
                )
            except Exception as exc:
                logger.warning(
                    "SDK event handler failed: plugin=%s handler=%s error=%s",
                    record.plugin_id,
                    descriptor.id,
                    exc,
                )

    async def dispatch_message_event(
        self,
        event_type: str,
        event: AstrMessageEvent,
        payload: dict[str, Any] | None = None,
        *,
        provider_request: CoreProviderRequest | None = None,
        llm_response: CoreLLMResponse | None = None,
        event_result: MessageEventResult | None = None,
    ) -> None:
        dispatch_token = self.bridge._get_dispatch_token(event)
        if not dispatch_token:
            return
        overlay = self.bridge.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return
        normalized_platform = self.bridge._normalize_platform_name(
            event.get_platform_name()
        )
        matches = self.bridge._match_event_handlers(
            event_type,
            allowed_plugins=overlay.handler_whitelist,
            platform_name=normalized_platform,
        )
        for record, descriptor in matches:
            if record.session is None:
                continue
            request_id = f"sdk_event_{record.plugin_id}_{uuid.uuid4().hex}"
            request_context = self.bridge._request_contexts.get(dispatch_token)
            if request_context is None:
                request_context = _RequestContext(
                    plugin_id=record.plugin_id,
                    request_id=request_id,
                    dispatch_token=dispatch_token,
                    dispatch_state=_DispatchState(event=event),
                )
                self.bridge._request_contexts[dispatch_token] = request_context
            request_context.plugin_id = record.plugin_id
            request_context.request_id = request_id
            if request_context.dispatch_state is None:
                request_context.dispatch_state = _DispatchState(event=event)
            request_context.dispatch_state.event = event
            request_context.cancelled = False
            self.bridge._track_request_scope(
                dispatch_token=dispatch_token,
                request_id=request_id,
                plugin_id=record.plugin_id,
            )
            event_payload = self.bridge.build_sdk_event_payload(
                event,
                dispatch_token=dispatch_token,
                plugin_id=record.plugin_id,
                request_id=request_id,
                overlay=overlay,
                raw_updates={"event_type": event_type, **(payload or {})},
                field_updates={
                    "type": event_type,
                    "event_type": event_type,
                    **(payload or {}),
                },
            )
            if provider_request is not None:
                request_payload = self.bridge._core_provider_request_to_sdk_payload(
                    provider_request
                )
                event_payload["provider_request"] = request_payload
                if isinstance(event_payload["raw"], dict):
                    event_payload["raw"]["provider_request"] = request_payload
            if llm_response is not None:
                response_payload = self.bridge._core_llm_response_to_sdk_payload(
                    llm_response
                )
                event_payload["llm_response"] = response_payload
                if isinstance(event_payload["raw"], dict):
                    event_payload["raw"]["llm_response"] = response_payload
            if event_result is not None:
                result_payload = self.bridge._legacy_result_to_sdk_payload(event_result)
                if result_payload is not None:
                    event_payload["event_result"] = result_payload
                    if isinstance(event_payload["raw"], dict):
                        event_payload["raw"]["event_result"] = result_payload
            try:
                output = await record.session.invoke_handler(
                    descriptor.id,
                    event_payload,
                    request_id=request_id,
                    args={},
                )
                if isinstance(output, dict):
                    handler_result = extract_sdk_handler_result(output)
                    if "sdk_local_extras" in output:
                        self.bridge._persist_sdk_local_extras_from_handler(
                            overlay,
                            output.get("sdk_local_extras"),
                            plugin_id=record.plugin_id,
                            handler_id=descriptor.id,
                        )
                    request_payload = output.get("provider_request")
                    if provider_request is not None and isinstance(
                        request_payload, dict
                    ):
                        self.bridge._apply_sdk_provider_request_payload(
                            provider_request,
                            request_payload,
                        )
                    result_payload = output.get("event_result")
                    if event_result is not None and isinstance(result_payload, dict):
                        if not self.bridge.set_result_for_request(
                            request_id,
                            result_payload,
                        ):
                            self.bridge._apply_sdk_result_payload(
                                event_result,
                                result_payload,
                            )
                    if handler_result["stop"]:
                        event.stop_event()
                    if handler_result["call_llm"]:
                        overlay.requested_llm = True
                        overlay.should_call_llm = True
                    if handler_result["sent_message"]:
                        # 系统事件处理中发送了消息，标记到 event 供后续 pipeline 判断
                        self.bridge.request_runtime._mark_event_send_operation(event)
                    if handler_result["sent_message"] or handler_result["stop"]:
                        overlay.should_call_llm = False
            except Exception as exc:
                logger.warning(
                    "SDK event handler failed: plugin=%s handler=%s error=%s",
                    record.plugin_id,
                    descriptor.id,
                    exc,
                )

    async def dispatch_waiter_event(
        self,
        event: AstrMessageEvent,
        records: list[SdkPluginRecord],
    ) -> SdkDispatchResult:
        result = SdkDispatchResult()
        dispatch_state = _DispatchState(event=event)
        dispatch_token = self.bridge.get_or_bind_dispatch_token(event)
        overlay = self.bridge._ensure_request_overlay(
            dispatch_token,
            should_call_llm=self.bridge.get_effective_should_call_llm(event),
        )
        request_context = _RequestContext(
            plugin_id="",
            request_id="",
            dispatch_token=dispatch_token,
            dispatch_state=dispatch_state,
        )
        self.bridge._request_contexts[dispatch_token] = request_context
        for record in records:
            if record.state in {
                self.bridge.SDK_STATE_DISABLED,
                self.bridge.SDK_STATE_FAILED,
                self.bridge.SDK_STATE_RELOADING,
            }:
                continue
            if record.session is None:
                continue
            whitelist = (
                None
                if overlay.handler_whitelist is None
                else set(overlay.handler_whitelist)
            )
            if whitelist is not None and record.plugin_id not in whitelist:
                continue
            request_id = f"sdk_waiter_{record.plugin_id}_{uuid.uuid4().hex}"
            request_context.plugin_id = record.plugin_id
            request_context.request_id = request_id
            request_context.cancelled = False
            self.bridge._set_sdk_origin_plugin_id(event, record.plugin_id)
            setattr(event, "_sdk_last_request_id", request_id)
            payload = self.bridge.build_sdk_event_payload(
                event,
                dispatch_token=dispatch_token,
                plugin_id=record.plugin_id,
                request_id=request_id,
                overlay=overlay,
            )
            self.bridge._track_request_scope(
                dispatch_token=dispatch_token,
                request_id=request_id,
                plugin_id=record.plugin_id,
            )
            try:
                output = await record.session.invoke_handler(
                    "__sdk_session_waiter__",
                    payload,
                    request_id=request_id,
                    args={},
                )
            except Exception as exc:
                logger.warning(
                    "SDK waiter dispatch failed: plugin=%s error=%s",
                    record.plugin_id,
                    exc,
                )
                output = {}
            handler_result = extract_sdk_handler_result(
                output if isinstance(output, dict) else {}
            )
            if isinstance(output, dict) and "sdk_local_extras" in output:
                self.bridge._persist_sdk_local_extras_from_handler(
                    overlay,
                    output.get("sdk_local_extras"),
                    plugin_id=record.plugin_id,
                    handler_id="__sdk_session_waiter__",
                )
            result.executed_handlers.append(
                {"plugin_id": record.plugin_id, "handler_id": "__sdk_session_waiter__"}
            )
            dispatch_state.sent_message = (
                dispatch_state.sent_message or handler_result["sent_message"]
            )
            dispatch_state.stopped = dispatch_state.stopped or handler_result["stop"]
            if handler_result["call_llm"]:
                overlay.requested_llm = True
                overlay.should_call_llm = True
            if handler_result["sent_message"] or handler_result["stop"]:
                overlay.should_call_llm = False
            if handler_result["stop"]:
                break
        result.sent_message = dispatch_state.sent_message
        result.stopped = dispatch_state.stopped
        if not result.executed_handlers:
            result.skipped_reason = self.bridge.SKIP_NO_MATCH
        if result.sent_message:
            # waiter dispatch 同样需要同步发送状态到 event，供后续 pipeline 阶段判断
            self.bridge.request_runtime._mark_event_send_operation(event)
            overlay.should_call_llm = False
            self.bridge.request_runtime._set_event_default_llm_blocked(
                event,
                blocked=True,
            )
        if result.stopped:
            event.stop_event()
            overlay.should_call_llm = False
            self.bridge.request_runtime._set_event_default_llm_blocked(
                event,
                blocked=True,
            )
        return result
