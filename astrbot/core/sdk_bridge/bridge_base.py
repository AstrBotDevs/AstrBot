from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from astrbot_sdk._internal.invocation_context import current_caller_plugin_id
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.runtime.capability_router import CapabilityRouter

from astrbot.core.file_token_service import FileTokenService
from astrbot.core.message.components import ComponentTypes, Image, Plain
from astrbot.core.message.message_event_result import MessageChain

if TYPE_CHECKING:
    from astrbot.core.star.context import Context as StarContext


def _get_runtime_sp():
    from astrbot.core import sp

    return sp


def _get_runtime_html_renderer():
    from astrbot.core import html_renderer

    return html_renderer


def _get_runtime_astrbot_config():
    from astrbot.core import astrbot_config

    return astrbot_config


def _get_runtime_file_token_service() -> FileTokenService:
    from astrbot.core import file_token_service

    return cast(FileTokenService, file_token_service)


def _get_runtime_tool_types():
    from astrbot.core.agent.tool import FunctionTool, ToolSet

    return FunctionTool, ToolSet


def _get_runtime_provider_types():
    from astrbot.core.provider.provider import (
        EmbeddingProvider,
        RerankProvider,
        STTProvider,
        TTSProvider,
    )

    return STTProvider, TTSProvider, EmbeddingProvider, RerankProvider


@dataclass(slots=True)
class _EventStreamState:
    request_context: Any
    queue: asyncio.Queue[MessageChain | None]
    task: asyncio.Task[None]


