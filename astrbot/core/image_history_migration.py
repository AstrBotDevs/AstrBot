"""Migrate bounded legacy inline image history into conversation-scoped assets."""

from __future__ import annotations

import base64
import binascii
import copy
import os
import stat
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from astrbot.core.agent.message import ImageRefPart, ImageURLPart, get_checkpoint_id
from astrbot.core.conversation_history_limits import HistoryTooLargeError
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import ConversationImageRef
from astrbot.core.image_asset_store import (
    DEFAULT_MAX_FILE_BYTES,
    ImageAssetStore,
    ImageStorageCapacityError,
    ImageStorageLimitError,
    ImageValidationError,
    run_image_io,
    validate_image_source,
)
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import is_recoverable_image_error

MAX_CONTEXT_IMAGE_PIXELS = 20_000_000
MAX_CONTEXT_IMAGE_FRAMES = 100


class ImageHistoryMigrationError(Exception):
    """A legacy image prevented an all-or-nothing history migration.

    Attributes:
        reason: Stable failure category safe to log without image data or paths.
    """

    _USER_MESSAGES = {
        "unavailable": (
            "旧对话里有图片来源已失效或不受支持，图片整理没有完成；"
            "原对话保持不变，这条消息没有发送给模型。"
        ),
        "invalid_image": (
            "旧对话里有图片数据损坏或超过图片限制，图片整理没有完成；"
            "原对话保持不变，这条消息没有发送给模型。"
        ),
        "library_full": (
            "图库空间不足，旧对话图片整理没有完成；原对话保持不变，"
            "这条消息没有发送给模型。"
        ),
        "storage_error": (
            "图片存储暂时不可用，旧对话整理没有完成；原对话保持不变，"
            "这条消息没有发送给模型。"
        ),
        "history_changed": (
            "旧对话在整理时发生了变化，图片整理没有完成；原对话保持不变，请稍后重试。"
        ),
        "invalid_history": (
            "旧对话里的图片轮次无法安全对应，图片整理没有完成；"
            "原对话保持不变，这条消息没有发送给模型。"
        ),
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason if reason in self._USER_MESSAGES else "storage_error"
        super().__init__(self._USER_MESSAGES[self.reason])

    @property
    def user_message(self) -> str:
        """Return a safe, localized message without exposing a path or payload."""
        return self._USER_MESSAGES[self.reason]


@dataclass(slots=True)
class _LegacyImage:
    message_index: int
    part_index: int
    part: dict[str, Any]
    url: str
    checkpoint_id: str = ""
    rewritten_message_index: int = -1
    source_path: Path | None = None
    staged_path: Path | None = None
    asset: Any = None


@dataclass(slots=True)
class ImageHistoryMigrationResult:
    """Result of migrating one bounded conversation history snapshot."""

    history: list[dict[str, Any]]
    migrated_images: int = 0


def _legacy_image_url(part: Any) -> tuple[dict[str, Any], str] | None:
    """Extract supported legacy image blocks without interpreting other parts.

    Args:
        part: One persisted message content part.

    Returns:
        The original mapping and image source URL, or None for an unknown block.

    Raises:
        ImageHistoryMigrationError: A recognized image block has malformed data.
    """
    if isinstance(part, ImageURLPart):
        return part.model_dump(), part.image_url.url
    if not isinstance(part, dict) or part.get("type") != "image_url":
        return None

    value = part.get("image_url")
    if isinstance(value, dict):
        url = value.get("url")
    elif isinstance(value, str):
        url = value
    else:
        url = part.get("url")
    if not isinstance(url, str) or not url:
        raise ImageHistoryMigrationError("invalid_history")
    return part, url


def _checkpoint_image_groups(
    history: list[dict[str, Any]], images: list[_LegacyImage]
) -> tuple[list[dict[str, Any]], dict[tuple[int, int], str]]:
    """Bind inline images to existing boundaries or add boundaries to old turns.

    Args:
        history: The original database history snapshot.
        images: Inline image parts found in the history.

    Returns:
        A copied history and a mapping from source part position to checkpoint ID.

    Raises:
        ImageHistoryMigrationError: A malformed or ambiguous boundary is found.
    """
    existing_markers = [
        message
        for message in history
        if isinstance(message, dict) and message.get("role") == "_checkpoint"
    ]
    image_groups: dict[tuple[int, int], str] = {}
    if existing_markers:
        candidates_by_message: dict[int, list[_LegacyImage]] = {}
        for image in images:
            image.rewritten_message_index = image.message_index
            candidates_by_message.setdefault(image.message_index, []).append(image)
        pending: list[_LegacyImage] = []
        seen_checkpoints: set[str] = set()
        for message_index, message in enumerate(history):
            if not isinstance(message, dict):
                raise ImageHistoryMigrationError("invalid_history")
            if message.get("role") != "_checkpoint":
                pending.extend(candidates_by_message.get(message_index, ()))
                continue
            if candidates_by_message.get(message_index):
                raise ImageHistoryMigrationError("invalid_history")
            checkpoint_id = get_checkpoint_id(message)
            if not checkpoint_id or checkpoint_id in seen_checkpoints:
                raise ImageHistoryMigrationError("invalid_history")
            seen_checkpoints.add(checkpoint_id)
            for image in pending:
                image.checkpoint_id = checkpoint_id
                image_groups[(image.message_index, image.part_index)] = checkpoint_id
            pending.clear()
        if pending:
            # Inventing a turn after the last stored boundary could reorder the
            # existing checkpoint sequence, so leave this history untouched.
            raise ImageHistoryMigrationError("invalid_history")
        return copy.deepcopy(history), image_groups

    image_positions = {
        (image.message_index, image.part_index): image for image in images
    }
    rewritten: list[dict[str, Any]] = []
    mapping: dict[tuple[int, int], str] = {}
    pending: list[_LegacyImage] = []
    segment_started = False
    user_seen = False

    def close_segment() -> None:
        nonlocal pending
        checkpoint_id = str(uuid.uuid4())
        rewritten.append({"role": "_checkpoint", "content": {"id": checkpoint_id}})
        for image in pending:
            image.checkpoint_id = checkpoint_id
            mapping[(image.message_index, image.part_index)] = checkpoint_id
        pending = []

    for message_index, message in enumerate(history):
        if not isinstance(message, dict):
            raise ImageHistoryMigrationError("invalid_history")
        if message.get("role") == "user" and user_seen and segment_started:
            close_segment()
            segment_started = False
        if message.get("role") == "user":
            user_seen = True
        segment_started = True
        rewritten_message_index = len(rewritten)
        rewritten.append(copy.deepcopy(message))
        content = message.get("content")
        if isinstance(content, list):
            for part_index in range(len(content)):
                image = image_positions.get((message_index, part_index))
                if image is not None:
                    pending.append(image)
                    image.rewritten_message_index = rewritten_message_index
    if segment_started:
        close_segment()
    if len(mapping) != len(images):
        raise ImageHistoryMigrationError("invalid_history")
    return rewritten, mapping


def _stage_data_uri(url: str, temp_root: Path) -> Path:
    """Decode a bounded image data URI into an AstrBot-owned temporary file.

    Args:
        url: A supported base64 data URI.
        temp_root: Canonical AstrBot temporary directory.

    Returns:
        The path of the complete staged image.

    Raises:
        ImageHistoryMigrationError: The URI is invalid or staging failed.
        OSError: A process resource limit was reached.
        MemoryError: Decoding exhausted process memory.
    """
    header, separator, encoded = url.partition(",")
    if not separator or not header.lower().startswith("data:image/"):
        raise ImageHistoryMigrationError("unavailable")
    parameters = header[5:].split(";")
    if (
        not parameters
        or not parameters[0].lower().startswith("image/")
        or not any(item.lower() == "base64" for item in parameters[1:])
    ):
        raise ImageHistoryMigrationError("invalid_image")
    if len(encoded) > 4 * ((DEFAULT_MAX_FILE_BYTES + 2) // 3):
        raise ImageHistoryMigrationError("invalid_image")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ImageHistoryMigrationError("invalid_image") from None
    if not decoded or len(decoded) > DEFAULT_MAX_FILE_BYTES:
        raise ImageHistoryMigrationError("invalid_image")
    path = temp_root / f"image-history-migration-{uuid.uuid4()}.img"
    try:
        with path.open("xb") as stream:
            if stream.write(decoded) != len(decoded):
                raise OSError("Incomplete image staging write")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            if not is_recoverable_image_error(cleanup_error):
                raise
        if isinstance(exc, OSError):
            if not is_recoverable_image_error(exc):
                raise
            raise ImageHistoryMigrationError("storage_error") from None
        raise
    return path


def _resolve_temp_file(url: str, temp_root: Path) -> Path:
    """Resolve only a regular local file canonically contained in AstrBot temp.

    Args:
        url: A local absolute path or local file URI from legacy history.
        temp_root: Canonical AstrBot temporary directory.

    Returns:
        The canonical source path.

    Raises:
        ImageHistoryMigrationError: The source is remote, missing, unsafe, or too
            large to be a supported image.
        OSError: A process resource limit was reached.
    """
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() in {"http", "https"}:
        raise ImageHistoryMigrationError("unavailable")
    if parsed.scheme:
        if parsed.scheme.lower() != "file" or parsed.netloc not in {"", "localhost"}:
            if not (
                os.name == "nt"
                and len(parsed.scheme) == 1
                and len(url) > 2
                and url[1] == ":"
            ):
                raise ImageHistoryMigrationError("unavailable")
            source = Path(url)
        else:
            if parsed.query or parsed.fragment:
                raise ImageHistoryMigrationError("unavailable")
            source = Path(urllib.request.url2pathname(parsed.path))
    else:
        source = Path(url)
    if not source.is_absolute():
        raise ImageHistoryMigrationError("unavailable")
    try:
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ImageHistoryMigrationError("unavailable")
        resolved = source.resolve(strict=True)
        if not resolved.is_relative_to(temp_root) or not resolved.is_file():
            raise ImageHistoryMigrationError("unavailable")
        if resolved.stat().st_size > DEFAULT_MAX_FILE_BYTES:
            raise ImageHistoryMigrationError("invalid_image")
    except ImageHistoryMigrationError:
        raise
    except OSError as exc:
        if not is_recoverable_image_error(exc):
            raise
        raise ImageHistoryMigrationError("unavailable") from None
    except ValueError:
        raise ImageHistoryMigrationError("unavailable") from None
    return resolved


async def migrate_legacy_image_history(
    db: BaseDatabase,
    conversation_id: str,
    history: list[dict[str, Any]],
    *,
    user_id: str,
    platform_id: str,
) -> ImageHistoryMigrationResult:
    """Move supported legacy inline images to the managed library atomically.

    Only embedded image data and existing regular files under AstrBot's temporary
    directory are read. Remote URLs and paths elsewhere are never fetched or opened.
    Files are prepared and validated before one history/reference CAS is attempted.

    Args:
        db: AstrBot database containing the selected conversation.
        conversation_id: Server-selected conversation identity.
        history: The bounded history snapshot returned by the guarded reader.
        user_id: Expected conversation owner from the current event.
        platform_id: Expected platform from the current event.

    Returns:
        The committed history and number of image occurrences migrated.

    Raises:
        ImageHistoryMigrationError: An image, boundary, storage, or CAS failure
            prevents the complete conversation update.
        HistoryTooLargeError: Rewritten history would exceed the online read
            limit; its history and reference transaction is rolled back.
    """
    if not isinstance(history, list):
        raise ImageHistoryMigrationError("invalid_history")
    candidates: list[_LegacyImage] = []
    for message_index, message in enumerate(history):
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part_index, part in enumerate(content):
            legacy = _legacy_image_url(part)
            if legacy is None:
                continue
            original_part, url = legacy
            candidates.append(
                _LegacyImage(
                    message_index,
                    part_index,
                    copy.deepcopy(original_part),
                    url,
                )
            )
    if not candidates:
        return ImageHistoryMigrationResult(copy.deepcopy(history))

    try:
        conversation = await db.get_conversation_by_id(
            conversation_id, include_history=False
        )
    except SQLAlchemyError:
        raise ImageHistoryMigrationError("storage_error") from None
    if (
        conversation is None
        or conversation.user_id != user_id
        or conversation.platform_id != platform_id
    ):
        raise ImageHistoryMigrationError("history_changed")

    rewritten, checkpoint_groups = _checkpoint_image_groups(history, candidates)
    for image in candidates:
        image.checkpoint_id = checkpoint_groups[(image.message_index, image.part_index)]

    temp_root = Path(get_astrbot_temp_path())
    try:
        temp_root.mkdir(parents=True, exist_ok=True)
        temp_root = temp_root.resolve(strict=True)
    except OSError as exc:
        if not is_recoverable_image_error(exc):
            raise
        raise ImageHistoryMigrationError("storage_error") from None

    staged_paths: list[Path] = []
    references: list[ConversationImageRef] = []
    try:
        for image in candidates:
            if image.url.lower().startswith("data:"):
                image.staged_path = _stage_data_uri(image.url, temp_root)
                image.source_path = image.staged_path
                staged_paths.append(image.staged_path)
            else:
                image.source_path = _resolve_temp_file(image.url, temp_root)

        store = ImageAssetStore(
            db,
            max_pixels=MAX_CONTEXT_IMAGE_PIXELS,
            max_frames=MAX_CONTEXT_IMAGE_FRAMES,
        )
        required_bytes = 0
        for image in candidates:
            assert image.source_path is not None
            try:
                info = image.source_path.lstat()
            except OSError as exc:
                if not is_recoverable_image_error(exc):
                    raise
                raise ImageHistoryMigrationError("unavailable") from None
            if not stat.S_ISREG(info.st_mode) or info.st_size > DEFAULT_MAX_FILE_BYTES:
                raise ImageHistoryMigrationError("invalid_image")
            required_bytes += info.st_size
            try:
                await run_image_io(
                    validate_image_source,
                    image.source_path,
                    MAX_CONTEXT_IMAGE_PIXELS,
                    MAX_CONTEXT_IMAGE_FRAMES,
                )
            except (ImageStorageLimitError, ValueError):
                raise ImageHistoryMigrationError("invalid_image") from None
            except OSError as exc:
                if not is_recoverable_image_error(exc):
                    raise
                if isinstance(exc, ImageValidationError):
                    raise ImageHistoryMigrationError("invalid_image") from None
                raise ImageHistoryMigrationError("storage_error") from None

        used_bytes = 0
        try:
            for entry in store.root.iterdir():
                if entry.name == ".store.lock":
                    continue
                info = entry.lstat()
                if not stat.S_ISREG(info.st_mode):
                    raise OSError("Unexpected image store entry")
                used_bytes += info.st_size
        except OSError as exc:
            if not is_recoverable_image_error(exc):
                raise
            raise ImageHistoryMigrationError("storage_error") from None
        if required_bytes > store.max_total_bytes - used_bytes:
            raise ImageHistoryMigrationError("library_full")

        for image in candidates:
            assert image.source_path is not None
            try:
                image.asset = await store.import_file(
                    image.source_path, source_kind="legacy_model_input"
                )
            except ImageStorageCapacityError:
                raise ImageHistoryMigrationError("library_full") from None
            except (ImageStorageLimitError, ValueError):
                raise ImageHistoryMigrationError("invalid_image") from None
            except OSError as exc:
                if not is_recoverable_image_error(exc):
                    raise
                if isinstance(exc, ImageValidationError):
                    raise ImageHistoryMigrationError("invalid_image") from None
                raise ImageHistoryMigrationError("storage_error") from None
            except SQLAlchemyError:
                raise ImageHistoryMigrationError("storage_error") from None

        positions_by_message: dict[int, list[int]] = {}
        for image in candidates:
            positions_by_message.setdefault(image.message_index, []).append(
                image.part_index
            )
        for image in candidates:
            occurrence_id = str(uuid.uuid4())
            part = ImageRefPart(
                occurrence_id=occurrence_id,
                asset_id=image.asset.asset_id,
                description="",
                description_status="pending",
            )
            rewritten[image.rewritten_message_index]["content"][image.part_index] = (
                part.model_dump()
            )
            image_index = positions_by_message[image.message_index].index(
                image.part_index
            )
            references.append(
                ConversationImageRef(
                    conversation_id=conversation_id,
                    occurrence_id=occurrence_id,
                    asset_id=image.asset.asset_id,
                    checkpoint_id=image.checkpoint_id,
                    image_index=image_index,
                    description_status="pending",
                )
            )

        try:
            await db.update_conversation(
                cid=conversation_id,
                content=rewritten,
                image_refs=references,
                expected_history=history,
                expected_identity=(user_id, platform_id),
            )
        except HistoryTooLargeError:
            raise
        except (ValueError, PermissionError):
            raise ImageHistoryMigrationError("history_changed") from None
        except SQLAlchemyError:
            raise ImageHistoryMigrationError("storage_error") from None
        return ImageHistoryMigrationResult(rewritten, len(candidates))
    except ImageHistoryMigrationError:
        raise
    except SQLAlchemyError:
        raise ImageHistoryMigrationError("storage_error") from None
    finally:
        for staged in staged_paths:
            try:
                staged.unlink(missing_ok=True)
            except OSError as exc:
                if not is_recoverable_image_error(exc):
                    raise
                pass
