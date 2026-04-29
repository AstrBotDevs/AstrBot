import json
import mimetypes
import shutil
import uuid
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from astrbot.core.db.po import Attachment
from astrbot.core.message.components import (
    File,
    Image,
    Json,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.core.message.message_event_result import MessageChain

AttachmentGetter = Callable[[str], Awaitable[Attachment | None]]
AttachmentInserter = Callable[..., Awaitable[Attachment | None]]
ReplyHistoryGetter = Callable[
    [Any],
    Awaitable[tuple[list[dict], str | None, str | None] | None],
]

MEDIA_PART_TYPES = {"image", "record", "file", "video"}


def strip_message_parts_path_fields(message_parts: list[dict]) -> list[dict]:
    return [{k: v for k, v in part.items() if k != "path"} for part in message_parts]


def webchat_message_parts_have_content(message_parts: list[dict]) -> bool:
    return any(
        part.get("type") in ("plain", "image", "record", "file", "video")
        and (part.get("text") or part.get("attachment_id") or part.get("filename"))
        for part in message_parts
    )


async def parse_webchat_message_parts(
    message_parts: list,
    *,
    strict: bool = False,
    include_empty_plain: bool = False,
    verify_media_path_exists: bool = True,
    reply_history_getter: ReplyHistoryGetter | None = None,
    current_depth: int = 0,
    max_reply_depth: int = 0,
    cast_reply_id_to_str: bool = True,
) -> tuple[list, list[str], bool]:
    """Parse webchat message parts into components/text parts.

    Returns:
        tuple[list, list[str], bool]:
            (components, plain_text_parts, has_non_reply_content)
    """
    components = []
    text_parts: list[str] = []
    has_content = False

    for part in message_parts:
        if not isinstance(part, dict):
            if strict:
                raise ValueError("message part must be an object")
            continue

        part_type = str(part.get("type", "")).strip()
        if part_type == "plain":
            text = str(part.get("text", ""))
            if text or include_empty_plain:
                components.append(Plain(text=text))
                text_parts.append(text)
            if text:
                has_content = True
            continue

        if part_type == "reply":
            message_id = part.get("message_id")
            if message_id is None:
                if strict:
                    raise ValueError("reply part missing message_id")
                continue

            reply_chain = []
            reply_message_str = str(part.get("selected_text", ""))
            sender_id = None
            sender_name = None

            if reply_message_str:
                reply_chain = [Plain(text=reply_message_str)]
            elif (
                reply_history_getter
                and current_depth < max_reply_depth
                and message_id is not None
            ):
                reply_info = await reply_history_getter(message_id)
                if reply_info:
                    reply_parts, sender_id, sender_name = reply_info
                    (
                        reply_chain,
                        reply_text_parts,
                        _,
                    ) = await parse_webchat_message_parts(
                        reply_parts,
                        strict=strict,
                        include_empty_plain=include_empty_plain,
                        verify_media_path_exists=verify_media_path_exists,
                        reply_history_getter=reply_history_getter,
                        current_depth=current_depth + 1,
                        max_reply_depth=max_reply_depth,
                        cast_reply_id_to_str=cast_reply_id_to_str,
                    )
                    reply_message_str = "".join(reply_text_parts)

            reply_id = str(message_id) if cast_reply_id_to_str else message_id
            components.append(
                Reply(
                    id=reply_id,
                    message_str=reply_message_str,
                    chain=reply_chain,
                    sender_id=sender_id,
                    sender_nickname=sender_name,
                )
            )
            continue

        if part_type not in MEDIA_PART_TYPES:
            if strict:
                raise ValueError(f"unsupported message part type: {part_type}")
            continue

        path = part.get("path")
        if not path:
            if strict:
                raise ValueError(f"{part_type} part missing path")
            continue

        file_path = Path(str(path))
        if verify_media_path_exists and not file_path.exists():
            if strict:
                raise ValueError(f"file not found: {file_path!s}")
            continue

        file_path_str = (
            str(file_path.resolve()) if verify_media_path_exists else str(file_path)
        )
        has_content = True
        if part_type == "image":
            components.append(Image.fromFileSystem(file_path_str))
        elif part_type == "record":
            components.append(Record.fromFileSystem(file_path_str))
        elif part_type == "video":
            components.append(Video.fromFileSystem(file_path_str))
        else:
            filename = str(part.get("filename", "")).strip() or file_path.name
            components.append(File(name=filename, file=file_path_str))

    return components, text_parts, has_content


async def build_webchat_message_parts(
    message_payload: str | list,
    *,
    get_attachment_by_id: AttachmentGetter,
    strict: bool = False,
    attachments_dir: str | Path | None = None,
) -> list[dict]:
    if isinstance(message_payload, str):
        text = message_payload.strip()
        return [{"type": "plain", "text": text}] if text else []

    if not isinstance(message_payload, list):
        if strict:
            raise ValueError("message must be a string or list")
        return []

    message_parts: list[dict] = []
    for part in message_payload:
        if not isinstance(part, dict):
            if strict:
                raise ValueError("message part must be an object")
            continue

        part_type = str(part.get("type", "")).strip()
        if part_type == "plain":
            text = str(part.get("text", ""))
            if text:
                message_parts.append({"type": "plain", "text": text})
            continue

        if part_type == "reply":
            message_id = part.get("message_id")
            if message_id is None:
                if strict:
                    raise ValueError("reply part missing message_id")
                continue
            message_parts.append(
                {
                    "type": "reply",
                    "message_id": message_id,
                    "selected_text": str(part.get("selected_text", "")),
                }
            )
            continue

        if part_type not in MEDIA_PART_TYPES:
            if strict:
                raise ValueError(f"unsupported message part type: {part_type}")
            continue

        attachment_id = part.get("attachment_id")
        if not attachment_id:
            if strict:
                raise ValueError(f"{part_type} part missing attachment_id")
            continue

        attachment = await get_attachment_by_id(str(attachment_id))
        if not attachment:
            if strict:
                raise ValueError(f"attachment not found: {attachment_id}")
            continue

        attachment_path = Path(attachment.path)
        display_name = attachment.original_filename or attachment_path.name
        # Resolve relative paths to absolute for runtime usage
        if attachments_dir is not None and not attachment_path.is_absolute():
            attachment_path = Path(attachments_dir) / attachment_path
        message_parts.append(
            {
                "type": attachment.type,
                "attachment_id": attachment.attachment_id,
                "filename": display_name,
                "path": str(attachment_path),
            }
        )

    return message_parts


def webchat_message_parts_to_message_chain(
    message_parts: list[dict],
    *,
    strict: bool = False,
) -> MessageChain:
    components = []
    has_content = False

    for part in message_parts:
        if not isinstance(part, dict):
            if strict:
                raise ValueError("message part must be an object")
            continue

        part_type = str(part.get("type", "")).strip()
        if part_type == "plain":
            text = str(part.get("text", ""))
            if text:
                components.append(Plain(text=text))
                has_content = True
            continue

        if part_type == "reply":
            message_id = part.get("message_id")
            if message_id is None:
                if strict:
                    raise ValueError("reply part missing message_id")
                continue
            components.append(
                Reply(
                    id=str(message_id),
                    message_str=str(part.get("selected_text", "")),
                    chain=[],
                )
            )
            continue

        if part_type not in MEDIA_PART_TYPES:
            if strict:
                raise ValueError(f"unsupported message part type: {part_type}")
            continue

        path = part.get("path")
        if not path:
            if strict:
                raise ValueError(f"{part_type} part missing path")
            continue

        file_path = Path(str(path))
        if not file_path.exists():
            if strict:
                raise ValueError(f"file not found: {file_path!s}")
            continue

        file_path_str = str(file_path.resolve())
        has_content = True
        if part_type == "image":
            components.append(Image.fromFileSystem(file_path_str))
        elif part_type == "record":
            components.append(Record.fromFileSystem(file_path_str))
        elif part_type == "video":
            components.append(Video.fromFileSystem(file_path_str))
        else:
            filename = str(part.get("filename", "")).strip() or file_path.name
            components.append(File(name=filename, file=file_path_str))

    if strict and (not components or not has_content):
        raise ValueError("Message content is empty (reply only is not allowed)")

    return MessageChain(chain=components)


async def build_message_chain_from_payload(
    message_payload: str | list,
    *,
    get_attachment_by_id: AttachmentGetter,
    strict: bool = True,
    attachments_dir: str | Path | None = None,
) -> MessageChain:
    message_parts = await build_webchat_message_parts(
        message_payload,
        get_attachment_by_id=get_attachment_by_id,
        strict=strict,
        attachments_dir=attachments_dir,
    )
    components, _, has_content = await parse_webchat_message_parts(
        message_parts,
        strict=strict,
    )
    if strict and (not components or not has_content):
        raise ValueError("Message content is empty (reply only is not allowed)")
    return MessageChain(chain=components)


async def create_attachment_part_from_existing_file(
    filename: str,
    *,
    attach_type: str,
    insert_attachment: AttachmentInserter,
    attachments_dir: str | Path,
    fallback_dirs: Sequence[str | Path] = (),
    creator: str | None = None,
    session_id: str | None = None,
) -> dict | None:
    basename = Path(filename).name
    attachments_dir = Path(attachments_dir)

    # Search in attachments_dir (including subdirectories) and fallback_dirs
    candidate_paths: list[Path] = []
    if attachments_dir.exists():
        candidate_paths.extend(attachments_dir.rglob(basename))
    candidate_paths.extend(Path(p) / basename for p in fallback_dirs)

    file_path = next((path for path in candidate_paths if path.exists()), None)
    if not file_path:
        return None

    # Compute relative path if inside attachments_dir, otherwise absolute
    try:
        rel_path = str(file_path.relative_to(attachments_dir))
    except ValueError:
        rel_path = str(file_path)

    mime_type, _ = mimetypes.guess_type(str(file_path))
    attachment = await insert_attachment(
        rel_path,
        attach_type,
        mime_type or "application/octet-stream",
        original_filename=basename,
        creator=creator,
        session_id=session_id,
    )
    if not attachment:
        return None

    return {
        "type": attach_type,
        "attachment_id": attachment.attachment_id,
        "filename": basename,
    }


async def message_chain_to_storage_message_parts(
    message_chain: MessageChain,
    *,
    insert_attachment: AttachmentInserter,
    attachments_dir: str | Path,
    conversation_id: str,
) -> list[dict]:
    target_dir = Path(attachments_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    parts: list[dict] = []
    for comp in message_chain.chain:
        if isinstance(comp, Plain):
            if comp.text:
                parts.append({"type": "plain", "text": comp.text})
            continue

        if isinstance(comp, Json):
            parts.append(
                {"type": "plain", "text": json.dumps(comp.data, ensure_ascii=False)}
            )
            continue

        if isinstance(comp, Image):
            file_path = await comp.convert_to_file_path()
            attachment_part = await _copy_file_to_attachment_part(
                file_path=file_path,
                attach_type="image",
                insert_attachment=insert_attachment,
                attachments_dir=target_dir,
                session_id=conversation_id,
            )
            if attachment_part:
                parts.append(attachment_part)
            continue

        if isinstance(comp, Record):
            file_path = await comp.convert_to_file_path()
            attachment_part = await _copy_file_to_attachment_part(
                file_path=file_path,
                attach_type="record",
                insert_attachment=insert_attachment,
                attachments_dir=target_dir,
                session_id=conversation_id,
            )
            if attachment_part:
                parts.append(attachment_part)
            continue

        if isinstance(comp, Video):
            file_path = await comp.convert_to_file_path()
            attachment_part = await _copy_file_to_attachment_part(
                file_path=file_path,
                attach_type="video",
                insert_attachment=insert_attachment,
                attachments_dir=target_dir,
                session_id=conversation_id,
            )
            if attachment_part:
                parts.append(attachment_part)
            continue

        if isinstance(comp, File):
            file_path = await comp.get_file()
            attachment_part = await _copy_file_to_attachment_part(
                file_path=file_path,
                attach_type="file",
                insert_attachment=insert_attachment,
                attachments_dir=target_dir,
                display_name=comp.name,
                session_id=conversation_id,
            )
            if attachment_part:
                parts.append(attachment_part)
            continue

    return parts


async def _copy_file_to_attachment_part(
    *,
    file_path: str,
    attach_type: str,
    insert_attachment: AttachmentInserter,
    attachments_dir: Path,
    display_name: str | None = None,
    creator: str | None = None,
    session_id: str | None = None,
) -> dict | None:
    import datetime

    src_path = Path(file_path)
    if not src_path.exists() or not src_path.is_file():
        return None

    suffix = src_path.suffix
    random_name = f"{uuid.uuid4().hex}{suffix}"
    date_dir = datetime.datetime.now().strftime("%Y/%m/%d")
    target_dir = attachments_dir / date_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / random_name
    shutil.copy2(src_path, target_path)

    rel_path = str(Path(date_dir) / random_name)
    mime_type, _ = mimetypes.guess_type(target_path.name)
    attachment = await insert_attachment(
        rel_path,
        attach_type,
        mime_type or "application/octet-stream",
        original_filename=display_name or src_path.name,
        creator=creator,
        session_id=session_id,
    )
    if not attachment:
        return None

    return {
        "type": attach_type,
        "attachment_id": attachment.attachment_id,
        "filename": display_name or src_path.name,
    }
