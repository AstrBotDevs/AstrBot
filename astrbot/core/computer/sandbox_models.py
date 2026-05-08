from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SandboxRetentionPolicy(StrEnum):
    TEMPORARY = "temporary"
    PERSISTENT = "persistent"


class SandboxStatus(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class SandboxRecord:
    sandbox_id: str
    sandbox_name: str
    booter_type: str
    provider: str
    managed: bool
    created_by_astrbot: bool
    is_default: bool = False
    owner_user_id: str | None = None
    owner_session_id: str | None = None
    controller_user_id: str | None = None
    controller_session_id: str | None = None
    lease_expires_at: float | None = None
    last_used_at: float | None = None
    idle_timeout: int | float | None = None
    expires_at: float | None = None
    retention_policy: SandboxRetentionPolicy = SandboxRetentionPolicy.TEMPORARY
    status: SandboxStatus = SandboxStatus.RUNNING
    connect_info: dict[str, Any] = field(default_factory=dict)
    labels: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None

    @staticmethod
    def _required_string(data: dict[str, Any], field_name: str) -> str:
        value = data[field_name]
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a non-empty string")
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must be a non-empty string")
        return value

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SandboxRecord:
        return cls(
            sandbox_id=cls._required_string(data, "sandbox_id"),
            sandbox_name=cls._required_string(data, "sandbox_name"),
            booter_type=cls._required_string(data, "booter_type"),
            provider=cls._required_string(data, "provider"),
            managed=bool(data["managed"]),
            created_by_astrbot=bool(data["created_by_astrbot"]),
            is_default=bool(data.get("is_default", False)),
            owner_user_id=data.get("owner_user_id"),
            owner_session_id=data.get("owner_session_id"),
            controller_user_id=data.get("controller_user_id"),
            controller_session_id=data.get("controller_session_id"),
            lease_expires_at=data.get("lease_expires_at"),
            last_used_at=data.get("last_used_at"),
            idle_timeout=data.get("idle_timeout"),
            expires_at=data.get("expires_at"),
            retention_policy=SandboxRetentionPolicy(
                data.get("retention_policy", SandboxRetentionPolicy.TEMPORARY)
            ),
            status=SandboxStatus(data.get("status", SandboxStatus.RUNNING)),
            connect_info=dict(data.get("connect_info") or {}),
            labels=dict(data.get("labels") or {}),
            notes=data.get("notes"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "sandbox_name": self.sandbox_name,
            "booter_type": self.booter_type,
            "provider": self.provider,
            "managed": self.managed,
            "created_by_astrbot": self.created_by_astrbot,
            "is_default": self.is_default,
            "owner_user_id": self.owner_user_id,
            "owner_session_id": self.owner_session_id,
            "controller_user_id": self.controller_user_id,
            "controller_session_id": self.controller_session_id,
            "lease_expires_at": self.lease_expires_at,
            "last_used_at": self.last_used_at,
            "idle_timeout": self.idle_timeout,
            "expires_at": self.expires_at,
            "retention_policy": self.retention_policy.value,
            "status": self.status.value,
            "connect_info": dict(self.connect_info),
            "labels": dict(self.labels),
            "notes": self.notes,
        }

    def has_active_lease(self, *, now: float | None = None) -> bool:
        current_time = time.time() if now is None else now
        return bool(
            self.controller_session_id
            and self.lease_expires_at
            and self.lease_expires_at > current_time
        )

    def is_controlled_by(self, session_id: str, *, now: float | None = None) -> bool:
        return self.controller_session_id == session_id and self.has_active_lease(
            now=now
        )
