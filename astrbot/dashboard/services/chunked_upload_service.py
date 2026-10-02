"""Generic chunked-upload session management.

Business services keep ownership of file validation, final naming and
post-merge handling; this service owns the session lifecycle, chunk storage,
streaming assembly and expiry cleanup. Every session is bound to an owner
(the authenticated username) and a purpose (the consuming business), so a
session created for one business cannot be consumed by another caller or
another upload flow.
"""

from __future__ import annotations

import asyncio
import math
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from astrbot.core import logger
from astrbot.core.utils.upload import UploadTooLargeError

DEFAULT_CHUNK_SIZE = 1024 * 1024
DEFAULT_EXPIRE_SECONDS = 3600
CLEANUP_INTERVAL_SECONDS = 300


class ChunkedUploadError(Exception):
    pass


@dataclass
class UploadSession:
    id: str
    owner: str
    purpose: str
    filename: str
    original_filename: str
    total_size: int
    total_chunks: int
    chunk_size: int
    chunk_dir: Path
    meta: dict = field(default_factory=dict)
    received_chunks: set[int] = field(default_factory=set)
    created_at: float = 0.0
    last_activity: float = 0.0


class ChunkedUploadService:
    """Manage chunked upload sessions on disk with bounded memory."""

    def __init__(
        self,
        chunks_root: str | Path,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        expire_seconds: int = DEFAULT_EXPIRE_SECONDS,
    ) -> None:
        self.chunks_root = Path(chunks_root)
        self.chunk_size = chunk_size
        self.expire_seconds = expire_seconds
        self.sessions: dict[str, UploadSession] = {}
        self._cleanup_task: asyncio.Task | None = None

    def init_session(
        self,
        *,
        owner: str,
        purpose: str,
        filename: str,
        original_filename: str,
        total_size: int,
        meta: dict | None = None,
    ) -> UploadSession:
        """Create a session and its chunk directory.

        Args:
            owner: Authenticated username the session is bound to.
            purpose: Consuming business identifier (e.g. "backup").
            filename: Sanitized final file name chosen by the business.
            original_filename: Name as reported by the client.
            total_size: Declared total size in bytes; the business validates
                any upper bound before calling, so only sanity is checked here.
            meta: Opaque business metadata carried with the session (e.g. the
                client-reported content type) and read back at assembly time.

        Returns:
            The created session.

        Raises:
            ChunkedUploadError: The declared size is not positive.
        """
        if total_size <= 0:
            raise ChunkedUploadError("Invalid file size")

        upload_id = str(uuid.uuid4())
        chunk_dir = self.chunks_root / upload_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        now = time.time()
        session = UploadSession(
            id=upload_id,
            owner=owner,
            purpose=purpose,
            filename=filename,
            original_filename=original_filename,
            total_size=total_size,
            total_chunks=math.ceil(total_size / self.chunk_size),
            chunk_size=self.chunk_size,
            chunk_dir=chunk_dir,
            meta=meta or {},
            created_at=now,
            last_activity=now,
        )
        self.sessions[upload_id] = session
        logger.info(
            f"Chunked upload session started: id={upload_id}, owner={owner}, "
            f"purpose={purpose}, file={filename}, chunks={session.total_chunks}"
        )
        return session

    def get_session(self, upload_id: str, *, owner: str | None = None) -> UploadSession:
        """Look up a session, optionally enforcing its owner.

        Missing sessions, expired sessions and owner mismatches raise the
        same error so callers cannot probe which sessions exist. The janitor
        reaps expired chunk directories; this check keeps expired sessions
        from staying usable in the meantime.

        Raises:
            ChunkedUploadError: Session unknown, expired or owned by someone else.
        """
        session = self.sessions.get(upload_id)
        if (
            session is None
            or (owner is not None and session.owner != owner)
            or time.time() - session.last_activity > self.expire_seconds
        ):
            raise ChunkedUploadError("Upload session not found or expired")
        return session

    async def save_chunk(
        self,
        upload_id: str,
        chunk_index: int,
        file: Any,
        *,
        owner: str | None = None,
    ) -> dict:
        """Persist one chunk; repeats and out-of-order arrivals are idempotent.

        Args:
            file: Upload object exposing the adapter ``save()`` contract.

        Returns:
            Progress dict with received/total/chunk_index.

        Raises:
            ChunkedUploadError: Unknown session, bad index or oversized chunk.
        """
        session = self.get_session(upload_id, owner=owner)
        if chunk_index < 0 or chunk_index >= session.total_chunks:
            raise ChunkedUploadError("Chunk index out of range")

        # Save to a uniquely named temp file and publish it atomically:
        # a failed or concurrent retry for the same index must not clobber
        # the chunk that was already received.
        chunk_path = session.chunk_dir / f"{chunk_index}.part"
        temp_path = session.chunk_dir / f"{chunk_index}.{uuid.uuid4().hex}.tmp"
        try:
            written = await file.save(temp_path, max_bytes=session.chunk_size)
        except BaseException as exc:
            temp_path.unlink(missing_ok=True)
            if isinstance(exc, UploadTooLargeError):
                raise ChunkedUploadError("Chunk exceeds the size limit") from exc
            raise

        # The save contract returns the byte count; a short or absent write
        # means the chunk is unusable and must not be published.
        expected = min(
            session.total_size - chunk_index * session.chunk_size,
            session.chunk_size,
        )
        if written != expected:
            temp_path.unlink(missing_ok=True)
            raise ChunkedUploadError(
                f"Chunk size mismatch: got {written} bytes, expected {expected}"
            )

        try:
            await asyncio.to_thread(os.replace, temp_path, chunk_path)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
        session.received_chunks.add(chunk_index)
        session.last_activity = time.time()

        logger.debug(
            f"Chunk received: id={upload_id}, "
            f"chunk={chunk_index + 1}/{session.total_chunks}"
        )
        return {
            "received": len(session.received_chunks),
            "total": session.total_chunks,
            "chunk_index": chunk_index,
        }

    def session_status(self, upload_id: str, *, owner: str | None = None) -> dict:
        """Return resumable progress for a session.

        Read-only on purpose: it must not refresh ``last_activity``, or
        polling this endpoint would anchor a session (and its on-disk
        chunks) alive forever, defeating the expiry mechanism.

        Raises:
            ChunkedUploadError: Session unknown, expired or owned by someone else.
        """
        session = self.get_session(upload_id, owner=owner)
        remaining = self.expire_seconds - (time.time() - session.last_activity)
        return {
            "received_chunks": sorted(session.received_chunks),
            "total_chunks": session.total_chunks,
            "chunk_size": session.chunk_size,
            "expires_in": max(0, int(remaining)),
        }

    async def assemble(
        self,
        upload_id: str,
        dest: str | Path,
        *,
        owner: str | None = None,
    ) -> int:
        """Merge all chunks into dest, verify the size and clean up.

        Returns:
            Size in bytes of the merged file.

        Raises:
            ChunkedUploadError: Chunks missing or merged size mismatch.
        """
        session = self.get_session(upload_id, owner=owner)
        if len(session.received_chunks) != session.total_chunks:
            missing = sorted(set(range(session.total_chunks)) - session.received_chunks)
            raise ChunkedUploadError(f"Chunks incomplete, missing: {missing[:10]}...")

        dest_path = Path(dest)
        try:
            with dest_path.open("wb") as outfile:
                for i in range(session.total_chunks):
                    with (session.chunk_dir / f"{i}.part").open("rb") as part:
                        shutil.copyfileobj(part, outfile)
            size = dest_path.stat().st_size
            if size != session.total_size:
                raise ChunkedUploadError(
                    f"Merged size ({size}) does not match the declared size "
                    f"({session.total_size})"
                )
        except BaseException:
            dest_path.unlink(missing_ok=True)
            raise

        await self.cleanup_session(upload_id)
        return size

    async def abort(self, upload_id: str, *, owner: str | None = None) -> bool:
        """Abort and clean up a session. Unknown sessions abort silently.

        Works on expired sessions too — cleanup is the point — but never on
        sessions owned by someone else.

        Returns:
            True when a session existed and was removed.

        Raises:
            ChunkedUploadError: The session exists but belongs to another owner.
        """
        session = self.sessions.get(upload_id)
        if session is None:
            return False
        if owner is not None and session.owner != owner:
            raise ChunkedUploadError("Upload session not found or expired")
        await self.cleanup_session(upload_id)
        return True

    async def cleanup_session(self, upload_id: str) -> None:
        session = self.sessions.get(upload_id)
        if session is None:
            return
        if session.chunk_dir.exists():
            try:
                shutil.rmtree(session.chunk_dir)
            except Exception as exc:
                logger.warning(f"Failed to remove chunk dir {session.chunk_dir}: {exc}")
                # Keep the session registered so the janitor can retry the
                # leftover directory instead of forgetting it permanently.
                return
        self.sessions.pop(upload_id, None)

    def ensure_cleanup_task_started(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            try:
                self._cleanup_task = asyncio.create_task(
                    self._cleanup_expired_sessions()
                )
            except RuntimeError:
                pass

    async def _cleanup_expired_sessions(self) -> None:
        while True:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
                now = time.time()
                expired = [
                    upload_id
                    for upload_id, session in self.sessions.items()
                    if now - session.last_activity > self.expire_seconds
                ]
                for upload_id in expired:
                    await self.cleanup_session(upload_id)
                    logger.info(f"Cleaned up expired upload session: {upload_id}")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Failed to clean up expired upload sessions: {exc}")
