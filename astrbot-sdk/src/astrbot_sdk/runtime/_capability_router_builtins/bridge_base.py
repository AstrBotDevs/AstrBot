from __future__ import annotations

import copy
import hashlib
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..._internal.plugin_ids import resolve_plugin_data_dir, validate_plugin_id
from ...errors import AstrBotError
from ...protocol.descriptors import (
    BUILTIN_CAPABILITY_SCHEMAS,
    CapabilityDescriptor,
    SessionRef,
)
from ._host import CapabilityRouterHost


def _clone_target_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _clone_chain_payload(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {str(key): item for key, item in chunk.items()}
        for chunk in value
        if isinstance(chunk, dict)
    ]


_MOCK_EMBEDDING_DIM = 24


def _embedding_terms(text: str) -> list[str]:
    """Build stable tokens for the mock embedding implementation."""
    normalized = re.sub(r"\s+", " ", str(text).strip().casefold())
    compact = normalized.replace(" ", "")
    if not normalized:
        return []

    terms = [word for word in re.findall(r"\w+", normalized, flags=re.UNICODE) if word]
    if compact:
        if len(compact) == 1:
            terms.append(compact)
        else:
            terms.extend(
                compact[index : index + 2] for index in range(len(compact) - 1)
            )
            terms.append(compact)
    return terms or [normalized]


def _mock_embedding_vector(text: str, *, provider_id: str) -> list[float]:
    """Generate a deterministic normalized mock embedding vector."""
    values = [0.0] * _MOCK_EMBEDDING_DIM
    for term in _embedding_terms(text):
        digest = hashlib.sha256(f"{provider_id}:{term}".encode()).digest()
        index = int.from_bytes(digest[:2], "big") % _MOCK_EMBEDDING_DIM
        values[index] += 1.0 + min(len(term), 8) * 0.05
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        return values
    return [value / norm for value in values]


class CapabilityRouterBridgeBase(CapabilityRouterHost):
    _memory_backends: dict[str, Any]

    @staticmethod
    def _normalize_platform_name(value: Any) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _normalized_platform_names(cls, values: Any) -> set[str]:
        if not isinstance(values, list):
            return set()
        return {
            cls._normalize_platform_name(item)
            for item in values
            if cls._normalize_platform_name(item)
        }

    @staticmethod
    def _validated_plugin_id(plugin_id: str, *, capability_name: str) -> str:
        try:
            return validate_plugin_id(plugin_id)
        except ValueError as exc:
            raise AstrBotError.invalid_input(
                f"{capability_name} requires a safe plugin_id: {exc}"
            ) from exc

    def _plugin_data_dir(self, plugin_id: str, *, capability_name: str) -> Path:
        try:
            return resolve_plugin_data_dir(self._system_data_root, plugin_id)
        except ValueError as exc:
            raise AstrBotError.invalid_input(
                f"{capability_name} requires a safe plugin_id: {exc}"
            ) from exc

    def _builtin_descriptor(
        self,
        name: str,
        description: str,
        *,
        supports_stream: bool = False,
        cancelable: bool = False,
    ) -> CapabilityDescriptor:
        schema = BUILTIN_CAPABILITY_SCHEMAS[name]
        return CapabilityDescriptor(
            name=name,
            description=description,
            input_schema=copy.deepcopy(schema["input"]),
            output_schema=copy.deepcopy(schema["output"]),
            supports_stream=supports_stream,
            cancelable=cancelable,
        )

    def _resolve_target(
        self, payload: dict[str, Any]
    ) -> tuple[str, dict[str, Any] | None]:
        target_payload = payload.get("target")
        if isinstance(target_payload, dict):
            target = SessionRef.model_validate(target_payload)
            return target.session, target.to_payload()
        return str(payload.get("session", "")), None

    @staticmethod
    def _is_group_session(session: str) -> bool:
        normalized = str(session).lower()
        return ":group:" in normalized or ":groupmessage:" in normalized

    @staticmethod
    def _mock_group_payload(session: str) -> dict[str, Any] | None:
        if not CapabilityRouterBridgeBase._is_group_session(session):
            return None
        members = [
            {
                "user_id": f"{session}:member-1",
                "nickname": "Member 1",
                "role": "member",
            },
            {
                "user_id": f"{session}:member-2",
                "nickname": "Member 2",
                "role": "admin",
            },
        ]
        return {
            "group_id": session.rsplit(":", maxsplit=1)[-1],
            "group_name": f"Mock Group {session.rsplit(':', maxsplit=1)[-1]}",
            "group_avatar": "",
            "group_owner": members[0]["user_id"],
            "group_admins": [members[1]["user_id"]],
            "members": members,
        }

    def _session_plugin_config(self, session: str) -> dict[str, Any]:
        config = self._session_plugin_configs.get(str(session), {})
        return dict(config) if isinstance(config, dict) else {}

    def _session_service_config(self, session: str) -> dict[str, Any]:
        config = self._session_service_configs.get(str(session), {})
        return dict(config) if isinstance(config, dict) else {}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _session_platform_id(session: str) -> str:
        parts = str(session).split(":", maxsplit=1)
        if parts and parts[0].strip():
            return parts[0].strip()
        return "unknown"

    def _plugin_supports_platform(self, plugin_id: str, platform_name: str) -> bool:
        normalized_platform = self._normalize_platform_name(platform_name)
        if not normalized_platform:
            return True
        plugin = self._plugins.get(str(plugin_id))
        if plugin is None:
            return True
        metadata = getattr(plugin, "metadata", None)
        if not isinstance(metadata, dict):
            return True
        supported = self._normalized_platform_names(metadata.get("support_platforms"))
        if not supported:
            return True
        return normalized_platform in supported

    def _platform_name_from_id(self, platform_id: str) -> str:
        normalized_platform_id = str(platform_id).strip()
        if not normalized_platform_id:
            return ""
        for item in self.get_platform_instances():
            if not isinstance(item, dict):
                continue
            if str(item.get("id", "")).strip() != normalized_platform_id:
                continue
            return self._normalize_platform_name(item.get("type"))
        return ""

    def _session_platform_name(self, session: str) -> str:
        return self._platform_name_from_id(self._session_platform_id(session))

    def _require_platform_support_for_session(
        self,
        capability_name: str,
        session: str,
    ) -> str:
        plugin_id = self._require_caller_plugin_id(capability_name)
        platform_name = self._session_platform_name(session)
        if not platform_name or self._plugin_supports_platform(
            plugin_id, platform_name
        ):
            return plugin_id
        raise AstrBotError.invalid_input(
            f"{capability_name} does not support platform '{platform_name}' for plugin '{plugin_id}'"
        )

    @staticmethod
    def _normalize_history_payload(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, dict)]

    @staticmethod
    def _normalize_persona_dialogs_payload(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if isinstance(item, str)]

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
