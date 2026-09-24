"""Offline orchestration for resumable migration of legacy image histories."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import uuid
from dataclasses import asdict
from pathlib import Path

from filelock import AsyncFileLock
from sqlmodel import select

from astrbot.core.agent.message import ImageRefPart, get_checkpoint_id
from astrbot.core.conversation_history_limits import MAX_ONLINE_HISTORY_BYTES
from astrbot.core.db.po import (
    ConversationImageRef,
    ImageAsset,
    ImageHistoryMigrationTask,
)
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.image_asset_store import (
    COPY_CHUNK_BYTES,
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_MAX_TOTAL_BYTES,
    ImageAssetStore,
    image_store_lock,
    run_image_io,
    validate_image_source,
)
from astrbot.core.image_history_maintenance_storage import (
    commit_migrated_history,
    create_database_snapshot,
    fingerprint_conversation,
    open_fingerprinted_conversation_history,
)
from astrbot.core.image_history_migration import (
    MAX_CONTEXT_IMAGE_FRAMES,
    MAX_CONTEXT_IMAGE_PIXELS,
    _checkpoint_image_groups,
    _LegacyImage,
)
from astrbot.core.image_history_stream import rewrite_legacy_history_stream
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class ImageHistoryMaintenanceError(ValueError):
    """A maintenance operation stopped without a successful history replacement."""


def _hash_file(path: Path, limit: int | None = None) -> tuple[str, int]:
    """Hash a regular file in bounded chunks and detect concurrent replacement.

    Args:
        path: Trusted local file selected by the maintenance task.
        limit: Optional maximum number of bytes to read.

    Returns:
        SHA-256 hexadecimal digest and byte count.

    Raises:
        ImageHistoryMaintenanceError: The file is unsafe, changed, or exceeds limit.
        OSError: The file cannot be read.
    """
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ImageHistoryMaintenanceError("A maintenance file is not a regular file.")
    size = 0
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ImageHistoryMaintenanceError(
                "A maintenance file changed before reading."
            )
        while chunk := stream.read(COPY_CHUNK_BYTES):
            size += len(chunk)
            if limit is not None and size > limit:
                raise ImageHistoryMaintenanceError(
                    "A maintenance file exceeds its byte limit."
                )
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    if (opened.st_size, opened.st_mtime_ns) != (
        after.st_size,
        after.st_mtime_ns,
    ) or size != opened.st_size:
        raise ImageHistoryMaintenanceError("A maintenance file changed during reading.")
    return digest.hexdigest(), size


async def _maintenance_io(function, *args):
    """Drain worker I/O before releasing maintenance locks on cancellation.

    Args:
        function: Synchronous file operation.
        *args: Positional arguments for the file operation.

    Returns:
        The operation's result.
    """

    def work(*values):
        return function(*values[:-1])

    return await run_image_io(work, *args)


def _prepare_backup(database: Path, job_dir: Path, fingerprint, gallery: Path) -> None:
    """Create or verify a persistent database-and-gallery backup for one task.

    Args:
        database: Live database, with callers holding the image-store lock.
        job_dir: Stable directory belonging to this task.
        fingerprint: Exact selected source conversation identity and bytes.
        gallery: AstrBot's managed image directory.

    Raises:
        ImageHistoryMaintenanceError: Backup integrity or source checks fail.
        OSError: There is insufficient space or a file cannot be copied.
    """
    backup = job_dir / "backup"
    media = backup / "image_assets"
    for directory in (backup, media):
        if directory.is_symlink():
            raise ImageHistoryMaintenanceError(
                "Backup directories must not be symlinks."
            )
        directory.mkdir(exist_ok=True)
    snapshot = backup / "database.sqlite"
    manifest = backup / "media.jsonl"
    ready = backup / "ready.json"
    if ready.exists():
        if ready.is_symlink() or ready.stat().st_size > 64 * 1024:
            raise ImageHistoryMaintenanceError("Invalid backup manifest.")
        saved = json.loads(ready.read_text())
        if saved.get("source") != asdict(fingerprint):
            raise ImageHistoryMaintenanceError(
                "The backup belongs to another source snapshot."
            )
        if list(_hash_file(snapshot)) != saved.get("database") or list(
            _hash_file(manifest)
        ) != saved.get("media_manifest"):
            raise ImageHistoryMaintenanceError(
                "The maintenance backup failed integrity verification."
            )
        with manifest.open("r", encoding="utf-8") as entries:
            for line in entries:
                item = json.loads(line)
                key = item["key"]
                name = Path(key)
                if (
                    name.name != key
                    or name.suffix not in {".img", ".part"}
                    or str(uuid.UUID(name.stem)) != name.stem
                ):
                    raise ImageHistoryMaintenanceError("Invalid image key in backup.")
                if list(_hash_file(media / key)) != item["file"]:
                    raise ImageHistoryMaintenanceError(
                        "An image backup failed integrity verification."
                    )
        return

    if snapshot.is_symlink() or manifest.is_symlink():
        raise ImageHistoryMaintenanceError("Backup files must not be symlinks.")
    snapshot_bytes = 0
    if not snapshot.exists():
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
            page_count = connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        snapshot_bytes = page_count * page_size
    gallery_bytes = 0
    if gallery.exists():
        for entry in gallery.iterdir():
            if entry.name == ".store.lock":
                continue
            info = entry.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ImageHistoryMaintenanceError(
                    "An image-store entry is not a regular file."
                )
            gallery_bytes += info.st_size
    # A previous run may have published the snapshot but not its gallery copy.
    # Conservatively reserve a full gallery copy even when some files exist.
    needed = (
        snapshot_bytes
        + gallery_bytes
        + 2 * fingerprint.source_byte_size
        + DEFAULT_MAX_FILE_BYTES
        + 6 * MAX_ONLINE_HISTORY_BYTES
    )
    if shutil.disk_usage(job_dir).free < needed:
        raise ImageHistoryMaintenanceError(
            "Insufficient free disk space for the database/gallery backup and staging."
        )
    if not snapshot.exists():
        create_database_snapshot(database, snapshot)
    if fingerprint_conversation(snapshot, fingerprint.conversation_id) != fingerprint:
        raise ImageHistoryMaintenanceError(
            "The source changed while its backup was prepared."
        )
    partial_manifest = backup / "media.jsonl.part"
    if partial_manifest.is_symlink():
        raise ImageHistoryMaintenanceError("Backup files must not be symlinks.")
    total_bytes = 0
    with partial_manifest.open("w", encoding="utf-8") as listing:
        if gallery.exists():
            for source in gallery.iterdir():
                if source.name == ".store.lock":
                    continue
                if (
                    source.suffix not in {".img", ".part"}
                    or str(uuid.UUID(source.stem)) != source.stem
                ):
                    raise ImageHistoryMaintenanceError("Unexpected image-store file.")
                before = source.lstat()
                if not stat.S_ISREG(before.st_mode):
                    raise ImageHistoryMaintenanceError(
                        "An image-store entry is not a regular file."
                    )
                total_bytes += before.st_size
                if total_bytes > DEFAULT_MAX_TOTAL_BYTES:
                    raise ImageHistoryMaintenanceError(
                        "The existing gallery exceeds its capacity."
                    )
                target = media / source.name
                if target.is_symlink():
                    raise ImageHistoryMaintenanceError(
                        "Image backup files must not be symlinks."
                    )
                digest = hashlib.sha256()
                size = 0
                with source.open("rb") as incoming, target.open("wb") as outgoing:
                    while chunk := incoming.read(COPY_CHUNK_BYTES):
                        size += len(chunk)
                        if size > before.st_size:
                            raise ImageHistoryMaintenanceError(
                                "An image changed during backup."
                            )
                        digest.update(chunk)
                        if outgoing.write(chunk) != len(chunk):
                            raise OSError("Incomplete image backup write")
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                after = source.stat()
                if size != before.st_size or (before.st_mtime_ns, before.st_ino) != (
                    after.st_mtime_ns,
                    after.st_ino,
                ):
                    raise ImageHistoryMaintenanceError(
                        "An image changed during backup."
                    )
                listing.write(
                    json.dumps({"key": source.name, "file": [digest.hexdigest(), size]})
                    + "\n"
                )
        listing.flush()
        os.fsync(listing.fileno())
    partial_manifest.replace(manifest)
    metadata = {
        "source": asdict(fingerprint),
        "database": list(_hash_file(snapshot)),
        "media_manifest": list(_hash_file(manifest)),
        "gallery_bytes": total_bytes,
    }
    partial_ready = backup / "ready.json.part"
    if partial_ready.is_symlink():
        raise ImageHistoryMaintenanceError("Backup files must not be symlinks.")
    with partial_ready.open("w", encoding="utf-8") as stream:
        json.dump(metadata, stream)
        stream.flush()
        os.fsync(stream.fileno())
    partial_ready.replace(ready)
    if os.name != "nt":
        for directory in (media, backup, job_dir, job_dir.parent):
            descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)


async def run_image_history_maintenance(
    db: SQLiteDatabase, conversation_id: str, *, apply: bool = False
) -> dict:
    """Prepare or apply a resumable migration while the application is stopped.

    Args:
        db: Initialized database belonging to the selected AstrBot data root.
        conversation_id: One administrator-selected conversation.
        apply: Publish images and commit history after successful preflight.

    Returns:
        Metadata-only status and paths to retained recovery artifacts.

    Raises:
        ImageHistoryMaintenanceError: Source, backup, or preflight checks fail.
        ValueError: A source image or JSON history is invalid or over budget.
        OSError: Persistent storage is unavailable.
    """
    root = Path(get_astrbot_data_path())
    jobs = root / "image_history_migrations"
    if jobs.is_symlink():
        raise ImageHistoryMaintenanceError(
            "The maintenance directory must not be a symlink."
        )
    jobs.mkdir(exist_ok=True)
    lock_path = jobs / ".maintenance.lock"
    if lock_path.is_symlink():
        raise ImageHistoryMaintenanceError(
            "The maintenance lock must not be a symlink."
        )
    async with AsyncFileLock(lock_path, run_in_executor=False):
        database = Path(db.db_path).resolve(strict=True)
        source = await _maintenance_io(
            fingerprint_conversation, database, conversation_id
        )
        async with db.get_db() as session:
            tasks = []
            for state in ("prepared", "committed"):
                statement = select(ImageHistoryMigrationTask).where(
                    ImageHistoryMigrationTask.conversation_id == conversation_id,
                    ImageHistoryMigrationTask.state == state,
                )
                if state == "committed":
                    statement = statement.where(
                        ImageHistoryMigrationTask.output_sha256 == source.source_sha256,
                        ImageHistoryMigrationTask.output_byte_size
                        == source.source_byte_size,
                    )
                row = (
                    await session.execute(
                        statement.order_by(
                            ImageHistoryMigrationTask.created_at.desc()
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                if row is not None:
                    tasks.append(row)
        for task in tasks:
            same_identity = (
                task.user_id == source.user_id
                and task.platform_id == source.platform_id
                and task.source_row_id == source.source_row_id
                and task.source_created_at == source.source_created_at
            )
            if (
                task.state == "committed"
                and same_identity
                and task.output_sha256 == source.source_sha256
                and task.output_byte_size == source.source_byte_size
            ):
                return {
                    "status": "already_committed",
                    "task_id": task.task_id,
                    "conversation_id": conversation_id,
                }
            if task.state == "prepared" and (
                not same_identity
                or task.source_sha256 != source.source_sha256
                or task.source_byte_size != source.source_byte_size
            ):
                raise ImageHistoryMaintenanceError(
                    "An unfinished task has a different source. The conversation was not changed."
                )
        identity = json.dumps(
            [str(database), *asdict(source).values()], ensure_ascii=True
        )
        task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
        namespace = uuid.UUID(task_id)
        job_dir = jobs / task_id
        if job_dir.is_symlink():
            raise ImageHistoryMaintenanceError(
                "The task directory must not be a symlink."
            )
        job_dir.mkdir(exist_ok=True)
        async with db.get_db() as session, session.begin():
            task = await session.get(ImageHistoryMigrationTask, task_id)
            if task is None:
                session.add(
                    ImageHistoryMigrationTask(task_id=task_id, **asdict(source))
                )
            elif task.state != "prepared":
                raise ImageHistoryMaintenanceError(
                    "This task is complete but its conversation no longer matches the committed output."
                )
        async with image_store_lock():
            await _maintenance_io(
                _prepare_backup, database, job_dir, source, root / "image_assets"
            )

        snapshot = job_dir / "backup" / "database.sqlite"
        staging = job_dir / "staging"
        if staging.is_symlink():
            raise ImageHistoryMaintenanceError(
                "The staging directory must not be a symlink."
            )
        staging.mkdir(exist_ok=True)
        compact = job_dir / "compact.json"
        plan_path = job_dir / "images.jsonl"
        planned_path = job_dir / "images.jsonl.part"
        for path in (compact, plan_path, planned_path, job_dir / "checked.json"):
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise ImageHistoryMaintenanceError("Task files must be regular files.")
        store = ImageAssetStore(
            db, max_pixels=MAX_CONTEXT_IMAGE_PIXELS, max_frames=MAX_CONTEXT_IMAGE_FRAMES
        )
        # A message and its current part may coexist as disk-backed JSON spools.
        staging_reserve = (
            2 * source.source_byte_size
            + DEFAULT_MAX_FILE_BYTES
            + 6 * MAX_ONLINE_HISTORY_BYTES
        )
        if shutil.disk_usage(job_dir).free < staging_reserve:
            raise ImageHistoryMaintenanceError(
                "Insufficient free disk space for streaming history staging."
            )
        expected = plan_path.open("r", encoding="utf-8") if plan_path.exists() else None
        new_images = []
        required_bytes = 0
        previous_message = -1
        ordinal = 0
        plan_bytes = 0
        try:
            with planned_path.open("w", encoding="utf-8") as planned:

                async def preflight_image(image):
                    nonlocal required_bytes, previous_message, ordinal, plan_bytes
                    await run_image_io(
                        validate_image_source,
                        image.payload_path,
                        MAX_CONTEXT_IMAGE_PIXELS,
                        MAX_CONTEXT_IMAGE_FRAMES,
                    )
                    digest, size = await _maintenance_io(
                        _hash_file, image.payload_path, DEFAULT_MAX_FILE_BYTES
                    )
                    if image.message_index != previous_message:
                        previous_message, ordinal = image.message_index, 0
                    key = f"{image.message_index}:{image.part_index}"
                    record = {
                        "message_index": image.message_index,
                        "part_index": image.part_index,
                        "image_index": ordinal,
                        "sha256": digest,
                        "byte_size": size,
                        "asset_id": str(uuid.uuid5(namespace, "asset:" + key)),
                        "occurrence_id": str(
                            uuid.uuid5(namespace, "occurrence:" + key)
                        ),
                    }
                    ordinal += 1
                    if expected is not None:
                        previous = expected.readline(4096)
                        if not previous or json.loads(previous) != record:
                            raise ImageHistoryMaintenanceError(
                                "An image source changed since preflight; the conversation was not changed."
                            )
                    async with db.get_db() as session:
                        existing = await session.get(ImageAsset, record["asset_id"])
                    if (
                        existing is None
                        and not (store.root / f"{record['asset_id']}.img").exists()
                    ):
                        required_bytes += size
                    plan_line = json.dumps(record) + "\n"
                    plan_bytes += len(plan_line.encode("utf-8"))
                    if plan_bytes > 2 * MAX_ONLINE_HISTORY_BYTES:
                        raise ImageHistoryMaintenanceError(
                            "The image migration manifest exceeds its staging budget."
                        )
                    planned.write(plan_line)
                    new_images.append(record)
                    return ImageRefPart(
                        occurrence_id=record["occurrence_id"],
                        asset_id=record["asset_id"],
                        description="",
                        description_status="pending",
                    ).model_dump()

                with (
                    open_fingerprinted_conversation_history(
                        snapshot, source
                    ) as incoming,
                    compact.open("wb") as outgoing,
                ):
                    await rewrite_legacy_history_stream(
                        incoming,
                        outgoing,
                        staging_dir=staging,
                        import_image=preflight_image,
                    )
                if expected is not None and expected.read(1):
                    raise ImageHistoryMaintenanceError(
                        "The number of image sources changed since preflight."
                    )
                planned.flush()
                os.fsync(planned.fileno())
        finally:
            if expected is not None:
                expected.close()
        if compact.stat().st_size > MAX_ONLINE_HISTORY_BYTES:
            raise ImageHistoryMaintenanceError(
                "Rewritten history still exceeds the 16 MiB online limit."
            )
        with compact.open("rb") as stream:
            projection = json.load(stream)
        if not isinstance(projection, list) or any(
            not isinstance(message, dict) for message in projection
        ):
            raise ImageHistoryMaintenanceError(
                "Conversation history must be an array of message objects."
            )
        images = [
            _LegacyImage(item["message_index"], item["part_index"], {}, "")
            for item in new_images
        ]
        existing_checkpoints = {get_checkpoint_id(message) for message in projection}
        history, _ = (
            _checkpoint_image_groups(projection, images) if images else (projection, {})
        )
        checkpoint_ids = {}
        for index, message in enumerate(history):
            checkpoint = get_checkpoint_id(message)
            if checkpoint and checkpoint not in existing_checkpoints:
                replacement = str(uuid.uuid5(namespace, f"checkpoint:{index}"))
                checkpoint_ids[checkpoint] = replacement
                message["content"]["id"] = replacement
        references = []
        for image, item in zip(images, new_images, strict=True):
            references.append(
                ConversationImageRef(
                    conversation_id=conversation_id,
                    occurrence_id=item["occurrence_id"],
                    asset_id=item["asset_id"],
                    image_index=item["image_index"],
                    checkpoint_id=checkpoint_ids.get(
                        image.checkpoint_id, image.checkpoint_id
                    ),
                    description_status="pending",
                )
            )
        serialized = json.dumps(history, ensure_ascii=True)
        final_bytes = len(serialized.encode("utf-8"))
        if final_bytes > MAX_ONLINE_HISTORY_BYTES:
            raise ImageHistoryMaintenanceError(
                "Rewritten history still exceeds the 16 MiB online limit; no history was replaced."
            )
        used_bytes = 0
        owned_parts = {f"{item['asset_id']}.part" for item in new_images}
        reclaimable_bytes = 0
        for entry in store.root.iterdir():
            if entry.name == ".store.lock":
                continue
            info = entry.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ImageHistoryMaintenanceError(
                    "An image-store entry is not a regular file."
                )
            used_bytes += info.st_size
            if entry.name in owned_parts:
                reclaimable_bytes += info.st_size
        if required_bytes > DEFAULT_MAX_TOTAL_BYTES - used_bytes + reclaimable_bytes:
            raise ImageHistoryMaintenanceError(
                "The image gallery is full; the conversation was not changed."
            )
        planned_path.replace(plan_path)
        report = {
            "status": "prepared",
            "task_id": task_id,
            "conversation_id": conversation_id,
            "source_bytes": source.source_byte_size,
            "output_bytes": final_bytes,
            "image_count": len(new_images),
            "additional_image_bytes": required_bytes,
            "reclaimable_staging_bytes": reclaimable_bytes,
            "backup_directory": str(job_dir / "backup"),
            "model_calls": 0,
        }
        if not apply:
            return report
        if shutil.disk_usage(job_dir).free < required_bytes + staging_reserve:
            raise ImageHistoryMaintenanceError(
                "Insufficient free disk space for image publication and staging."
            )

        # Only this task's deterministic unpublished staging files are restartable.
        # Clear all of them before importing, so a later image's partial write
        # cannot incorrectly consume capacity needed by an earlier image.
        async with image_store_lock():
            for name in owned_parts:
                path = store.root / name
                try:
                    info = path.lstat()
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise ImageHistoryMaintenanceError(
                        "A task staging image is not a regular file."
                    )
                path.unlink()

        iterator = iter(new_images)

        async def import_image(image):
            item = next(iterator, None)
            if item is None or (image.message_index, image.part_index) != (
                item["message_index"],
                item["part_index"],
            ):
                raise ImageHistoryMaintenanceError(
                    "Image order changed before publication."
                )
            if await _maintenance_io(
                _hash_file, image.payload_path, DEFAULT_MAX_FILE_BYTES
            ) != (item["sha256"], item["byte_size"]):
                raise ImageHistoryMaintenanceError(
                    "An image changed before publication."
                )
            asset = await store.import_file(
                image.payload_path,
                source_kind="legacy_model_input",
                asset_id=item["asset_id"],
            )
            if asset.sha256 != item["sha256"] or asset.byte_size != item["byte_size"]:
                raise ImageHistoryMaintenanceError(
                    "An image changed during publication."
                )
            return ImageRefPart(
                occurrence_id=item["occurrence_id"],
                asset_id=item["asset_id"],
                description="",
                description_status="pending",
            ).model_dump()

        checked_output = job_dir / "checked.json"
        with (
            open_fingerprinted_conversation_history(snapshot, source) as incoming,
            checked_output.open("wb") as outgoing,
        ):
            await rewrite_legacy_history_stream(
                incoming, outgoing, staging_dir=staging, import_image=import_image
            )
        if next(iterator, None) is not None or await _maintenance_io(
            _hash_file, checked_output
        ) != await _maintenance_io(_hash_file, compact):
            raise ImageHistoryMaintenanceError(
                "The rewritten history changed after preflight."
            )
        await commit_migrated_history(db, task_id, source, [], history, references)
        report["status"] = "committed"
        return report
