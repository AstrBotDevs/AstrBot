"""Bounded SQLite storage operations for offline image-history maintenance."""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import LargeBinary, cast, func, select, text
from sqlalchemy.orm.attributes import set_committed_value

from astrbot.core import conversation_history_limits
from astrbot.core.db.po import (
    ConversationImageRef,
    ConversationV2,
    ImageHistoryMigrationTask,
)

HISTORY_READ_CHUNK_BYTES = 64 * 1024
BACKUP_PAGE_COUNT = 128


@dataclass(frozen=True)
class SourceFingerprint:
    """Exact identity and digest of one stored conversation history value."""

    conversation_id: str
    user_id: str
    platform_id: str
    source_row_id: int
    source_created_at: str
    source_sha256: str
    source_byte_size: int


@dataclass(frozen=True)
class HistoryMigrationCommitResult:
    """Outcome and digest of an atomically committed history replacement."""

    status: str
    output_sha256: str
    output_byte_size: int


class ConversationSourceError(RuntimeError):
    """The selected conversation source is unavailable or has changed."""


def _open_readonly_database(database_path: Path) -> sqlite3.Connection:
    """Open an existing SQLite database without allowing accidental creation.

    Args:
        database_path: Existing AstrBot SQLite database file.

    Returns:
        A read-only connection in explicit transaction mode.

    Raises:
        FileNotFoundError: The selected database is missing.
        ValueError: The database path is not a regular file.
        sqlite3.Error: SQLite cannot open the database.
    """
    path = Path(database_path).resolve(strict=True)
    if not path.is_file():
        raise ValueError("The selected database path is not a regular file")
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=ro",
        uri=True,
        timeout=30,
        isolation_level=None,
    )
    connection.execute("PRAGMA query_only = ON")
    encoding = connection.execute("PRAGMA encoding").fetchone()[0]
    if encoding.upper().replace("-", "") != "UTF8":
        connection.close()
        raise ConversationSourceError(
            "Only UTF-8 SQLite databases can be migrated safely"
        )
    return connection


