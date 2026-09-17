#!/usr/bin/env python3
"""Explicit offline migration, repair, rollback, and cleanup for image history."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from astrbot.core.utils.image_media_store import ImageMediaRef, ImageMediaStore


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _logical_digest(connection: sqlite3.Connection) -> str:
    """Hash every table schema and row without loading the database in memory."""
    digest = hashlib.sha256()
    tables = connection.execute(
        "SELECT name, sql, type FROM sqlite_master WHERE type IN ('table','index','trigger','view') ORDER BY name"
    )
    for name, sql, object_type in tables:
        digest.update(json.dumps([name, sql], ensure_ascii=False).encode())
        if object_type != "table":
            continue
        rows = connection.execute(
            f'SELECT * FROM "{name.replace(chr(34), chr(34) * 2)}"'
        )
        for row in rows:
            digest.update(
                json.dumps(
                    list(row), ensure_ascii=False, default=str, separators=(",", ":")
                ).encode()
            )
    return digest.hexdigest()


def _manifest_media_name(name: str) -> tuple[str, str]:
    path = Path(name)
    if path.name != name or path.suffix not in {".bin", ".json"}:
        raise ValueError("invalid media manifest filename")
    media_id = path.stem
    if len(media_id) != 64 or any(char not in "0123456789abcdef" for char in media_id):
        raise ValueError("invalid media manifest media id")
    return media_id, path.suffix


def _inline_parts(value: Any) -> Iterator[tuple[dict[str, Any], str, str]]:
    if isinstance(value, list):
        for item in value:
            yield from _inline_parts(item)
    elif isinstance(value, dict):
        if value.get("type") == "image_url" and isinstance(
            value.get("image_url"), dict
        ):
            url = value["image_url"].get("url")
            if isinstance(url, str) and url.startswith("data:image/"):
                header, encoded = url.split(",", 1)
                yield value, header[5:].split(";", 1)[0], encoded
        else:
            for child in value.values():
                yield from _inline_parts(child)


def _replace_inline(value: Any, store: ImageMediaStore) -> tuple[Any, int, int]:
    changed = 0
    bytes_migrated = 0

    def visit(item: Any) -> Any:
        nonlocal changed, bytes_migrated
        if isinstance(item, list):
            return [visit(child) for child in item]
        if not isinstance(item, dict):
            return item
        if item.get("type") == "image_url" and isinstance(item.get("image_url"), dict):
            image = item["image_url"]
            url = image.get("url")
            if isinstance(url, str) and url.startswith("data:image/"):
                header, encoded = url.split(",", 1)
                data = base64.b64decode(encoded, validate=True)
                ref = store.put(
                    data,
                    header[5:].split(";", 1)[0],
                    image.get("detail"),
                    image.get("id"),
                )
                changed += 1
                bytes_migrated += len(data)
                return ref.model_dump()
        return {key: visit(child) for key, child in item.items()}

    return visit(value), changed, bytes_migrated


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _backup(db: Path, media: Path, destination: Path) -> Path:
    """Create a consistent database snapshot and a verified media snapshot."""
    destination.mkdir(parents=True, exist_ok=False)
    snapshot = sqlite3.connect(destination / db.name)
    readonly = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        readonly.backup(snapshot)
        snapshot.commit()
    finally:
        readonly.close()
        snapshot.close()
    if media.exists():
        (destination / "media").mkdir()
        manifest_media = []
        for path in media.iterdir():
            if path.is_symlink() or not path.is_file():
                raise RuntimeError("media backup refuses symlinks and non-files")
            target = destination / "media" / path.name
            shutil.copy2(path, target)
            manifest_media.append({"name": path.name, "sha256": _digest(target)})
    else:
        manifest_media = []
    manifest = {
        "database": _digest(destination / db.name),
        "media": manifest_media,
    }
    if (destination / "media").exists():
        manifest["media"] = sorted(manifest_media, key=lambda item: item["name"])
    (destination / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n"
    )
    return destination


def _migrate(args: argparse.Namespace) -> dict[str, int]:
    if args.apply and not args.offline:
        raise SystemExit("--apply requires --offline: stop all history writes first")
    db = Path(args.database).resolve()
    media = Path(args.media).resolve()
    connection = _connect(db)
    lock = args.apply
    try:
        if lock:
            connection.execute("BEGIN IMMEDIATE")
            backup = _backup(
                db,
                media,
                Path(args.backup)
                if args.backup
                else Path(
                    tempfile.mkdtemp(prefix="astrbot-image-history-backup-parent-")
                )
                / "snapshot",
            )
        query = (
            "SELECT inner_conversation_id, conversation_id, content FROM conversations"
        )
        parameters: tuple[Any, ...] = ()
        if args.conversation_id:
            query += (
                " WHERE conversation_id IN ("
                + ",".join("?" for _ in args.conversation_id)
                + ")"
            )
            parameters = tuple(args.conversation_id)
        total = changed = bytes_migrated = 0
        store = ImageMediaStore(media)
        for row in connection.execute(query, parameters):
            total += 1
            try:
                content = (
                    json.loads(row["content"])
                    if isinstance(row["content"], str)
                    else row["content"]
                )
                converted, count, amount = (
                    _replace_inline(content, store)
                    if args.apply
                    else (content, sum(1 for _ in _inline_parts(content)), 0)
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"conversation {row['conversation_id']} cannot be parsed or verified"
                ) from exc
            changed += count
            bytes_migrated += amount
            if args.apply and count:
                connection.execute(
                    "UPDATE conversations SET content=? WHERE inner_conversation_id=?",
                    (
                        json.dumps(converted, ensure_ascii=False),
                        row["inner_conversation_id"],
                    ),
                )
        if args.apply:
            post_migration_digest = _logical_digest(connection)
            connection.commit()
            manifest_path = backup / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["post_migration_logical_digest"] = post_migration_digest
            manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
            print(
                json.dumps(
                    {
                        "backup": str(backup),
                        "records": total,
                        "images": changed,
                        "bytes": bytes_migrated,
                    }
                )
            )
        else:
            connection.rollback()
            print(json.dumps({"dry_run": True, "records": total, "images": changed}))
        return {"records": total, "images": changed}
    finally:
        connection.close()


def _cleanup(args: argparse.Namespace) -> None:
    if args.apply and not args.offline:
        raise SystemExit("cleanup --apply requires --offline")
    connection = _connect(Path(args.database).resolve())
    media = Path(args.media).resolve()
    try:
        connection.execute("BEGIN IMMEDIATE")
        referenced: set[str] = set()
        for row in connection.execute("SELECT content FROM conversations"):
            try:
                content = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                if not isinstance(content, list):
                    raise ValueError("history content is not a list")
                for item in content:
                    if not isinstance(item, dict):
                        raise ValueError("history message is not an object")
                pending = list(content)
                while pending:
                    part = pending.pop()
                    if isinstance(part, list):
                        pending.extend(part)
                    elif isinstance(part, dict):
                        if part.get("type") == "image_media_ref":
                            parsed = ImageMediaRef(
                                media_id=part["media_id"],
                                mime_type=part["mime_type"],
                                width=part.get("width"),
                                height=part.get("height"),
                                byte_size=part["byte_size"],
                                detail=part.get("detail"),
                                version=part.get("version", 1),
                                image_id=part.get("image_id"),
                            )
                            ImageMediaStore(media).read(parsed, {parsed.media_id})
                            referenced.add(parsed.media_id)
                        else:
                            pending.extend(part.values())
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("history parse failed; cleanup aborted") from exc
        quarantine = Path(
            args.quarantine or (media.parent / (media.name + ".quarantine"))
        )
        if args.apply:
            quarantine.mkdir(parents=True, exist_ok=True)
        moved = 0
        for media_id in sorted(
            {path.stem for path in media.iterdir() if path.suffix in {".bin", ".json"}}
        ):
            paths = [media / f"{media_id}.bin", media / f"{media_id}.json"]
            if any(path.is_symlink() for path in paths if path.exists()):
                continue
            if media_id in referenced:
                continue
            existing_paths = [path for path in paths if path.exists()]
            if len(existing_paths) != 2:
                continue
            try:
                metadata = json.loads(paths[1].read_text())
                if (
                    metadata.get("media_id") != media_id
                    or _digest(paths[0]) != media_id
                ):
                    continue
            except (OSError, json.JSONDecodeError):
                continue
            if args.apply:
                targets = [quarantine / path.name for path in existing_paths]
                if any(target.exists() for target in targets):
                    raise RuntimeError(
                        "quarantine target already exists; refusing overwrite"
                    )
                for path, target in zip(existing_paths, targets):
                    shutil.move(str(path), target)
            moved += len(existing_paths)
        if args.apply:
            connection.commit()
        else:
            connection.rollback()
        print(
            json.dumps(
                {
                    "dry_run": not args.apply,
                    "quarantined": moved,
                    "referenced": len(referenced),
                }
            )
        )
    finally:
        connection.close()


def _restore(args: argparse.Namespace) -> None:
    """Restore only when the database and media are unchanged since migration."""
    if not args.offline:
        raise SystemExit("restore requires --offline")
    backup = Path(args.restore).resolve()
    db = Path(args.database).resolve()
    backup_db = backup / db.name
    manifest_path = backup / "manifest.json"
    if not backup_db.is_file() or not manifest_path.is_file():
        raise SystemExit("backup is incomplete")
    manifest = json.loads(manifest_path.read_text())
    if _digest(backup_db) != manifest.get("database"):
        raise SystemExit("restore refused: archived database hash mismatch")
    archived_media = backup / "media"
    manifest_names: set[str] = set()
    for item in manifest.get("media", []):
        _manifest_media_name(item["name"])
        checksum = item.get("sha256", "")
        if (
            item["name"] in manifest_names
            or len(checksum) != 64
            or any(char not in "0123456789abcdef" for char in checksum)
        ):
            raise SystemExit("restore refused: invalid media manifest")
        manifest_names.add(item["name"])
        source = archived_media / item["name"]
        if (
            source.is_symlink()
            or not source.is_file()
            or _digest(source) != item["sha256"]
        ):
            raise SystemExit("restore refused: archived media hash mismatch")
    current = _connect(db)
    try:
        if _logical_digest(current) != manifest.get("post_migration_logical_digest"):
            raise SystemExit("restore refused: database changed since migration")
    finally:
        current.close()
    media = Path(args.media).resolve()
    for item in manifest.get("media", []):
        target = media / item["name"]
        if target.exists() and (
            target.is_symlink() or _digest(target) != item["sha256"]
        ):
            raise SystemExit(f"restore refused: conflicting media: {target.name}")
    rollback = db.with_name(db.name + ".before-restore")
    if rollback.exists():
        raise SystemExit("refusing to overwrite an existing pre-restore copy")
    try:
        staged_media: list[tuple[Path, Path]] = []
        staging = Path(
            tempfile.mkdtemp(prefix="astrbot-restore-media-", dir=media.parent)
        )
        for item in manifest.get("media", []):
            source = archived_media / item["name"]
            staged = staging / item["name"]
            shutil.copy2(source, staged)
            if _digest(staged) != item["sha256"]:
                raise SystemExit("restore refused: staged media hash mismatch")
            staged_media.append((staged, media / item["name"]))
        media.mkdir(parents=True, exist_ok=True)
        for staged, target in staged_media:
            if not target.exists():
                staged.replace(target)

        rollback_connection = sqlite3.connect(rollback)
        current = _connect(db)
        try:
            current.backup(rollback_connection)
            rollback_connection.commit()
        finally:
            current.close()
            rollback_connection.close()
        destination = _connect(db)
        archived = _connect(backup_db)
        try:
            archived.backup(destination)
            destination.commit()
        finally:
            archived.close()
            destination.close()
    finally:
        if "staging" in locals():
            shutil.rmtree(staging, ignore_errors=True)
    print(json.dumps({"restored": str(db), "pre_restore_copy": str(rollback)}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("--media", required=True)
    parser.add_argument("--conversation-id", action="append")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--backup")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--quarantine")
    parser.add_argument("--restore")
    args = parser.parse_args()
    if args.restore:
        _restore(args)
    elif args.cleanup:
        _cleanup(args)
    else:
        _migrate(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
