from __future__ import annotations

import asyncio
import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.core.computer.sandbox_models import SandboxRecord, SandboxStatus
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

_UNSET = object()
_SCHEMA_VERSION = 1


def _default_registry_payload() -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "default_sandbox_id": None,
        "default_sandbox_ids": {},
        "sandboxes": {},
        "session_current": {},
    }


def _coerce_schema_version(value: Any) -> int:
    try:
        version = int(value)
    except (TypeError, ValueError):
        return _SCHEMA_VERSION
    return version if version > 0 else _SCHEMA_VERSION


class SandboxRegistry:
    def __init__(self, storage_path: str | Path | None = None):
        if storage_path is None:
            storage_path = Path(get_astrbot_data_path()) / "sandbox_registry.json"
        self.storage_path = Path(storage_path)
        self._payload = _default_registry_payload()
        self._save_lock = asyncio.Lock()

    @property
    def default_sandbox_id(self) -> str | None:
        return self._payload["default_sandbox_id"]

    def get_default_sandbox_id(self, provider: str) -> str | None:
        sandbox_id = self._payload.get("default_sandbox_ids", {}).get(provider)
        if sandbox_id and sandbox_id in self._payload["sandboxes"]:
            return sandbox_id
        if self._payload["default_sandbox_id"]:
            record = self.get_sandbox(self._payload["default_sandbox_id"])
            if record and record.get("provider") == provider:
                return self._payload["default_sandbox_id"]
        return None

    def get_sandbox(self, sandbox_id: str | None) -> dict[str, Any] | None:
        if sandbox_id is None:
            return None
        record = self._payload["sandboxes"].get(sandbox_id)
        return deepcopy(record) if record is not None else None

    def list_sandboxes(self) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._payload["sandboxes"].values()]

    def set_default_sandbox_id(self, sandbox_id: str | None) -> None:
        old_default = self._payload["default_sandbox_id"]
        self._payload["default_sandbox_id"] = sandbox_id
        if sandbox_id and sandbox_id in self._payload["sandboxes"]:
            record = self._payload["sandboxes"][sandbox_id]
            provider = record.get("provider")
            if provider:
                old_provider_default = self._payload.setdefault(
                    "default_sandbox_ids", {}
                ).get(provider)
                if (
                    old_provider_default
                    and old_provider_default in self._payload["sandboxes"]
                ):
                    self._payload["sandboxes"][old_provider_default]["is_default"] = (
                        False
                    )
                self._payload["default_sandbox_ids"][provider] = sandbox_id
            record["is_default"] = True
        elif old_default and old_default in self._payload["sandboxes"]:
            self._payload["sandboxes"][old_default]["is_default"] = False

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
        provider: str,
        managed: bool,
        created_by_astrbot: bool,
        owner_user_id: str | None,
        owner_session_id: str | None,
        connect_info: dict[str, Any],
        is_default: bool | object = _UNSET,
        status: str | object = _UNSET,
        idle_timeout: int | float | None | object = _UNSET,
        expires_at: float | None | object = _UNSET,
        retention_policy: str | object = _UNSET,
        last_used_at: float | None | object = _UNSET,
        controller_user_id: str | None | object = _UNSET,
        controller_session_id: str | None | object = _UNSET,
        lease_expires_at: float | None | object = _UNSET,
        labels: dict[str, Any] | None | object = _UNSET,
        capabilities: list[str] | set[str] | None | object = _UNSET,
        tool_names: list[str] | set[str] | None | object = _UNSET,
        notes: str | None | object = _UNSET,
    ) -> dict[str, Any]:
        record = self._payload["sandboxes"].get(sandbox_id, {})
        record.update(
            {
                "sandbox_id": sandbox_id,
                "sandbox_name": sandbox_name,
                "provider": provider,
                "managed": managed,
                "created_by_astrbot": created_by_astrbot,
                "owner_user_id": owner_user_id,
                "owner_session_id": owner_session_id,
                "created_by_user_id": owner_user_id,
                "created_by_session_id": owner_session_id,
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
            "is_default": False,
            "labels": {},
            "capabilities": [],
            "tool_names": [],
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
            "is_default": is_default,
            "labels": deepcopy(labels) if labels is not _UNSET else _UNSET,
            "capabilities": sorted(capabilities)
            if capabilities is not _UNSET
            else _UNSET,
            "tool_names": sorted(tool_names) if tool_names is not _UNSET else _UNSET,
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
        if is_default is True or (
            managed and self._payload["default_sandbox_id"] is None
        ):
            self.set_default_sandbox_id(sandbox_id)
        return deepcopy(record)

    def delete_sandbox(self, sandbox_id: str) -> None:
        was_default = self._payload["default_sandbox_id"] == sandbox_id
        deleted = self._payload["sandboxes"].pop(sandbox_id, None)
        if deleted:
            provider = deleted.get("provider")
            if (
                provider
                and self._payload.get("default_sandbox_ids", {}).get(provider)
                == sandbox_id
            ):
                self._payload["default_sandbox_ids"].pop(provider, None)
                for candidate_id, candidate in self._payload["sandboxes"].items():
                    if (
                        candidate.get("managed")
                        and candidate.get("provider") == provider
                    ):
                        self.set_default_sandbox_id(candidate_id)
                        break
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
        sandbox_name: str | object = _UNSET,
        connect_info: dict[str, Any] | object = _UNSET,
        idle_timeout: int | float | None | object = _UNSET,
        expires_at: int | float | None | object = _UNSET,
        retention_policy: str | object = _UNSET,
    ) -> dict[str, Any] | None:
        record = self._payload["sandboxes"].get(sandbox_id)
        if record is None:
            return None
        if sandbox_name is not _UNSET:
            name = str(sandbox_name).strip()
            if not name:
                raise ValueError("sandbox_name must be a non-empty string")
            record["sandbox_name"] = name
        if connect_info is not _UNSET:
            record["connect_info"] = deepcopy(connect_info)
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
        record["status"] = getattr(status, "value", status)
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
        record["lease_expires_at"] = current_time + ttl
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
        record["lease_expires_at"] = current_time + ttl
        return deepcopy(record)

    def reconcile_startup(self) -> None:
        self._payload["session_current"] = {}
        for sandbox_id, record in list(self._payload["sandboxes"].items()):
            record["controller_session_id"] = None
            record["controller_user_id"] = None
            record["lease_expires_at"] = None
            if record.get("retention_policy") == "persistent":
                if record.get("status") == SandboxStatus.RUNNING:
                    record["status"] = SandboxStatus.UNKNOWN.value
                elif record.get("status") == SandboxStatus.CREATING:
                    record["status"] = SandboxStatus.ERROR.value
            elif record.get("status") in {
                SandboxStatus.RUNNING,
                SandboxStatus.CREATING,
                SandboxStatus.UNKNOWN,
            }:
                record["status"] = SandboxStatus.ERROR.value
        self._prune_default_references()

    def _prune_default_references(self) -> None:
        sandboxes = self._payload["sandboxes"]
        default_sandbox_id = self._payload.get("default_sandbox_id")
        if default_sandbox_id not in sandboxes:
            self._payload["default_sandbox_id"] = None
        default_sandbox_ids = self._payload.get("default_sandbox_ids") or {}
        valid_default_sandbox_ids = {
            provider: sandbox_id
            for provider, sandbox_id in default_sandbox_ids.items()
            if sandbox_id in sandboxes
            and sandboxes[sandbox_id].get("provider") == provider
        }
        self._payload["default_sandbox_ids"] = valid_default_sandbox_ids
        for record in sandboxes.values():
            record["is_default"] = False
        if self._payload["default_sandbox_id"]:
            sandboxes[self._payload["default_sandbox_id"]]["is_default"] = True
        for sandbox_id in valid_default_sandbox_ids.values():
            if sandbox_id in sandboxes:
                sandboxes[sandbox_id]["is_default"] = True

    def load(self) -> None:
        if not self.storage_path.exists():
            self._payload = _default_registry_payload()
            return
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load sandbox registry: %s", exc)
            self._payload = _default_registry_payload()
            return
        if not isinstance(payload, dict):
            logger.warning("Failed to load sandbox registry: payload is not an object")
            self._payload = _default_registry_payload()
            return
        self._payload = _default_registry_payload()
        self._payload["schema_version"] = _coerce_schema_version(
            payload.get("schema_version")
        )
        self._payload.update({key: payload.get(key) for key in self._payload})
        self._payload["schema_version"] = _coerce_schema_version(
            self._payload.get("schema_version")
        )
        self._payload["default_sandbox_ids"] = dict(
            self._payload.get("default_sandbox_ids") or {}
        )
        self._payload["sandboxes"] = dict(self._payload.get("sandboxes") or {})
        self._payload["session_current"] = dict(
            self._payload.get("session_current") or {}
        )

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.storage_path.with_name(
            f"{self.storage_path.name}.{time.time_ns()}.tmp"
        )
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temp_path.replace(self.storage_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def save(self) -> None:
        self._write_payload(deepcopy(self._payload))

    async def save_async(self) -> None:
        async with self._save_lock:
            payload = deepcopy(self._payload)
            await asyncio.to_thread(self._write_payload, payload)
