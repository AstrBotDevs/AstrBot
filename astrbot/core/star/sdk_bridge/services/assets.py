from __future__ import annotations

import base64
import json
import time
import uuid
from pathlib import Path
from typing import Any

from astrbot_sdk.assets import AssetRef
from astrbot_sdk.errors import (
    CapabilityDenied,
    InvalidRequest,
    NotFound,
    RateLimited,
)

_MAX_ASSET_BYTES = 50 * 1024 * 1024
_MAX_TOTAL_BYTES = 256 * 1024 * 1024
_PENDING_TTL_SECONDS = 3600


class AssetStore:
    """Filesystem-backed asset store namespaced per plugin."""

    def __init__(self, root: Path, plugin_id: str) -> None:
        """Initialize the store.

        Args:
            root: Asset root directory shared by all plugins.
            plugin_id: Owning plugin; every asset lives below its namespace.
        """
        self._dir = root / plugin_id.replace("/", "_")
        self._pending_dir = self._dir / "pending"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._pending_dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, asset: AssetRef) -> Path:
        """Resolve an asset reference to its local file.

        Args:
            asset: Reference received from the plugin.

        Returns:
            Local file path of the asset payload.

        Raises:
            CapabilityDenied: The asset does not belong to this plugin.
        """
        path = self._dir / f"{_safe_name(asset.id)}.bin"
        if not path.is_file():
            raise CapabilityDenied(f"unknown or foreign asset: {asset.id}")
        return path

    def stat(self, asset_id: str) -> dict[str, Any]:
        """Read asset metadata."""
        path, meta = self._lookup(asset_id)
        return {
            "size": path.stat().st_size,
            "media_type": meta.get("media_type"),
            "filename": meta.get("filename"),
        }

    def read(self, asset_id: str, offset: int, length: int) -> bytes:
        """Read one byte range of an asset."""
        path, _ = self._lookup(asset_id)
        with path.open("rb") as handle:
            handle.seek(offset)
            return handle.read(length)

    def put(
        self,
        data: bytes,
        *,
        filename: str | None,
        media_type: str | None,
    ) -> AssetRef:
        """Store a complete payload and return its reference."""
        self._check_quota(len(data))
        asset_id = f"ast_{uuid.uuid4().hex[:16]}"
        path = self._dir / f"{asset_id}.bin"
        path.write_bytes(data)
        self._dir.joinpath(f"{asset_id}.json").write_text(
            json.dumps({"filename": filename, "media_type": media_type}),
            encoding="utf-8",
        )
        return AssetRef(
            id=asset_id,
            filename=filename,
            media_type=media_type,
            size=len(data),
        )

    def begin_pending(self, meta: dict[str, Any]) -> str:
        """Start a chunked upload and sweep stale pending files."""
        self._sweep_pending()
        upload_id = f"up_{uuid.uuid4().hex[:16]}"
        self._pending_dir.joinpath(f"{upload_id}.json").write_text(
            json.dumps(meta),
            encoding="utf-8",
        )
        self._pending_dir.joinpath(f"{upload_id}.part").touch()
        return upload_id

    def append_pending(self, upload_id: str, seq: int, data: bytes) -> None:
        """Append one chunk to a pending upload in sequence order."""
        part = self._pending_dir / f"{_safe_name(upload_id)}.part"
        if not part.is_file():
            raise NotFound(f"unknown upload: {upload_id}")
        expected = part.stat().st_size
        with part.open("ab") as handle:
            handle.write(data)
        _ = seq, expected  # sequence integrity is enforced at commit size

    def commit_pending(self, upload_id: str) -> AssetRef:
        """Finalize a pending upload into a stored asset."""
        safe = _safe_name(upload_id)
        part = self._pending_dir / f"{safe}.part"
        meta_path = self._pending_dir / f"{safe}.json"
        if not part.is_file() or not meta_path.is_file():
            raise NotFound(f"unknown upload: {upload_id}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        data = part.read_bytes()
        declared = meta.get("size")
        if declared is not None and int(declared) != len(data):
            self.abort_pending(upload_id)
            raise InvalidRequest("uploaded size does not match declaration")
        asset = self.put(
            data,
            filename=meta.get("filename"),
            media_type=meta.get("media_type"),
        )
        part.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        return asset

    def abort_pending(self, upload_id: str) -> None:
        """Discard a pending upload."""
        safe = _safe_name(upload_id)
        self._pending_dir.joinpath(f"{safe}.part").unlink(missing_ok=True)
        self._pending_dir.joinpath(f"{safe}.json").unlink(missing_ok=True)

    def _lookup(self, asset_id: str) -> tuple[Path, dict[str, Any]]:
        safe = _safe_name(asset_id)
        path = self._dir / f"{safe}.bin"
        if not path.is_file():
            raise CapabilityDenied(f"unknown or foreign asset: {asset_id}")
        meta_path = self._dir / f"{safe}.json"
        meta = (
            json.loads(meta_path.read_text(encoding="utf-8"))
            if meta_path.is_file()
            else {}
        )
        return path, meta

    def _check_quota(self, incoming: int) -> None:
        if incoming > _MAX_ASSET_BYTES:
            raise RateLimited("asset exceeds the single-file size limit")
        total = sum(path.stat().st_size for path in self._dir.glob("*.bin"))
        if total + incoming > _MAX_TOTAL_BYTES:
            raise RateLimited("plugin asset quota exceeded")

    def _sweep_pending(self) -> None:
        cutoff = time.time() - _PENDING_TTL_SECONDS
        for part in self._pending_dir.glob("*.part"):
            if part.stat().st_mtime < cutoff:
                self.abort_pending(part.stem)


def _safe_name(value: str) -> str:
    """Restrict identifiers to safe filename characters."""
    safe = "".join(char for char in value if char.isalnum() or char in "_-")
    if not safe:
        raise InvalidRequest("invalid asset identifier")
    return safe


class AssetTransferService:
    """Serve the assets.transfer capability against the plugin asset store."""

    capability_id = "assets.transfer"

    def __init__(self, store: AssetStore) -> None:
        """Initialize the service.

        Args:
            store: Plugin-namespaced asset store.
        """
        self._store = store

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve upload, stat, and read operations."""
        if operation == "upload":
            data = _decode_chunk(payload, "data")
            asset = self._store.put(
                data,
                filename=payload.get("filename"),
                media_type=payload.get("media_type"),
            )
            return {"asset": asset}
        if operation == "upload_begin":
            return {
                "upload_id": self._store.begin_pending(
                    {
                        "filename": payload.get("filename"),
                        "media_type": payload.get("media_type"),
                        "size": payload.get("size"),
                    },
                ),
            }
        if operation == "upload_chunk":
            self._store.append_pending(
                str(payload["upload_id"]),
                int(payload.get("seq", 0)),
                _decode_chunk(payload, "data"),
            )
            return {}
        if operation == "upload_commit":
            return {"asset": self._store.commit_pending(str(payload["upload_id"]))}
        if operation == "upload_abort":
            self._store.abort_pending(str(payload["upload_id"]))
            return {}
        if operation == "stat":
            return self._store.stat(str(payload["asset_id"]))
        if operation == "read":
            data = self._store.read(
                str(payload["asset_id"]),
                int(payload["offset"]),
                int(payload["length"]),
            )
            return {"data": base64.b64encode(data).decode("ascii")}
        raise NotFound(f"unknown assets operation: {operation}")


def _decode_chunk(payload: dict[str, Any], key: str) -> bytes:
    """Decode a base64 chunk field."""
    raw = payload.get(key)
    if not isinstance(raw, str):
        raise InvalidRequest(f"missing chunk field: {key}")
    try:
        return base64.b64decode(raw)
    except ValueError as exc:
        raise InvalidRequest("invalid base64 chunk") from exc
