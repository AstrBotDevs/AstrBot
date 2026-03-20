from __future__ import annotations

import copy
import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Any

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

    def _provider_entry(
        self,
        payload: dict[str, Any],
        capability_name: str,
        expected_kind: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def _provider_embedding_get_embedding(
        self, request_id: str, payload: dict[str, Any], token
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def _provider_embedding_get_embeddings(
        self, request_id: str, payload: dict[str, Any], token
    ) -> dict[str, Any]:
        raise NotImplementedError