class CapabilityBridgeBase(CapabilityRouter):
    MEMORY_SCOPE = "sdk_memory"

    _star_context: StarContext
    _plugin_bridge: Any

    @staticmethod
    def _to_iso_datetime(value: Any) -> str | None:
        if value is None:
            return None
        isoformat = getattr(value, "isoformat", None)
        if callable(isoformat):
            return str(isoformat())
        if isinstance(value, (int, float)) and value > 0:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        return None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_history_items(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, dict)]
        if isinstance(value, str):
            with contextlib.suppress(json.JSONDecodeError, TypeError, ValueError):
                decoded = json.loads(value)
                if isinstance(decoded, list):
                    return [dict(item) for item in decoded if isinstance(item, dict)]
        return []

    @staticmethod
    def _normalize_persona_dialogs(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if isinstance(item, str)]
        if isinstance(value, str):
            with contextlib.suppress(json.JSONDecodeError, TypeError, ValueError):
                decoded = json.loads(value)
                if isinstance(decoded, list):
                    return [str(item) for item in decoded if isinstance(item, str)]
        return []

    @staticmethod
    def _normalize_session_scoped_config(
        raw_config: Any,
        session_id: str,
    ) -> dict[str, Any]:
        if not isinstance(raw_config, dict):
            return {}
        nested = raw_config.get(session_id)
        if isinstance(nested, dict):
            return dict(nested)
        return dict(raw_config)

    def _serialize_persona(self, persona: Any) -> dict[str, Any] | None:
        if persona is None:
            return None
        return {
            "persona_id": str(getattr(persona, "persona_id", "") or ""),
            "system_prompt": str(getattr(persona, "system_prompt", "") or ""),
            "begin_dialogs": self._normalize_persona_dialogs(
                getattr(persona, "begin_dialogs", None)
            ),
            "tools": (
                [str(item) for item in getattr(persona, "tools", [])]
                if isinstance(getattr(persona, "tools", None), list)
                else None
            ),
            "skills": (
                [str(item) for item in getattr(persona, "skills", [])]
                if isinstance(getattr(persona, "skills", None), list)
                else None
            ),
            "custom_error_message": (
                str(getattr(persona, "custom_error_message", ""))
                if getattr(persona, "custom_error_message", None) is not None
                else None
            ),
            "folder_id": (
                str(getattr(persona, "folder_id", ""))
                if getattr(persona, "folder_id", None) is not None
                else None
            ),
            "sort_order": int(getattr(persona, "sort_order", 0) or 0),
            "created_at": self._to_iso_datetime(getattr(persona, "created_at", None)),
            "updated_at": self._to_iso_datetime(getattr(persona, "updated_at", None)),
        }

    def _serialize_conversation(self, conversation: Any) -> dict[str, Any] | None:
        if conversation is None:
            return None
        return {
            "conversation_id": str(getattr(conversation, "cid", "") or ""),
            "session": str(getattr(conversation, "user_id", "") or ""),
            "platform_id": str(getattr(conversation, "platform_id", "") or ""),
            "history": self._normalize_history_items(
                getattr(conversation, "history", None)
            ),
            "title": (
                str(getattr(conversation, "title", ""))
                if getattr(conversation, "title", None) is not None
                else None
            ),
            "persona_id": (
                str(getattr(conversation, "persona_id", ""))
                if getattr(conversation, "persona_id", None) is not None
                else None
            ),
            "created_at": self._to_iso_datetime(
                getattr(conversation, "created_at", None)
            ),
            "updated_at": self._to_iso_datetime(
                getattr(conversation, "updated_at", None)
            ),
            "token_usage": (
                int(getattr(conversation, "token_usage"))
                if getattr(conversation, "token_usage", None) is not None
                else None
            ),
        }

    def _serialize_kb(self, kb_helper_or_record: Any) -> dict[str, Any] | None:
        kb = getattr(kb_helper_or_record, "kb", kb_helper_or_record)
        if kb is None:
            return None
        return {
            "kb_id": str(getattr(kb, "kb_id", "") or ""),
            "kb_name": str(getattr(kb, "kb_name", "") or ""),
            "description": (
                str(getattr(kb, "description", ""))
                if getattr(kb, "description", None) is not None
                else None
            ),
            "emoji": (
                str(getattr(kb, "emoji", ""))
                if getattr(kb, "emoji", None) is not None
                else None
            ),
            "embedding_provider_id": str(
                getattr(kb, "embedding_provider_id", "") or ""
            ),
            "rerank_provider_id": (
                str(getattr(kb, "rerank_provider_id", ""))
                if getattr(kb, "rerank_provider_id", None) is not None
                else None
            ),
            "chunk_size": (
                int(getattr(kb, "chunk_size"))
                if getattr(kb, "chunk_size", None) is not None
                else None
            ),
            "chunk_overlap": (
                int(getattr(kb, "chunk_overlap"))
                if getattr(kb, "chunk_overlap", None) is not None
                else None
            ),
            "top_k_dense": (
                int(getattr(kb, "top_k_dense"))
                if getattr(kb, "top_k_dense", None) is not None
                else None
            ),
            "top_k_sparse": (
                int(getattr(kb, "top_k_sparse"))
                if getattr(kb, "top_k_sparse", None) is not None
                else None
            ),
            "top_m_final": (
                int(getattr(kb, "top_m_final"))
                if getattr(kb, "top_m_final", None) is not None
                else None
            ),
            "doc_count": int(getattr(kb, "doc_count", 0) or 0),
            "chunk_count": int(getattr(kb, "chunk_count", 0) or 0),
            "created_at": self._to_iso_datetime(getattr(kb, "created_at", None)),
            "updated_at": self._to_iso_datetime(getattr(kb, "updated_at", None)),
        }

    @staticmethod
    def _serialize_member(member: Any) -> dict[str, Any] | None:
        if member is None:
            return None
        user_id = getattr(member, "user_id", None)
        if user_id is None and isinstance(member, dict):
            user_id = member.get("user_id")
        if user_id is None:
            return None
        nickname = getattr(member, "nickname", None)
        if nickname is None and isinstance(member, dict):
            nickname = member.get("nickname")
        role = getattr(member, "role", None)
        if role is None and isinstance(member, dict):
            role = member.get("role")
        return {
            "user_id": str(user_id),
            "nickname": str(nickname or ""),
            "role": str(role or ""),
        }

    @classmethod
    def _serialize_group(cls, group: Any) -> dict[str, Any] | None:
        if group is None:
            return None
        members_payload = []
        raw_members = getattr(group, "members", None)
        if raw_members is None:
            raw_members = getattr(group, "member_list", None)
        if raw_members is None and isinstance(group, dict):
            raw_members = group.get("members") or group.get("member_list")
        if isinstance(raw_members, list):
            for member in raw_members:
                serialized_member = cls._serialize_member(member)
                if serialized_member is not None:
                    members_payload.append(serialized_member)
        group_id = getattr(group, "group_id", None)
        if group_id is None and isinstance(group, dict):
            group_id = group.get("group_id")
        group_name = getattr(group, "group_name", None)
        if group_name is None and isinstance(group, dict):
            group_name = group.get("group_name")
        group_avatar = getattr(group, "group_avatar", None)
        if group_avatar is None and isinstance(group, dict):
            group_avatar = group.get("group_avatar")
        group_owner = getattr(group, "group_owner", None)
        if group_owner is None and isinstance(group, dict):
            group_owner = group.get("group_owner")
        group_admins = getattr(group, "group_admins", None)
        if group_admins is None and isinstance(group, dict):
            group_admins = group.get("group_admins")
        return {
            "group_id": str(group_id or ""),
            "group_name": str(group_name or ""),
            "group_avatar": str(group_avatar or ""),
            "group_owner": str(group_owner or ""),
            "group_admins": (
                [str(item) for item in group_admins]
                if isinstance(group_admins, list)
                else []
            ),
            "members": members_payload,
        }

    @staticmethod
    def _serialize_platform_error(error: Any) -> dict[str, Any] | None:
        if error is None:
            return None
        message = getattr(error, "message", None)
        timestamp = getattr(error, "timestamp", None)
        traceback_value = getattr(error, "traceback", None)
        if isinstance(error, dict):
            message = error.get("message", message)
            timestamp = error.get("timestamp", timestamp)
            traceback_value = error.get("traceback", traceback_value)
        if not message:
            return None
        return {
            "message": str(message),
            "timestamp": CapabilityBridgeBase._to_iso_datetime(timestamp)
            or str(timestamp or ""),
            "traceback": (
                str(traceback_value) if traceback_value is not None else None
            ),
        }

    @classmethod
    def _serialize_platform_snapshot(cls, platform: Any) -> dict[str, Any] | None:
        if platform is None:
            return None
        meta = None
        try:
            meta = platform.meta()
        except Exception:
            meta = None
        platform_id = str(
            getattr(meta, "id", None) or getattr(platform, "config", {}).get("id", "")
        ).strip()
        platform_type = str(getattr(meta, "name", "") or "").strip()
        if not platform_id or not platform_type:
            return None
        status = getattr(platform, "status", None)
        errors = getattr(platform, "errors", [])
        status_value = getattr(status, "value", status)
        return {
            "id": platform_id,
            "name": str(getattr(meta, "adapter_display_name", None) or platform_type),
            "type": platform_type,
            "status": str(status_value or "pending"),
            "errors": [
                payload
                for payload in (
                    cls._serialize_platform_error(item)
                    for item in (errors if isinstance(errors, list) else [])
                )
                if payload is not None
            ],
            "last_error": cls._serialize_platform_error(
                getattr(platform, "last_error", None)
            ),
            "unified_webhook": bool(
                platform.unified_webhook()
                if hasattr(platform, "unified_webhook")
                else False
            ),
        }

    @classmethod
    def _serialize_platform_stats(cls, stats: Any) -> dict[str, Any] | None:
        if not isinstance(stats, dict):
            return None
        payload = dict(stats)
        payload["last_error"] = cls._serialize_platform_error(stats.get("last_error"))
        meta = stats.get("meta")
        payload["meta"] = dict(meta) if isinstance(meta, dict) else {}
        return payload

    def _get_platform_inst_by_id(self, platform_id: str) -> Any | None:
        platform_manager = getattr(self._star_context, "platform_manager", None)
        if platform_manager is None or not hasattr(platform_manager, "get_insts"):
            return None
        normalized_platform_id = str(platform_id).strip()
        if not normalized_platform_id:
            return None
        for platform in list(platform_manager.get_insts()):
            meta = None
            try:
                meta = platform.meta()
            except Exception:
                continue
            if str(getattr(meta, "id", "")).strip() == normalized_platform_id:
                return platform
        return None

    def _resolve_plugin_id(self, request_id: str) -> str:
        plugin_id = current_caller_plugin_id()
        if plugin_id:
            return plugin_id
        return self._plugin_bridge.resolve_request_plugin_id(request_id)

    def _reserved_plugin_names(self) -> set[str]:
        reserved: set[str] = set()
        get_all_stars = getattr(self._star_context, "get_all_stars", None)
        if not callable(get_all_stars):
            return reserved
        stars = get_all_stars()
        if not isinstance(stars, Iterable):
            return reserved
        for star in stars:
            name = getattr(star, "name", None)
            if name and bool(getattr(star, "reserved", False)):
                reserved.add(str(name))
        return reserved

    def _require_reserved_plugin(
        self,
        request_id: str,
        capability_name: str,
    ) -> str:
        plugin_id = self._resolve_plugin_id(request_id)
        if plugin_id in {"system", "__system__"}:
            return plugin_id
        if plugin_id in self._reserved_plugin_names():
            return plugin_id
        raise AstrBotError.invalid_input(
            f"{capability_name} is restricted to reserved/system plugins"
        )

    def _resolve_dispatch_target(
        self,
        request_id: str,
        payload: dict[str, Any],
    ) -> tuple[str, str]:
        target_payload = payload.get("target")
        dispatch_token = ""
        if isinstance(target_payload, dict):
            raw_payload = target_payload.get("raw")
            if isinstance(raw_payload, dict):
                dispatch_token = str(raw_payload.get("dispatch_token", ""))
                if not dispatch_token:
                    nested_raw_payload = raw_payload.get("raw")
                    if isinstance(nested_raw_payload, dict):
                        dispatch_token = str(
                            nested_raw_payload.get("dispatch_token", "")
                        )
        if not dispatch_token:
            request_context = self._plugin_bridge.resolve_request_session(request_id)
            if request_context is None:
                raise AstrBotError.invalid_input(
                    "Missing dispatch token for platform send"
                )
            dispatch_token = request_context.dispatch_token
        session = str(payload.get("session", ""))
        return session, dispatch_token

    def _resolve_event_request_context(
        self,
        request_id: str,
        payload: dict[str, Any],
    ):
        target_payload = payload.get("target")
        dispatch_token = ""
        if isinstance(target_payload, dict):
            raw_payload = target_payload.get("raw")
            if isinstance(raw_payload, dict):
                dispatch_token = str(raw_payload.get("dispatch_token", ""))
                if not dispatch_token:
                    nested_raw = raw_payload.get("raw")
                    if isinstance(nested_raw, dict):
                        dispatch_token = str(nested_raw.get("dispatch_token", ""))
        if dispatch_token:
            return self._plugin_bridge.get_request_context_by_token(dispatch_token)
        return self._plugin_bridge.resolve_request_session(request_id)

    def _resolve_current_group_request_context(
        self,
        request_id: str,
        payload: dict[str, Any],
    ):
        request_context = self._resolve_event_request_context(request_id, payload)
        if request_context is None:
            return None
        payload_session = str(payload.get("session", "")).strip()
        if payload_session and payload_session != str(
            request_context.event.unified_msg_origin
        ):
            raise AstrBotError.invalid_input(
                "platform.get_group/get_members only support the current event session"
            )
        return request_context

    @staticmethod
    def _build_core_message_chain(chain_payload: list[dict[str, Any]]) -> MessageChain:
        components = []
        for item in chain_payload:
            if not isinstance(item, dict):
                continue
            comp_type = str(item.get("type", "")).lower()
            data = item.get("data", {})
            if comp_type in {"text", "plain"} and isinstance(data, dict):
                components.append(Plain(str(data.get("text", "")), convert=False))
                continue
            if comp_type == "image" and isinstance(data, dict):
                file_value = str(data.get("file") or data.get("url") or "")
                if file_value.startswith(("http://", "https://")):
                    components.append(Image.fromURL(file_value))
                elif file_value:
                    file_path = (
                        file_value[8:]
                        if file_value.startswith("file:///")
                        else file_value
                    )
                    components.append(Image.fromFileSystem(file_path))
                continue
            component_cls = ComponentTypes.get(comp_type)
            if component_cls is None:
                components.append(
                    Plain(json.dumps(item, ensure_ascii=False), convert=False)
                )
                continue
            try:
                if isinstance(data, dict):
                    components.append(component_cls(**data))
                else:
                    components.append(Plain(str(item), convert=False))
            except Exception:
                components.append(
                    Plain(json.dumps(item, ensure_ascii=False), convert=False)
                )
        return MessageChain(components)
