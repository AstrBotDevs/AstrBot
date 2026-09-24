"""Validated storage for original images, independent of request-time previews."""

from __future__ import annotations

import asyncio
import errno
import hashlib
import os
import stat
import threading
import uuid
import warnings
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import BinaryIO, TypeVar

from filelock import AsyncFileLock
from PIL import Image
from sqlmodel import select

from astrbot import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import (
    ConversationImageCheckpoint,
    ConversationImageRef,
    ConversationV2,
    ImageAsset,
)
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

Result = TypeVar("Result")
COPY_CHUNK_BYTES = 1024 * 1024


def image_store_lock() -> AsyncFileLock:
    """Create the shared lock used by image files, associations and backups.

    Returns:
        A fresh non-reentrant directory lock for this operation.

    Raises:
        OSError: The managed directory or lock path is a symbolic link.
    """
    root = Path(get_astrbot_data_path()) / "image_assets"
    if root.is_symlink():
        raise OSError("The image asset directory must not be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    if (root / ".store.lock").is_symlink():
        raise OSError("Image store lock must not be a symlink")
    return AsyncFileLock(root / ".store.lock", run_in_executor=False)


async def collect_pending_images(db: BaseDatabase) -> int:
    """Retry physical deletion only for explicitly retired, unreferenced assets.

    File publication and database commit are not one transaction. A failed unlink
    leaves the pending row for retry; a missing file completes a previous unlink.
    Never infer retirement from a missing reference on an available asset.

    Args:
        db: Database whose lifecycle transactions explicitly retired the assets.

    Returns:
        Number of retired assets removed from the database.
    """
    removed = 0
    root = Path(get_astrbot_data_path()) / "image_assets"
    async with image_store_lock():
        async with db.get_db() as session:
            # Iterate metadata in bounded batches without materializing histories.
            last_id = ""
            while True:
                result = await session.execute(
                    select(ImageAsset)
                    .where(
                        ImageAsset.state == "pending_delete",
                        ImageAsset.asset_id > last_id,
                        ~select(ConversationImageRef.asset_id)
                        .where(ConversationImageRef.asset_id == ImageAsset.asset_id)
                        .exists(),
                    )
                    .order_by(ImageAsset.asset_id)
                    .limit(100)
                )
                assets = result.scalars().all()
                if not assets:
                    break
                for asset in assets:
                    last_id = asset.asset_id
                    try:
                        if (
                            str(uuid.UUID(asset.asset_id)) != asset.asset_id
                            or asset.storage_key != f"{asset.asset_id}.img"
                        ):
                            raise OSError("Invalid retired image key")
                        path = root / asset.storage_key
                        if path.is_symlink():
                            raise OSError("Retired image must not be a symlink")
                        path.unlink(missing_ok=True)
                    except (OSError, ValueError):
                        logger.warning(
                            "Retired image removal failed; keeping it for retry"
                        )
                        continue
                    await session.delete(asset)
                    removed += 1
                await session.commit()
    return removed


async def cleanup_image_orphans(db: BaseDatabase, storage_keys: list[str]) -> int:
    """Remove explicitly selected orphan files during operator maintenance.

    Run with ingestion paused: a not-yet-associated upload may otherwise be
    deliberately removed before its caller can attach it. References are always
    rechecked under the shared lock. This function is never called automatically.

    Args:
        db: Database belonging to the selected image store.
        storage_keys: Exact store-relative UUID .img/.part filenames selected by
            the operator, not a wildcard or a model-supplied path.

    Returns:
        Number of orphan files or retired asset rows successfully removed.

    Raises:
        ValueError: A key is invalid or an asset is still referenced.
        OSError: An orphan path cannot be safely removed.
    """
    removed = 0
    root = Path(get_astrbot_data_path()) / "image_assets"
    async with image_store_lock():
        async with db.get_db() as session:
            selected: list[tuple[Path, ImageAsset | None]] = []
            for key in dict.fromkeys(storage_keys):
                name = Path(key)
                if (
                    name.name != key
                    or name.suffix not in {".img", ".part"}
                    or str(uuid.UUID(name.stem)) != name.stem
                ):
                    raise ValueError("Invalid orphan image key")
                asset = (
                    await session.execute(
                        select(ImageAsset).where(ImageAsset.storage_key == key)
                    )
                ).scalar_one_or_none()
                if asset is not None:
                    reference = (
                        await session.execute(
                            select(ConversationImageRef.occurrence_id)
                            .where(ConversationImageRef.asset_id == asset.asset_id)
                            .limit(1)
                        )
                    ).first()
                    if reference is not None:
                        raise ValueError("Cannot remove a referenced image")
                path = root / key
                if path.is_symlink():
                    raise OSError("Orphan image must not be a symlink")
                selected.append((path, asset))
            # Validate the complete selection before changing any asset or file.
            for path, asset in selected:
                if asset is not None:
                    asset.state = "pending_delete"
                    session.add(asset)
                else:
                    path.unlink(missing_ok=True)
                    removed += 1
            await session.commit()
    return removed + await collect_pending_images(db)


class ImageStorageLimitError(ValueError):
    """The configured pixel or animation frame budget was exceeded."""


class ImageAssetImportConflictError(ValueError):
    """A stable asset ID already names bytes or metadata different from the input."""


class ImageValidationError(OSError):
    """Encoded input is corrupt or exceeds image decoding limits."""


def validate_image_source(
    source: Path, max_pixels: int, max_frames: int, stop: threading.Event
) -> tuple[str, int, int]:
    """Validate bounded image pixels without changing original encoded bytes.

    Args:
        source: Local encoded source or staged immutable copy.
        max_pixels: Maximum pixels per decoded frame.
        max_frames: Maximum decoded animation frames.
        stop: Cooperative cancellation event.

    Returns:
        MIME type, width, and height.

    Raises:
        ImageValidationError: Corrupt image, invalid dimensions, or excessive frames.
        InterruptedError: Validation was cancelled.
    """
    try:
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ImageValidationError("Image input must be a regular file")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise ImageStorageLimitError("Image pixel budget exceeded")
                mime = Image.MIME.get(image.format or "")
                if not mime or not mime.startswith("image/"):
                    raise ValueError("Unsupported image format")
                image.verify()
            with Image.open(source) as image:
                for frame in range(max_frames):
                    if stop.is_set():
                        raise InterruptedError("Image validation cancelled")
                    if (
                        image.width <= 0
                        or image.height <= 0
                        or image.width * image.height > max_pixels
                    ):
                        raise ImageStorageLimitError("Image pixel budget exceeded")
                    image.load()
                    try:
                        image.seek(frame + 1)
                    except EOFError:
                        break
                    if frame + 1 == max_frames:
                        raise ImageStorageLimitError("Image frame budget exceeded")
        return mime, width, height
    except InterruptedError:
        raise
    except ImageStorageLimitError:
        raise
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        if isinstance(exc, OSError) and exc.errno in {
            errno.ENOMEM,
            errno.EMFILE,
            errno.ENFILE,
        }:
            raise
        raise ImageValidationError("Invalid encoded image") from exc


async def run_image_io(function: Callable[..., Result], *args) -> Result:
    """Drain a bounded worker before releasing locks on cancellation.

    Args:
        function: Synchronous operation accepting a final cancellation event.
        *args: Positional operation arguments.

    Returns:
        The completed worker result.

    Raises:
        asyncio.CancelledError: Cancellation requested, after the worker stops.
        Exception: The worker's original failure.
    """
    stop = threading.Event()
    task = asyncio.create_task(asyncio.to_thread(function, *args, stop))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        stop.set()
        # A second cancellation must not detach a writer from its directory lock.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise


class ImageAssetStore:
    """Store immutable bytes; callers own conversation/history transactions.

    This module is an internal API, not an endpoint accepting arbitrary paths.
    Every operation locks the store directory, including reader lifetimes. Future
    garbage collection must use the same lock.
    """

    def __init__(
        self,
        db: BaseDatabase,
        *,
        max_pixels: int,
        max_frames: int,
    ) -> None:
        """Configure a store without enabling any production image ingestion.

        Args:
            db: Database containing image assets and conversation associations.
            max_pixels: Maximum pixels per frame, checked before active decoding.
            max_frames: Maximum number of animation frames.

        Raises:
            ValueError: A pixel or frame limit is not a positive integer.
            OSError: The dedicated data directory cannot be safely created.
        """
        for value in (max_pixels, max_frames):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(
                    "Image pixel and frame limits must be positive integers"
                )
        self.db = db
        self.max_pixels = max_pixels
        self.max_frames = max_frames
        self.root = Path(get_astrbot_data_path()) / "image_assets"
        if self.root.is_symlink():
            raise OSError("The image asset directory must not be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve(strict=True)

    async def _run_io(self, function: Callable[..., Result], *args) -> Result:
        """Run store work using the shared cancellation-drained worker.

        Args:
            function: Synchronous operation accepting a final cancellation event.
            *args: Positional operation arguments.

        Returns:
            The completed operation's result.
        """
        return await run_image_io(function, *args)

    def _capture(
        self,
        source: Path,
        source_kind: str,
        stop: threading.Event,
        *,
        asset_id: str | None = None,
    ) -> ImageAsset:
        """Copy and validate one original while the caller holds the store lock.

        Args:
            source: Trusted, already-localized source file.
            source_kind: Original bytes or recovered legacy model input.
            stop: Cooperative cancellation flag.
            asset_id: Optional preselected UUID used by resumable maintenance.

        Returns:
            Metadata for an atomically published file, not yet committed to SQLite.

        Raises:
            ImageStorageLimitError: A pixel or animation frame limit is exceeded.
            ValueError: The input is not a supported raster image.
            OSError: Reading, validation, or publishing fails.
            InterruptedError: Cancellation was requested before publication.
        """
        for entry in self.root.iterdir():
            if stop.is_set():
                raise InterruptedError("Image capture cancelled")
            if entry.name == ".store.lock":
                continue
            if not stat.S_ISREG(entry.lstat().st_mode):
                raise OSError("Unexpected non-regular entry in the image store")
        before = source.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Image source must be a regular file")

        stable_asset_id = asset_id is not None
        asset_id = asset_id or str(uuid.uuid4())
        staged = self.root / f"{asset_id}.part"
        published = self.root / f"{asset_id}.img"
        digest = hashlib.sha256()
        size = 0
        try:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            with os.fdopen(os.open(source, flags), "rb") as incoming:
                opened = os.fstat(incoming.fileno())
                if not stat.S_ISREG(opened.st_mode) or (
                    before.st_dev,
                    before.st_ino,
                ) != (opened.st_dev, opened.st_ino):
                    raise OSError("Image source changed before capture")
                with staged.open("xb") as outgoing:
                    while chunk := incoming.read(COPY_CHUNK_BYTES):
                        if stop.is_set():
                            raise InterruptedError("Image capture cancelled")
                        size += len(chunk)
                        if outgoing.write(chunk) != len(chunk):
                            raise OSError("Incomplete image write")
                        digest.update(chunk)
                    after = os.fstat(incoming.fileno())
                    if size != opened.st_size or (
                        opened.st_size,
                        opened.st_mtime_ns,
                    ) != (after.st_size, after.st_mtime_ns):
                        raise OSError("Image source changed during capture")
                    outgoing.flush()
                    os.fsync(outgoing.fileno())

            mime, width, height = validate_image_source(
                staged, self.max_pixels, self.max_frames, stop
            )
            if stop.is_set():
                raise InterruptedError("Image publication cancelled")
            if stable_asset_id:
                try:
                    os.link(staged, published)
                except FileExistsError as exc:
                    raise ImageAssetImportConflictError(
                        "Stable image asset path already exists"
                    ) from exc
                staged.unlink()
            else:
                staged.replace(published)
            if os.name != "nt":
                directory_fd = os.open(
                    self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                )
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            return ImageAsset(
                asset_id=asset_id,
                storage_key=published.name,
                mime_type=mime,
                byte_size=size,
                width=width,
                height=height,
                sha256=digest.hexdigest(),
                source_kind=source_kind,
            )
        finally:
            staged.unlink(missing_ok=True)

    def _verify_stable_import(
        self,
        source: Path,
        asset_id: str,
        source_kind: str,
        existing: dict | None,
        stop: threading.Event,
    ) -> tuple[str, int, int, int, str]:
        """Compare an input with a file already published under its stable ID.

        Args:
            source: Trusted, already-localized source file.
            asset_id: Canonical UUID selecting the managed image path.
            source_kind: Expected asset source classification.
            existing: Persisted asset columns, or None for a published orphan.
            stop: Cooperative cancellation flag.

        Returns:
            MIME type, width, height, byte size, and SHA-256 of matching bytes.

        Raises:
            ImageAssetImportConflictError: The ID, file, or metadata conflicts.
            ImageValidationError: The source is not a supported image.
            OSError: A file cannot be read safely or changes during verification.
            InterruptedError: Cancellation was requested while reading or validating.
        """
        published = self.root / f"{asset_id}.img"
        try:
            target_info = published.lstat()
        except FileNotFoundError as exc:
            raise ImageAssetImportConflictError(
                "Stable image asset file is missing"
            ) from exc
        if not stat.S_ISREG(target_info.st_mode):
            raise ImageAssetImportConflictError(
                "Stable image asset path is not a regular file"
            )

        source_info = source.lstat()
        if not stat.S_ISREG(source_info.st_mode):
            raise ValueError("Image source must be a regular file")
        if source_info.st_size != target_info.st_size:
            raise ImageAssetImportConflictError(
                "Stable image asset byte size does not match the source"
            )
        if existing is not None and (
            existing.get("asset_id") != asset_id
            or existing.get("storage_key") != published.name
            or existing.get("source_kind") != source_kind
            or existing.get("state") != "available"
            or existing.get("byte_size") != source_info.st_size
            or not isinstance(existing.get("sha256"), str)
            or len(existing["sha256"]) != 64
        ):
            raise ImageAssetImportConflictError(
                "Stable image asset metadata does not match the source"
            )

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        source_digest = hashlib.sha256()
        target_digest = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(os.open(source, flags), "rb") as incoming:
                opened_source = os.fstat(incoming.fileno())
                if not stat.S_ISREG(opened_source.st_mode) or (
                    source_info.st_dev,
                    source_info.st_ino,
                ) != (opened_source.st_dev, opened_source.st_ino):
                    raise OSError("Image source changed before stable import check")
                with os.fdopen(os.open(published, flags), "rb") as stored:
                    opened_target = os.fstat(stored.fileno())
                    if not stat.S_ISREG(opened_target.st_mode) or (
                        target_info.st_dev,
                        target_info.st_ino,
                    ) != (opened_target.st_dev, opened_target.st_ino):
                        raise ImageAssetImportConflictError(
                            "Stable image asset changed before verification"
                        )
                    while True:
                        if stop.is_set():
                            raise InterruptedError(
                                "Stable image verification cancelled"
                            )
                        source_chunk = incoming.read(COPY_CHUNK_BYTES)
                        stored_chunk = stored.read(COPY_CHUNK_BYTES)
                        if source_chunk != stored_chunk:
                            raise ImageAssetImportConflictError(
                                "Stable image asset bytes do not match the source"
                            )
                        if not source_chunk:
                            break
                        size += len(source_chunk)
                        source_digest.update(source_chunk)
                        target_digest.update(stored_chunk)
                    after_source = os.fstat(incoming.fileno())
                    after_target = os.fstat(stored.fileno())
                    if size != opened_source.st_size or (
                        opened_source.st_size,
                        opened_source.st_mtime_ns,
                    ) != (after_source.st_size, after_source.st_mtime_ns):
                        raise OSError("Image source changed during stable import check")
                    if size != opened_target.st_size or (
                        opened_target.st_size,
                        opened_target.st_mtime_ns,
                    ) != (after_target.st_size, after_target.st_mtime_ns):
                        raise ImageAssetImportConflictError(
                            "Stable image asset changed during verification"
                        )
        except FileNotFoundError as exc:
            raise ImageAssetImportConflictError(
                "Stable image asset path disappeared during verification"
            ) from exc

        digest = source_digest.hexdigest()
        if digest != target_digest.hexdigest() or (
            existing is not None and digest != existing["sha256"]
        ):
            raise ImageAssetImportConflictError(
                "Stable image asset digest does not match the source"
            )
        mime, width, height = validate_image_source(
            source, self.max_pixels, self.max_frames, stop
        )
        if existing is not None and (
            existing.get("mime_type") != mime
            or existing.get("width") != width
            or existing.get("height") != height
        ):
            raise ImageAssetImportConflictError(
                "Stable image asset image metadata does not match the source"
            )
        return mime, width, height, size, digest

    async def import_file(
        self,
        source: Path,
        *,
        source_kind: str = "original",
        asset_id: str | None = None,
    ) -> ImageAsset:
        """Persist bytes before committing metadata, without creating a conversation link.

        Args:
            source: Trusted local image path. URL/download authorization is upstream.
            source_kind: ``original`` or ``legacy_model_input``.
            asset_id: Optional canonical UUID for resumable maintenance. Repeated
                imports under that ID are accepted only for identical bytes.

        Returns:
            The committed asset. No conversation obtains access merely by knowing its ID.

        Raises:
            ValueError: Invalid source kind or image data.
            ImageAssetImportConflictError: The stable ID already names different data.
            ImageStorageLimitError: The image exceeds the pixel or frame limit.
            OSError: File I/O or image validation fails.
            Exception: Metadata commit fails; the published file remains available
                for later reconciliation, including uncertain commit outcomes.
        """
        if source_kind not in {"original", "legacy_model_input"}:
            raise ValueError("Invalid image source kind")
        if asset_id is not None:
            try:
                if str(uuid.UUID(asset_id)) != asset_id:
                    raise ValueError
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(
                    "Stable image asset ID must be a canonical UUID"
                ) from exc
        if self.root.is_symlink() or (self.root / ".store.lock").is_symlink():
            raise OSError("Image store paths must not be symlinks")
        # A fresh lock instance avoids reentrancy between concurrent tasks/instances.
        async with AsyncFileLock(self.root / ".store.lock", run_in_executor=False):
            if asset_id is not None:
                part_path = self.root / f"{asset_id}.part"
                try:
                    part_info = part_path.lstat()
                except FileNotFoundError:
                    pass
                else:
                    if not stat.S_ISREG(part_info.st_mode):
                        raise ImageAssetImportConflictError(
                            "Stable image staging path is not a regular file"
                        )
                    part_path.unlink()

                async with self.db.get_db() as session:
                    existing = await session.get(ImageAsset, asset_id)
                    existing_values = (
                        existing.model_dump() if existing is not None else None
                    )

                published = self.root / f"{asset_id}.img"
                try:
                    published.lstat()
                    published_exists = True
                except FileNotFoundError:
                    published_exists = False

                if existing is not None or published_exists:
                    mime, width, height, size, digest = await self._run_io(
                        self._verify_stable_import,
                        Path(source),
                        asset_id,
                        source_kind,
                        existing_values,
                    )
                    if existing is not None:
                        return existing
                    asset = ImageAsset(
                        asset_id=asset_id,
                        storage_key=published.name,
                        mime_type=mime,
                        byte_size=size,
                        width=width,
                        height=height,
                        sha256=digest,
                        source_kind=source_kind,
                    )
                    async with self.db.get_db() as session:
                        session.add(asset)
                        await session.commit()
                    return asset

                capture = partial(self._capture, asset_id=asset_id)
                asset = await self._run_io(capture, Path(source), source_kind)
            else:
                asset = await self._run_io(self._capture, Path(source), source_kind)
            async with self.db.get_db() as session:
                session.add(asset)
                await session.commit()
            return asset

    def _verify_file(
        self, stream: BinaryIO, asset: ImageAsset, stop: threading.Event
    ) -> None:
        """Check immutable bytes with bounded memory before exposing a reader.

        Args:
            stream: Open descriptor in the managed directory.
            asset: Authorized metadata to check.
            stop: Cooperative cancellation flag.

        Raises:
            OSError: Stored bytes differ from the published asset.
            InterruptedError: Cancellation is requested.
        """
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != asset.byte_size:
            raise OSError("Image asset size mismatch")
        digest = hashlib.sha256()
        size = 0
        while chunk := stream.read(COPY_CHUNK_BYTES):
            if stop.is_set():
                raise InterruptedError("Image read cancelled")
            size += len(chunk)
            if size > asset.byte_size:
                raise OSError("Image asset changed during read")
            digest.update(chunk)
        if size != asset.byte_size or digest.hexdigest() != asset.sha256:
            raise OSError("Image asset checksum mismatch")
        stream.seek(0)

    @asynccontextmanager
    async def open_image(
        self,
        *,
        conversation_id: str,
        occurrence_id: str,
        user_id: str,
        platform_id: str,
    ) -> AsyncIterator[BinaryIO]:
        """Yield an authorized stream while holding the store's read/delete protection.

        Args:
            conversation_id: Current server-selected conversation.
            occurrence_id: Image occurrence selected within that conversation.
            user_id: Server-selected conversation owner, never a model-supplied owner.
            platform_id: Server-selected platform belonging to the conversation.

        Yields:
            Binary stream positioned at the beginning; caller must not retain it.

        Raises:
            PermissionError: No matching authorized, available association exists.
            OSError: The stored path is invalid, missing, or corrupted.
        """
        if self.root.is_symlink() or (self.root / ".store.lock").is_symlink():
            raise OSError("Image store paths must not be symlinks")
        async with AsyncFileLock(self.root / ".store.lock", run_in_executor=False):
            async with self.db.get_db() as session:
                result = await session.execute(
                    select(ImageAsset)
                    .join(
                        ConversationImageRef,
                        ConversationImageRef.asset_id == ImageAsset.asset_id,
                    )
                    .join(
                        ConversationV2,
                        ConversationV2.conversation_id
                        == ConversationImageRef.conversation_id,
                    )
                    .join(
                        ConversationImageCheckpoint,
                        (
                            ConversationImageCheckpoint.conversation_id
                            == ConversationImageRef.conversation_id
                        )
                        & (
                            ConversationImageCheckpoint.checkpoint_id
                            == ConversationImageRef.checkpoint_id
                        ),
                    )
                    .where(
                        ConversationImageCheckpoint.active == True,  # noqa: E712
                        ConversationImageRef.conversation_id == conversation_id,
                        ConversationImageRef.occurrence_id == occurrence_id,
                        ConversationV2.user_id == user_id,
                        ConversationV2.platform_id == platform_id,
                        ImageAsset.state == "available",
                    )
                )
                asset = result.scalar_one_or_none()
            if asset is None:
                raise PermissionError(
                    "Image reference is not available in this conversation"
                )
            # Only store-generated flat keys are valid on every supported platform.
            try:
                canonical_id = str(uuid.UUID(asset.asset_id))
            except ValueError as exc:
                raise OSError("Invalid image asset ID") from exc
            if (
                asset.storage_key != f"{canonical_id}.img"
                or canonical_id != asset.asset_id
            ):
                raise OSError("Invalid image asset storage key")
            path = self.root / asset.storage_key
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise OSError("Image asset must be a regular file")
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            with os.fdopen(os.open(path, flags), "rb") as stream:
                opened = os.fstat(stream.fileno())
                if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
                    raise OSError("Image asset changed before opening")
                await self._run_io(self._verify_file, stream, asset)
                yield stream
