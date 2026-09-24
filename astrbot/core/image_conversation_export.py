"""Build a portable, single-conversation archive with active image assets."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import uuid
import zipfile
from pathlib import Path

from sqlalchemy import case, func, select, text

from astrbot.core.conversation_history_limits import (
    MAX_ONLINE_HISTORY_BYTES,
    HistoryTooLargeError,
    history_size_bytes,
)
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import (
    ConversationImageCheckpoint,
    ConversationImageRef,
    ConversationV2,
    ImageAsset,
    PlatformSession,
)
from astrbot.core.image_asset_store import (
    COPY_CHUNK_BYTES,
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_MAX_TOTAL_BYTES,
    ImageAssetStore,
)
from astrbot.core.image_context import (
    MAX_CONTEXT_IMAGE_FRAMES,
    MAX_CONTEXT_IMAGE_PIXELS,
)
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.datetime_utils import to_utc_timestamp

EXPORT_PAGE_SIZE = 20
MEDIA_EXTENSIONS = {
    "image/avif": ".avif",
    "image/bmp": ".bmp",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
}


class ImageConversationExportError(ValueError):
    """Raised when a conversation cannot be exported as a complete media archive."""


async def build_image_conversation_export(
    db: BaseDatabase,
    conversation_id: str,
    *,
    user_id: str,
    platform_id: str,
) -> Path:
    """Create a bounded ZIP containing one conversation and its active images.

    Args:
        db: Database containing the selected conversation and image registry.
        conversation_id: Server-selected conversation identity.
        user_id: Server-selected conversation owner.
        platform_id: Server-selected conversation platform.

    Returns:
        Path to the completed temporary ZIP archive.

    Raises:
        HistoryTooLargeError: Stored history exceeds the 16 MiB online limit.
        ImageConversationExportError: The conversation or one of its active images
            is unavailable, invalid, or exceeds the existing image-store budget.
        OSError: The temporary archive or image store cannot be read or written.
    """
    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)
    descriptor, output_name = tempfile.mkstemp(
        prefix="astrbot_image_conversation_", suffix=".zip", dir=temp_dir
    )
    os.close(descriptor)
    output_path = Path(output_name)
    try:
        store = ImageAssetStore(
            db,
            max_pixels=MAX_CONTEXT_IMAGE_PIXELS,
            max_frames=MAX_CONTEXT_IMAGE_FRAMES,
        )

        async with db.get_db() as session, session.begin():
            # sqlite3's legacy transaction mode does not start a read
            # transaction for SELECT. Explicit BEGIN pins one WAL snapshot for
            # every metadata page below while allowing concurrent writers.
            await session.execute(text("BEGIN"))
            history_bytes_expression = history_size_bytes(ConversationV2.content)
            result = await session.execute(
                select(
                    ConversationV2.conversation_id,
                    ConversationV2.user_id,
                    ConversationV2.platform_id,
                    ConversationV2.title,
                    ConversationV2.persona_id,
                    ConversationV2.created_at,
                    ConversationV2.updated_at,
                    history_bytes_expression.label("history_bytes"),
                    case(
                        (
                            history_bytes_expression <= MAX_ONLINE_HISTORY_BYTES,
                            ConversationV2.content,
                        ),
                        else_=None,
                    ).label("bounded_content"),
                ).where(
                    ConversationV2.conversation_id == conversation_id,
                    ConversationV2.user_id == user_id,
                    ConversationV2.platform_id == platform_id,
                )
            )
            conversation = result.one_or_none()
            if conversation is None:
                raise ImageConversationExportError("Conversation does not exist")
            history_bytes = int(conversation.history_bytes)
            if history_bytes > MAX_ONLINE_HISTORY_BYTES:
                raise HistoryTooLargeError(
                    conversation_id, history_bytes, MAX_ONLINE_HISTORY_BYTES
                )

            content = conversation.bounded_content
            if content is None:
                content = []
            if not isinstance(content, list):
                raise ImageConversationExportError("Conversation history is invalid")

            # A damaged registry must fail the whole archive instead of being
            # silently filtered out by the paginated asset joins below.
            missing_asset = await session.scalar(
                select(ConversationImageRef.occurrence_id)
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
                .outerjoin(
                    ImageAsset, ImageAsset.asset_id == ConversationImageRef.asset_id
                )
                .where(
                    ConversationImageRef.conversation_id == conversation_id,
                    ConversationImageCheckpoint.active == True,  # noqa: E712
                    ImageAsset.asset_id.is_(None),
                )
                .limit(1)
            )
            if missing_asset is not None:
                raise ImageConversationExportError(
                    "An active image has no asset metadata"
                )

            title = conversation.title
            if not title and platform_id == "webchat" and "!" in user_id:
                session_id = user_id.rsplit("!", 1)[-1]
                title = await session.scalar(
                    select(PlatformSession.display_name).where(
                        PlatformSession.session_id == session_id
                    )
                )

            record = {
                "cid": conversation_id,
                "user_id": user_id,
                "platform_id": platform_id,
                "title": title or None,
                "persona_id": conversation.persona_id,
                "created_at": int(to_utc_timestamp(conversation.created_at) or 0),
                "updated_at": int(to_utc_timestamp(conversation.updated_at) or 0),
                "content": content,
            }
            manifest = {
                "format": "astrbot-image-conversation",
                "version": 1,
                "conversation": "conversation.jsonl",
                "image_references": "image_refs.jsonl",
                "media_prefix": "media/",
                "media_bytes_limit": DEFAULT_MAX_TOTAL_BYTES,
                "imports_into_astrbot": False,
            }

            with zipfile.ZipFile(
                output_path, "w", compression=zipfile.ZIP_STORED
            ) as archive:
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                )
                archive.writestr(
                    "conversation.jsonl",
                    json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                )

                total_media_bytes = 0
                asset_cursor = ""
                while True:
                    asset_page = await session.execute(
                        select(
                            ImageAsset,
                            func.min(ConversationImageRef.occurrence_id).label(
                                "authorized_occurrence_id"
                            ),
                        )
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
                            ConversationImageRef.conversation_id == conversation_id,
                            ConversationV2.user_id == user_id,
                            ConversationV2.platform_id == platform_id,
                            ConversationImageCheckpoint.active == True,  # noqa: E712
                            ImageAsset.asset_id > asset_cursor,
                        )
                        .group_by(*ImageAsset.__table__.columns)
                        .order_by(ImageAsset.asset_id)
                        .limit(EXPORT_PAGE_SIZE)
                    )
                    assets = asset_page.all()
                    if not assets:
                        break

                    for asset, authorized_occurrence_id in assets:
                        if asset.state != "available":
                            raise ImageConversationExportError(
                                "An active image is unavailable"
                            )
                        try:
                            valid_asset_id = str(uuid.UUID(asset.asset_id))
                        except (AttributeError, ValueError) as exc:
                            raise ImageConversationExportError(
                                "An active image has an invalid identifier"
                            ) from exc
                        if (
                            valid_asset_id != asset.asset_id
                            or asset.storage_key != f"{asset.asset_id}.img"
                            or not 0 < asset.byte_size <= DEFAULT_MAX_FILE_BYTES
                            or asset.mime_type not in MEDIA_EXTENSIONS
                        ):
                            raise ImageConversationExportError(
                                "An active image has invalid metadata"
                            )
                        total_media_bytes += asset.byte_size
                        if total_media_bytes > DEFAULT_MAX_TOTAL_BYTES:
                            raise ImageConversationExportError(
                                "Conversation images exceed the image-store capacity"
                            )

                        member_name = (
                            f"media/{asset.asset_id}{MEDIA_EXTENSIONS[asset.mime_type]}"
                        )
                        digest = hashlib.sha256()
                        copied_bytes = 0
                        async with store.open_image(
                            conversation_id=conversation_id,
                            occurrence_id=authorized_occurrence_id,
                            user_id=user_id,
                            platform_id=platform_id,
                        ) as source:
                            with archive.open(member_name, "w") as target:
                                while chunk := source.read(COPY_CHUNK_BYTES):
                                    copied_bytes += len(chunk)
                                    if copied_bytes > asset.byte_size:
                                        raise ImageConversationExportError(
                                            "An image changed while it was exported"
                                        )
                                    digest.update(chunk)
                                    target.write(chunk)
                                    await asyncio.sleep(0)
                        if (
                            copied_bytes != asset.byte_size
                            or digest.hexdigest() != asset.sha256
                        ):
                            raise ImageConversationExportError(
                                "An active image failed integrity verification"
                            )
                        asset_cursor = asset.asset_id

                with archive.open("image_refs.jsonl", "w") as refs_file:
                    cursor: tuple[int, str] | None = None
                    while True:
                        statement = (
                            select(
                                ConversationImageRef,
                                ConversationImageCheckpoint.sequence,
                                ImageAsset,
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
                            .join(
                                ConversationV2,
                                ConversationV2.conversation_id
                                == ConversationImageRef.conversation_id,
                            )
                            .join(
                                ImageAsset,
                                ImageAsset.asset_id == ConversationImageRef.asset_id,
                            )
                            .where(
                                ConversationImageRef.conversation_id == conversation_id,
                                ConversationV2.user_id == user_id,
                                ConversationV2.platform_id == platform_id,
                                ConversationImageCheckpoint.active == True,  # noqa: E712
                            )
                        )
                        if cursor is not None:
                            sequence, occurrence_id = cursor
                            statement = statement.where(
                                (ConversationImageCheckpoint.sequence > sequence)
                                | (
                                    (ConversationImageCheckpoint.sequence == sequence)
                                    & (
                                        ConversationImageRef.occurrence_id
                                        > occurrence_id
                                    )
                                )
                            )
                        statement = statement.order_by(
                            ConversationImageCheckpoint.sequence,
                            ConversationImageRef.occurrence_id,
                        ).limit(EXPORT_PAGE_SIZE)
                        rows = (await session.execute(statement)).all()
                        if not rows:
                            break

                        for reference, sequence, asset in rows:
                            if asset.state != "available":
                                raise ImageConversationExportError(
                                    "An active image is unavailable"
                                )
                            extension = MEDIA_EXTENSIONS.get(asset.mime_type)
                            if extension is None:
                                raise ImageConversationExportError(
                                    "An active image has an unsupported media type"
                                )
                            image_record = reference.model_dump(mode="json")
                            image_record.update(
                                checkpoint_sequence=sequence,
                                media_path=f"media/{asset.asset_id}{extension}",
                                mime_type=asset.mime_type,
                                byte_size=asset.byte_size,
                                width=asset.width,
                                height=asset.height,
                                sha256=asset.sha256,
                            )
                            refs_file.write(
                                (
                                    json.dumps(
                                        image_record,
                                        ensure_ascii=False,
                                        separators=(",", ":"),
                                    )
                                    + "\n"
                                ).encode("utf-8")
                            )
                            cursor = (sequence, reference.occurrence_id)
                        await asyncio.sleep(0)

        return output_path
    except BaseException:
        output_path.unlink(missing_ok=True)
        raise
