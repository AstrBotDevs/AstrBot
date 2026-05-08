from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.core.computer.sandbox_models import SandboxRecord
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

_UNSET = object()


def _default_registry_payload() -> dict[str, Any]:
    return {
        "default_sandbox_id": None,
        "sandboxes": {},
        "session_current": {},
    }


class SandboxRegistry:
    def __init__(self, storage_path: str | Path | None = None):
        if storage_path is None:
            storage_path = Path(get_astrbot_data_path()) / "sandbox_registry.json"
        self.storage_path = Path(storage_path)
        self._payload = _default_registry_payload()

    @property
    def default_sandbox_id(self) -> str | None:
        return self._payload["default_sandbox_id"]

    def get_sandbox(self, sandbox_id: str) -> dict[str, Any] | None:
        record = self._payload["sandboxes"].get(sandbox_id)
        return deepcopy(record) if record is not None else None

    def list_sandboxes(self) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._payload["sandboxes"].values()]

    def set_default_sandbox_id(self, sandbox_id: str | None) -> None:
        old_default = self._payload["default_sandbox_id"]
        if old_default and old_default in self._payload["sandboxes"]:
            self._payload["sandboxes"][old_default]["is_default"] = False
        self._payload["default_sandbox_id"] = sandbox_id
        if sandbox_id and sandbox_id in self._payload["sandboxes"]:
            self._payload["sandboxes"][sandbox_id]["is_default"] = True

    def get_current_sandbox_id(self, session_id: str) -> str | None:
        return self._payload["session_current"].get(session_id)

    def set_current_sandbox_id(self, session_id: str, sandbox_id: str | None) -> None:
        if sandbox_id is None:
            self._payload["session_current"].pop(session_id, None)
        else:
            self._payload["session_current"][session_id] = sandbox_id

    def upsert_sandbox(
        self,
        *,
        sandbox_id: str,
        sandbox_name: str,
        booter_type: str,
        provider: str,
        managed: bool,
        created_by_astrbot: bool,
        owner_user_id: str | None,
        owner_session_id: str | None,
        connect_info: dict[str, Any],
        is_default: bool = False,
        status: str | object = _UNSET,
        idle_timeout: int | float | None | object = _UNSET,
        expires_at: float | None | object = _UNSET,
        retention_policy: str | object = _UNSET,
        last_used_at: float | None | object = _UNSET,
        controller_user_id: str | None | object = _UNSET,
        controller_session_id: str | None | object = _UNSET,
        lease_expires_at: float | None | object = _UNSET,
        labels: dict[str, Any] | None | object = _UNSET,
        notes: str | None | object = _UNSET,
    ) -> dict[str, Any]:
        record = self._payload["sandboxes"].get(sandbox_id, {})
        record.update(
            {
                "sandbox_id": sandbox_id,
                "sandbox_name": sandbox_name,
                "booter_type": booter_type,
                "provider": provider,
                "managed": managed,
                "created_by_astrbot": created_by_astrbot,
                "is_default": is_default,
                "owner_user_id": owner_user_id,
                "owner_session_id": owner_session_id,
                "connect_info": deepcopy(connect_info),
            }
        )
        defaults = {
            "controller_user_id": None,
            "controller_session_id": None,
            "lease_expires_at": None,
            "last_used_at": None,
            "idle_timeout": None,
            "expires_at": None,
            "retention_policy": "temporary",
            "status": "running",
            "labels": {},
            "notes": None,
        }
        updates = {
            "controller_user_id": controller_user_id,
            "controller_session_id": controller_session_id,
            "lease_expires_at": lease_expires_at,
            "last_used_at": last_used_at,
            "idle_timeout": idle_timeout,
            "expires_at": expires_at,
            "retention_policy": retention_policy,
            "status": status,
            "labels": deepcopy(labels) if labels is not _UNSET else _UNSET,
            "notes": notes,
        }
        for field_name, default_value in defaults.items():
            value = updates[field_name]
            if value is _UNSET:
                record.setdefault(field_name, deepcopy(default_value))
            else:
                record[field_name] = value
        record = SandboxRecord.from_dict(record).to_dict()
        self._payload["sandboxes"][sandbox_id] = record
        if is_default or (managed and self._payload["default_sandbox_id"] is None):
            self.set_default_sandbox_id(sandbox_id)
        return deepcopy(record)

    def delete_sandbox(self, sandbox_id: str) -> None:
        was_default = self._payload["default_sandbox_id"] == sandbox_id
        self._payload["sandboxes"].pop(sandbox_id, None)
        if was_default:
            self._payload["default_sandbox_id"] = None
            for candidate_id, candidate in self._payload["sandboxes"].items():
                if candidate.get("managed"):
                    self.set_default_sandbox_id(candidate_id)
                    break
        stale_sessions = [
            session_id
            for session_id, current_id in self._payload["session_current"].items()
            if current_id == sandbox_id
        ]
        for session_id in stale_sessions:
            self._payload["session_current"].pop(session_id, None)

    def touch_sandbox(
        self, sandbox_id: str, *, ts: float | None = None
    ) -> dict[str, Any] | None:
        record = self._payload["sandboxes"].get(sandbox_id)
        if record is None:
            return None
        record["last_used_at"] = ts if ts is not None else time.time()
        return deepcopy(record)

    def update_sandbox_config(
        self,
        sandbox_id: str,
        *,
        idle_timeout: int | float | None | object = _UNSET,
        expires_at: int | float | None | object = _UNSET,
        retention_policy: str | object = _UNSET,
    ) -> dict[str, Any] | None:
        record = self._payload["sandboxes"].get(sandbox_id)
        if record is None:
            return None
        if idle_timeout is not _UNSET:
            record["idle_timeout"] = idle_timeout
        if expires_at is not _UNSET:
            record["expires_at"] = expires_at
        if retention_policy is not _UNSET:
            record["retention_policy"] = retention_policy
        return deepcopy(record)

    def update_sandbox_status(
        self, sandbox_id: str, status: str
    ) -> dict[str, Any] | None:
        record = self._payload["sandboxes"].get(sandbox_id)
        if record is None:
            return None
        record["status"] = status
        return deepcopy(record)

    def acquire_lease(
        self,
        *,
        sandbox_id: str,
        session_id: str,
        user_id: str | None,
        ttl: int | float,
        now: float | None = None,
    ) -> bool:
        record = self._payload["sandboxes"].get(sandbox_id)
        if record is None:
            return False
        current_time = time.time() if now is None else now
        controller_session_id = record.get("controller_session_id")
        lease_expires_at = record.get("lease_expires_at")
        if (
            controller_session_id
            and controller_session_id != session_id
            and lease_expires_at
            and lease_expires_at > current_time
        ):
            return False
        record["controller_session_id"] = session_id
        record["controller_user_id"] = user_id
        record["lease_expires_at"] = current_time + float(ttl)
        return True

    def release_lease(self, sandbox_id: str) -> dict[str, Any] | None:
        record = self._payload["sandboxes"].get(sandbox_id)
        if record is None:
            return None
        record["controller_session_id"] = None
        record["controller_user_id"] = None
        record["lease_expires_at"] = None
        return deepcopy(record)

    def takeover_lease(
        self,
        *,
        sandbox_id: str,
        session_id: str,
        user_id: str | None,
        ttl: int | float,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        record = self._payload["sandboxes"].get(sandbox_id)
        if record is None:
            return None
        current_time = time.time() if now is None else now
        record["controller_session_id"] = session_id
        record["controller_user_id"] = user_id
        record["lease_expires_at"] = current_time + float(ttl)
        return deepcopy(record)

    def reconcile_startup(self) -> None:
        for record in self._payload["sandboxes"].values():
            if not record.get("managed"):
                continue
            record["controller_user_id"] = None
            record["controller_session_id"] = None
            record["lease_expires_at"] = None
            if record.get("status") != "stopped":
                record["status"] = "unknown"

    def save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(self._payload, f, ensure_ascii=False, indent=2)

    def load(self) -> None:
        if not self.storage_path.exists():
            self._payload = _default_registry_payload()
            return
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "[Computer] Failed to load sandbox registry %s: %s",
                self.storage_path,
                exc,
            )
            self._payload = _default_registry_payload()
            return
        self._payload = _default_registry_payload()
        self._payload.update(payload)
        sandboxes = self._payload.get("sandboxes", {})
        valid_sandboxes = {}
        for record in sandboxes.values():
            try:
                normalized = SandboxRecord.from_dict(record).to_dict()
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "[Computer] Skip invalid sandbox registry record: %s",
                    exc,
                )
                continue
            record = normalized
            if not record.get("managed"):
                valid_sandboxes[record["sandbox_id"]] = record
                continue
            record["controller_user_id"] = None
            record["controller_session_id"] = None
            record["lease_expires_at"] = None
            valid_sandboxes[record["sandbox_id"]] = record
        self._payload["sandboxes"] = valid_sandboxes
        if self._payload["default_sandbox_id"] not in valid_sandboxes:
            self._payload["default_sandbox_id"] = None