def _source_metadata(connection: sqlite3.Connection, conversation_id: str):
    """Read the small identity columns without selecting history content."""
    return connection.execute(
        "SELECT inner_conversation_id, conversation_id, user_id, platform_id, "
        "CAST(created_at AS TEXT), typeof(content) "
        "FROM conversations WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()


def _hash_blob(blob: sqlite3.Blob, chunk_bytes: int) -> str:
    """Hash a SQLite blob using a fixed-size Python buffer."""
    digest = hashlib.sha256()
    blob.seek(0)
    while chunk := blob.read(chunk_bytes):
        digest.update(chunk)
    return digest.hexdigest()


def fingerprint_conversation(
    database_path: Path,
    conversation_id: str,
    *,
    chunk_bytes: int = HISTORY_READ_CHUNK_BYTES,
) -> SourceFingerprint:
    """Fingerprint one history directly from SQLite with bounded Python memory.

    The database TEXT value is opened by rowid through SQLite's incremental
    blob API. No ORM JSON decoder or whole-value SQL result is involved.

    Args:
        database_path: Existing SQLite database or a consistent snapshot.
        conversation_id: Conversation to identify and hash.
        chunk_bytes: Maximum bytes read into Python per operation.

    Returns:
        The conversation identity, exact stored byte length, and SHA-256.

    Raises:
        ValueError: The chunk size is invalid or the source is not TEXT/BLOB.
        ConversationSourceError: The conversation is absent or its row changes.
        sqlite3.Error: SQLite cannot read the selected database value.
    """
    if chunk_bytes <= 0 or chunk_bytes > 1024 * 1024:
        raise ValueError("History read chunks must be between 1 byte and 1 MiB")
    connection = _open_readonly_database(database_path)
    try:
        connection.execute("BEGIN")
        metadata = _source_metadata(connection, conversation_id)
        if metadata is None:
            raise ConversationSourceError("Conversation was not found")
        row_id, cid, user_id, platform_id, created_at, value_type = metadata
        if value_type not in {"text", "blob"}:
            raise ConversationSourceError(
                "Conversation history is not stored as TEXT or BLOB"
            )
        with connection.blobopen(
            "conversations", "content", row_id, readonly=True
        ) as blob:
            source_size = len(blob)
            source_sha256 = _hash_blob(blob, chunk_bytes)
        return SourceFingerprint(
            conversation_id=cid,
            user_id=user_id,
            platform_id=platform_id,
            source_row_id=row_id,
            source_created_at=created_at,
            source_sha256=source_sha256,
            source_byte_size=source_size,
        )
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


@contextmanager
def open_fingerprinted_conversation_history(
    database_path: Path,
    expected: SourceFingerprint,
    *,
    chunk_bytes: int = HISTORY_READ_CHUNK_BYTES,
) -> Iterator[sqlite3.Blob]:
    """Open a seekable, read-only history stream after verifying its fingerprint.

    Keep all reads inside the context manager so the SQLite snapshot and blob
    handle remain alive. The full hash is checked before yielding the stream.

    Args:
        database_path: Snapshot database containing the selected conversation.
        expected: Fingerprint captured for the source snapshot or task.
        chunk_bytes: Maximum bytes read into Python while checking the hash.

    Yields:
        A seekable SQLite blob handle for the exact history bytes.

    Raises:
        ConversationSourceError: Identity, byte length, or content changed.
        ValueError: The chunk size is invalid or the value is not TEXT/BLOB.
        sqlite3.Error: SQLite cannot open or read the selected value.
    """
    if chunk_bytes <= 0 or chunk_bytes > 1024 * 1024:
        raise ValueError("History read chunks must be between 1 byte and 1 MiB")
    connection = _open_readonly_database(database_path)
    try:
        connection.execute("BEGIN")
        metadata = _source_metadata(connection, expected.conversation_id)
        if metadata is None:
            raise ConversationSourceError("Conversation was not found")
        row_id, cid, user_id, platform_id, created_at, value_type = metadata
        identity = (cid, user_id, platform_id, row_id, created_at)
        expected_identity = (
            expected.conversation_id,
            expected.user_id,
            expected.platform_id,
            expected.source_row_id,
            expected.source_created_at,
        )
        if identity != expected_identity:
            raise ConversationSourceError("Conversation identity changed")
        if value_type not in {"text", "blob"}:
            raise ConversationSourceError(
                "Conversation history is not stored as TEXT or BLOB"
            )
        with connection.blobopen(
            "conversations", "content", row_id, readonly=True
        ) as blob:
            if len(blob) != expected.source_byte_size:
                raise ConversationSourceError("Conversation history size changed")
            if _hash_blob(blob, chunk_bytes) != expected.source_sha256:
                raise ConversationSourceError("Conversation history content changed")
            blob.seek(0)
            yield blob
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


def create_database_snapshot(source_path: Path, snapshot_path: Path) -> Path:
    """Create a self-contained SQLite snapshot using SQLite's backup API.

    Args:
        source_path: Existing AstrBot database, including any active WAL state.
        snapshot_path: New path for the consistent standalone snapshot.

    Returns:
        The completed snapshot path.

    Raises:
        FileExistsError: The destination already exists.
        FileNotFoundError: The source database is missing.
        sqlite3.Error: Backup or integrity verification fails.
        OSError: The snapshot cannot be durably published.
    """
    source = Path(source_path).resolve(strict=True)
    if not source.is_file():
        raise ValueError("The selected database path is not a regular file")
    destination = Path(snapshot_path).expanduser().absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("The database snapshot destination already exists")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".partial",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    source_connection = None
    target_connection = None
    try:
        source_connection = _open_readonly_database(source)
        target_connection = sqlite3.connect(temporary, timeout=30)
        source_connection.backup(
            target_connection,
            pages=BACKUP_PAGE_COUNT,
            sleep=0.05,
        )
        check = target_connection.execute("PRAGMA quick_check").fetchone()
        if check is None or check[0] != "ok":
            raise sqlite3.DatabaseError("SQLite snapshot integrity check failed")
        mode = target_connection.execute("PRAGMA journal_mode = DELETE").fetchone()
        if mode is None or mode[0].lower() != "delete":
            raise sqlite3.DatabaseError("SQLite snapshot could not be made standalone")
        target_connection.close()
        target_connection = None
        source_connection.close()
        source_connection = None
        with temporary.open("rb+") as snapshot_file:
            snapshot_file.flush()
            os.fsync(snapshot_file.fileno())
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("The database snapshot destination already exists")
        os.replace(temporary, destination)
        if os.name != "nt":
            directory_fd = os.open(
                destination.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        return destination
    finally:
        if target_connection is not None:
            target_connection.close()
        if source_connection is not None:
            source_connection.close()
        for suffix in ("", "-journal", "-wal", "-shm"):
            try:
                Path(f"{temporary}{suffix}").unlink()
            except FileNotFoundError:
                pass


def _fingerprint_matches_task(
    task: ImageHistoryMigrationTask,
    expected: SourceFingerprint,
) -> bool:
    """Return whether the durable task records this exact source snapshot."""
    return (
        task.conversation_id == expected.conversation_id
        and task.user_id == expected.user_id
        and task.platform_id == expected.platform_id
        and task.source_row_id == expected.source_row_id
        and task.source_created_at == expected.source_created_at
        and task.source_sha256 == expected.source_sha256
        and task.source_byte_size == expected.source_byte_size
    )


async def commit_migrated_history(
    db,
    task_id: str,
    expected: SourceFingerprint,
    previous_projection: list | None,
    new_history: list,
    image_refs: Sequence[ConversationImageRef],
) -> HistoryMigrationCommitResult:
    """Atomically commit a bounded replacement and task completion marker.

    The source is re-hashed from a separate read-only SQLite connection while
    ``BEGIN IMMEDIATE`` prevents another writer from changing the conversation.
    The oversized source is never loaded through the ORM or passed as an
    optimistic ``expected_history`` value.

    Args:
        db: Initialized ``SQLiteDatabase`` instance.
        task_id: Durable prepared migration-task UUID.
        expected: Source identity and digest captured from the backup.
        previous_projection: Bounded history projection used to preserve existing
            checkpoint ordering, or None when no old projection is available.
        new_history: Parsed and checkpointed history within the 16 MiB limit.
        image_refs: Trusted new image references prepared from this source.

    Returns:
        ``committed`` after the transaction, or ``already_committed`` when the
        current history matches the task's committed output digest.

    Raises:
        ConversationSourceError: Source identity or content no longer matches.
        ValueError: The task is missing, stale, or not prepared.
        PermissionError: A database implementation lacks the SQLite maintenance
            transaction interface.
        HistoryTooLargeError: The final stored JSON exceeds 16 MiB.
        sqlite3.Error: The live source cannot be revalidated.
    """
    from astrbot.core.image_asset_store import image_store_lock

    db_path = getattr(db, "db_path", None)
    sync_image_history = getattr(db, "_sync_image_history", None)
    load_metadata = getattr(db, "_conversation_without_history", None)
    if db_path is None or sync_image_history is None or load_metadata is None:
        raise PermissionError("M7 maintenance requires the SQLite database backend")
    if not isinstance(new_history, list):
        raise ValueError("The replacement conversation history must be a list")

    async with image_store_lock():
        async with db.get_db() as session:
            async with session.begin():
                # Online connections favor a large page cache and mmap. Reclaiming
                # an oversized row would make those pages resident even though
                # Python reads it incrementally. This stopped-application session
                # uses a small page cache and disk-backed temporary storage.
                await session.execute(text("PRAGMA cache_size = -2048"))
                await session.execute(text("PRAGMA mmap_size = 0"))
                await session.execute(text("PRAGMA temp_store = FILE"))
                # SQLite's legacy transaction mode does not reserve a writer for
                # SELECT. Take the lock before reading either task or conversation.
                await session.execute(text("BEGIN IMMEDIATE"))
                task = await session.get(ImageHistoryMigrationTask, task_id)
                if task is None:
                    raise ValueError("Image-history migration task was not found")
                if not _fingerprint_matches_task(task, expected):
                    raise ValueError(
                        "Migration task does not match its source snapshot"
                    )

                actual = await asyncio.to_thread(
                    fingerprint_conversation,
                    Path(db_path),
                    expected.conversation_id,
                )
                expected_identity = (
                    expected.conversation_id,
                    expected.user_id,
                    expected.platform_id,
                    expected.source_row_id,
                    expected.source_created_at,
                )
                actual_identity = (
                    actual.conversation_id,
                    actual.user_id,
                    actual.platform_id,
                    actual.source_row_id,
                    actual.source_created_at,
                )
                if actual_identity != expected_identity:
                    raise ConversationSourceError("Conversation identity changed")

                if task.state == "committed":
                    if (
                        task.output_sha256 == actual.source_sha256
                        and task.output_byte_size == actual.source_byte_size
                    ):
                        return HistoryMigrationCommitResult(
                            status="already_committed",
                            output_sha256=actual.source_sha256,
                            output_byte_size=actual.source_byte_size,
                        )
                    raise ConversationSourceError(
                        "Committed migration output changed after completion"
                    )
                if task.state != "prepared":
                    raise ValueError("Migration task is not in a resumable state")
                if actual != expected:
                    raise ConversationSourceError(
                        "Conversation history changed after the backup was created"
                    )

                conversation = await load_metadata(
                    session,
                    expected.conversation_id,
                )
                if conversation is None:
                    raise ConversationSourceError("Conversation was deleted")
                if (
                    conversation.inner_conversation_id != expected.source_row_id
                    or conversation.user_id != expected.user_id
                    or conversation.platform_id != expected.platform_id
                ):
                    raise ConversationSourceError("Conversation identity changed")
                if previous_projection is not None:
                    set_committed_value(
                        conversation,
                        "content",
                        previous_projection,
                    )
                await sync_image_history(
                    session,
                    conversation,
                    new_history,
                    image_refs=image_refs,
                    expected_history=None,
                )
                conversation.content = new_history
                await session.flush()
                byte_size = await session.scalar(
                    select(
                        func.coalesce(
                            func.length(cast(ConversationV2.content, LargeBinary)),
                            0,
                        )
                    ).where(ConversationV2.conversation_id == expected.conversation_id)
                )
                limit = conversation_history_limits.MAX_ONLINE_HISTORY_BYTES
                if byte_size > limit:
                    raise conversation_history_limits.HistoryTooLargeError(
                        expected.conversation_id,
                        byte_size,
                        limit,
                    )
                stored_content = await session.scalar(
                    select(cast(ConversationV2.content, LargeBinary)).where(
                        ConversationV2.conversation_id == expected.conversation_id
                    )
                )
                if not isinstance(stored_content, bytes):
                    raise ConversationSourceError(
                        "Committed history is not stored as UTF-8 JSON bytes"
                    )
                output_byte_size = len(stored_content)
                if output_byte_size != byte_size or output_byte_size > limit:
                    raise ConversationSourceError(
                        "Stored output size changed during migration commit"
                    )
                output_sha256 = hashlib.sha256(stored_content).hexdigest()
                task.state = "committed"
                task.output_sha256 = output_sha256
                task.output_byte_size = output_byte_size
                await session.flush()
                result = HistoryMigrationCommitResult(
                    status="committed",
                    output_sha256=output_sha256,
                    output_byte_size=output_byte_size,
                )
    return result
