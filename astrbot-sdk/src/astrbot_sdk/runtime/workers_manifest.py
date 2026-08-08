"""Supervisor-side manifest for remote websocket workers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml


@dataclass(slots=True)
class RemoteWorkerTLSConfig:
    ca_file: Path
    cert_file: Path
    key_file: Path
    server_hostname: str | None = None


@dataclass(slots=True)
class RemoteWorkerSpec:
    id: str
    url: str
    tls: RemoteWorkerTLSConfig


def load_remote_workers_manifest(manifest_path: Path) -> list[RemoteWorkerSpec]:
    resolved_path = manifest_path.resolve()
    payload = yaml.safe_load(resolved_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("workers manifest must be a mapping")

    entries = payload.get("workers")
    if not isinstance(entries, list):
        raise ValueError("workers manifest must define a 'workers' list")

    workers: list[RemoteWorkerSpec] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"workers[{index}] must be an object")
        _reject_unsupported_worker_keys(entry, index=index)
        worker_id = str(entry.get("id", "")).strip()
        if not worker_id:
            raise ValueError(f"workers[{index}].id must be a non-empty string")
        if worker_id in seen_ids:
            raise ValueError(f"duplicate worker id in workers manifest: {worker_id}")
        seen_ids.add(worker_id)

        raw_url = str(entry.get("url", "")).strip()
        parsed = urlparse(raw_url)
        if parsed.scheme != "wss":
            raise ValueError(
                f"workers[{index}].url must use wss:// for mutual TLS: {raw_url!r}"
            )
        if not parsed.netloc:
            raise ValueError(f"workers[{index}].url must include a host: {raw_url!r}")

        tls_payload = entry.get("tls")
        if not isinstance(tls_payload, dict):
            raise ValueError(f"workers[{index}].tls must be an object")
        tls = _load_tls_config(
            tls_payload,
            manifest_dir=resolved_path.parent,
            prefix=f"workers[{index}].tls",
        )
        workers.append(RemoteWorkerSpec(id=worker_id, url=raw_url, tls=tls))

    return workers


def _reject_unsupported_worker_keys(entry: dict[str, object], *, index: int) -> None:
    unsupported = {"group_id", "plugins"} & set(entry)
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise ValueError(
            f"workers[{index}] must not declare {names}; websocket host config only "
            "accepts worker connection settings"
        )


def _load_tls_config(
    payload: dict[str, object],
    *,
    manifest_dir: Path,
    prefix: str,
) -> RemoteWorkerTLSConfig:
    ca_file = _resolve_required_path(
        payload.get("ca_file"), manifest_dir, f"{prefix}.ca_file"
    )
    cert_file = _resolve_required_path(
        payload.get("cert_file"),
        manifest_dir,
        f"{prefix}.cert_file",
    )
    key_file = _resolve_required_path(
        payload.get("key_file"), manifest_dir, f"{prefix}.key_file"
    )
    server_hostname_raw = payload.get("server_hostname")
    server_hostname = (
        str(server_hostname_raw).strip() if server_hostname_raw is not None else None
    )
    if server_hostname == "":
        server_hostname = None
    return RemoteWorkerTLSConfig(
        ca_file=ca_file,
        cert_file=cert_file,
        key_file=key_file,
        server_hostname=server_hostname,
    )


def _resolve_required_path(value: object, base_dir: Path, field_name: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty path")
    path = Path(text)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path
