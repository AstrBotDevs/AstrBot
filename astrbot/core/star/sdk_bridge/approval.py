"""Host-side capability governance (`declared ∩ approved`) for SDK plugins."""

from __future__ import annotations

import hashlib
from collections.abc import Collection
from pathlib import Path
from typing import Any

from astrbot_sdk.capabilities import (
    DEFAULT_CAPABILITY_IDS,
    CapabilityGrant,
    CapabilitySet,
)
from astrbot_sdk.errors import CapabilityDenied
from astrbot_sdk.runtime.metadata import CapabilityDeclarations

_APPROVALS_SP_KEY = "sdk_plugin_capability_approvals"


def compute_package_fingerprint(plugin_root: Path) -> str:
    """Compute a deterministic SHA-256 fingerprint of a plugin package tree.

    Args:
        plugin_root: Root directory of the installed plugin.

    Returns:
        Hexadecimal SHA-256 digest string.
    """
    if not plugin_root.is_dir():
        return ""
    hasher = hashlib.sha256()
    for path in sorted(plugin_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(plugin_root).as_posix()
        if any(
            part in {"__pycache__", ".pytest_cache", ".git", "target"}
            for part in path.parts
        ):
            continue
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(path.read_bytes())
        hasher.update(b"\n")
    return hasher.hexdigest()


class CapabilityApprovalStore:
    """Persist approved capability sets keyed by plugin ID and package digest."""

    def __init__(self, sp_backend: Any = None) -> None:
        self._sp_backend = sp_backend

    def _sp(self) -> Any:
        if self._sp_backend is not None:
            return self._sp_backend
        from astrbot.core.star.sdk_bridge import bridge as bridge_module

        return bridge_module.sp

    async def _load_all(self) -> dict[str, dict[str, Any]]:
        raw = await self._sp().global_get(_APPROVALS_SP_KEY, {})
        if not isinstance(raw, dict):
            return {}
        return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}

    async def _save_all(self, data: dict[str, dict[str, Any]]) -> None:
        await self._sp().global_put(_APPROVALS_SP_KEY, data)

    async def get_record(self, plugin_id: str) -> dict[str, Any] | None:
        """Return persisted approval record for `plugin_id`, if present."""
        all_records = await self._load_all()
        return all_records.get(plugin_id)

    async def set_approved(
        self,
        plugin_id: str,
        approved_ids: Collection[str],
        *,
        fingerprint: str = "",
    ) -> set[str]:
        """Persist explicit Host capability approvals for one plugin."""
        normalized = sorted({str(cap) for cap in approved_ids if cap})
        records = await self._load_all()
        existing = records.get(plugin_id, {})
        records[plugin_id] = {
            "approved": normalized,
            "fingerprint": fingerprint or str(existing.get("fingerprint") or ""),
        }
        await self._save_all(records)
        return set(normalized)

    async def revoke(self, plugin_id: str) -> None:
        """Remove saved approvals for an uninstalled plugin."""
        records = await self._load_all()
        if plugin_id in records:
            records.pop(plugin_id, None)
            await self._save_all(records)

    async def resolve_grants(
        self,
        plugin_id: str,
        declared: CapabilityDeclarations,
        *,
        fingerprint: str = "",
        explicit_scopes: CapabilitySet | None = None,
        auto_approve_declared: bool = True,
    ) -> CapabilitySet:
        """Intersect manifest-declared capabilities with Host-approved grants.

        Args:
            plugin_id: Unique plugin identifier.
            declared: Manifest capability declarations (`required` + `optional`).
            fingerprint: Current package SHA-256 fingerprint.
            explicit_scopes: Optional pre-built CapabilitySet carrying grant scopes.
            auto_approve_declared: Auto-approve declared capabilities on initial install.

        Returns:
            Effective `CapabilitySet` granted to the plugin.

        Raises:
            CapabilityDenied: A `required` capability has not been approved.
        """
        records = await self._load_all()
        record = records.get(plugin_id)
        declared_ids = set(declared.all_ids)

        if record is None:
            if not auto_approve_declared:
                approved_ids: set[str] = set()
            else:
                approved_ids = set(declared_ids)
                records[plugin_id] = {
                    "approved": sorted(approved_ids),
                    "fingerprint": fingerprint,
                }
                await self._save_all(records)
        else:
            approved_ids = {str(item) for item in record.get("approved") or ()}
            old_fp = str(record.get("fingerprint") or "")
            # Same-fingerprint unchanged package keeps its approved set. On
            # package upgrade with new capabilities, unapproved additions stay
            # denied until approved by the operator.
            if (
                old_fp == fingerprint
                and auto_approve_declared
                and not record.get("explicit")
                and declared_ids.issubset(approved_ids)
            ):
                pass

        effective_ids = declared_ids & approved_ids
        missing_required = sorted(set(declared.required_ids) - effective_ids)
        if missing_required:
            raise CapabilityDenied(
                f"required capability {missing_required[0]!r} for {plugin_id} "
                "is not approved"
            )

        grants: list[CapabilityGrant] = []
        for cap_id in sorted(effective_ids):
            scoped = (
                explicit_scopes.get(cap_id) if explicit_scopes is not None else None
            )
            grants.append(scoped or CapabilityGrant(id=cap_id))
        for cap_id in sorted(DEFAULT_CAPABILITY_IDS - declared_ids):
            grants.append(CapabilityGrant(id=cap_id))
        return CapabilitySet(grants)
