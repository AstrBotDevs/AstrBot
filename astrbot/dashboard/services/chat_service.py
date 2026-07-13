from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from collections.abc import AsyncIterator
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from astrbot.core import logger, sp
from astrbot.core.agent.message import get_checkpoint_id, is_checkpoint_message
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.webchat.message_parts_helper import (
    build_webchat_message_parts,
    create_attachment_part_from_existing_file,
    strip_message_parts_path_fields,
    webchat_message_parts_have_content,
)
from astrbot.core.platform.sources.webchat.webchat_queue_mgr import webchat_queue_mgr
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.datetime_utils import to_utc_isoformat
from astrbot.core.utils.media_utils import (
    MEDIA_MIME_EXTENSIONS,
    detect_image_mime_type_async,
)

SSE_HEARTBEAT = ": heartbeat\n\n"
CHAT_RUN_SUBSCRIBER_QUEUE_SIZE = 256


def sanitize_upload_filename(filename: str | None) -> str:
    if not filename:
        return f"{uuid.uuid4()!s}"
    normalized = filename.replace("\\", "/")
    name = PurePosixPath(normalized).name.replace("\x00", "").strip()
    if name in ("", ".", ".."):
        return f"{uuid.uuid4()!s}"
    return name


def normalize_reasoning_message_parts(
    message_parts: list[dict] | None,
    reasoning: str = "",
) -> list[dict]:
    parts: list[dict] = []
    for part in message_parts or []:
        if not isinstance(part, dict):
            continue
        copied = dict(part)
        if copied.get("type") == "reasoning":
            copied = {"type": "think", "think": copied.get("text", "")}
        parts.append(copied)
    if reasoning and not any(part.get("type") == "think" for part in parts):
        parts.insert(0, {"type": "think", "think": reasoning})
    return parts


def extract_reasoning_from_message_parts(message_parts: list[dict]) -> str:
    reasoning_parts: list[str] = []
    for part in message_parts:
        if part.get("type") != "think":
            continue
        think = part.get("think")
        if isinstance(think, str) and think:
            reasoning_parts.append(think)
    return "".join(reasoning_parts)


def collect_plain_text_from_message_parts(message_parts: list[dict]) -> str:
    text_parts: list[str] = []
    for part in message_parts:
        if part.get("type") != "plain":
            continue
        text = part.get("text")
        if isinstance(text, str) and text:
            text_parts.append(text)
    return "".join(text_parts)


def build_bot_history_content(
    message_parts: list[dict],
    *,
    agent_stats: dict | None = None,
    refs: dict | None = None,
    include_reasoning_field: bool = True,
) -> dict[str, Any]:
    normalized_parts = normalize_reasoning_message_parts(message_parts)
    content: dict[str, Any] = {"type": "bot", "message": normalized_parts}
    reasoning = extract_reasoning_from_message_parts(normalized_parts)
    if reasoning and include_reasoning_field:
        content["reasoning"] = reasoning
    if agent_stats:
        content["agent_stats"] = agent_stats
    if refs:
        content["refs"] = refs
    return content


class BotMessageAccumulator:
    def __init__(self) -> None:
        self.parts: list[dict] = []
        self.pending_text = ""
        self.pending_tool_calls: dict[str, dict] = {}

    def has_content(self) -> bool:
        return bool(self.parts or self.pending_text or self.pending_tool_calls)

    def add_plain(
        self,
        result_text: str,
        *,
        chain_type: str | None,
        streaming: bool,
    ) -> None:
        if chain_type == "tool_call":
            self._flush_pending_text()
            self._store_tool_call(result_text)
            return

        if chain_type == "tool_call_result":
            self._flush_pending_text()
            self._store_tool_call_result(result_text)
            return

        if chain_type == "reasoning":
            self._flush_pending_text()
            self._append_think_part(result_text)
            return

        if streaming:
            self.pending_text += result_text
        else:
            self.pending_text = result_text

    def add_attachment(self, part: dict | None) -> None:
        if not part:
            return
        self._flush_pending_text()
        self.parts.append(part)

    def build_message_parts(
        self, *, include_pending_tool_calls: bool = False
    ) -> list[dict]:
        self._flush_pending_text()
        if include_pending_tool_calls and self.pending_tool_calls:
            for tool_call in self.pending_tool_calls.values():
                self.parts.append({"type": "tool_call", "tool_calls": [tool_call]})
            self.pending_tool_calls = {}
        return self.parts

    def plain_text(self) -> str:
        return collect_plain_text_from_message_parts(self.build_message_parts())

    def reasoning_text(self) -> str:
        return extract_reasoning_from_message_parts(self.build_message_parts())

    def _flush_pending_text(self) -> None:
        if not self.pending_text:
            return

        if self.parts and self.parts[-1].get("type") == "plain":
            last_text = self.parts[-1].get("text")
            self.parts[-1]["text"] = f"{last_text or ''}{self.pending_text}"
        else:
            self.parts.append({"type": "plain", "text": self.pending_text})
        self.pending_text = ""

    def _append_think_part(self, text: str) -> None:
        if not text:
            return

        if self.parts and self.parts[-1].get("type") == "think":
            last_text = self.parts[-1].get("think")
            self.parts[-1]["think"] = f"{last_text or ''}{text}"
        else:
            self.parts.append({"type": "think", "think": text})

    def _store_tool_call(self, result_text: str) -> None:
        tool_call = self._parse_json_object(result_text)
        if not tool_call:
            return
        tool_call_id = str(tool_call.get("id") or "")
        if not tool_call_id:
            return
        self.pending_tool_calls[tool_call_id] = tool_call

    def _store_tool_call_result(self, result_text: str) -> None:
        tool_result = self._parse_json_object(result_text)
        if not tool_result:
            return

        tool_call_id = str(tool_result.get("id") or "")
        if not tool_call_id:
            return

        tool_call = self.pending_tool_calls.pop(tool_call_id, None) or {
            "id": tool_call_id
        }
        tool_call["result"] = tool_result.get("result")
        tool_call["finished_ts"] = tool_result.get("ts")
        self.parts.append({"type": "tool_call", "tool_calls": [tool_call]})

    @staticmethod
    def _parse_json_object(raw_text: str) -> dict | None:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


def extract_web_search_refs(accumulated_text: str, accumulated_parts: list) -> dict:
    supported = [
        "web_search_baidu",
        "web_search_tavily",
        "web_search_bocha",
        "web_search_brave",
    ]
    web_search_results = {}
    tool_call_parts = [
        p
        for p in accumulated_parts
        if p.get("type") == "tool_call" and p.get("tool_calls")
    ]

    for part in tool_call_parts:
        for tool_call in part["tool_calls"]:
            if tool_call.get("name") not in supported or not tool_call.get("result"):
                continue
            try:
                result_data = json.loads(tool_call["result"])
                for item in result_data.get("results", []):
                    if idx := item.get("index"):
                        web_search_results[idx] = {
                            "url": item.get("url"),
                            "title": item.get("title"),
                            "snippet": item.get("snippet"),
                        }
            except (json.JSONDecodeError, KeyError):
                pass

    if not web_search_results:
        return {}

    ref_indices = {m.strip() for m in re.findall(r"<ref>(.*?)</ref>", accumulated_text)}
    used_refs = []
    for ref_index in ref_indices:
        if ref_index not in web_search_results:
            continue
        payload = {"index": ref_index, **web_search_results[ref_index]}
        if favicon := sp.temporary_cache.get("_ws_favicon", {}).get(payload["url"]):
            payload["favicon"] = favicon
        used_refs.append(payload)

    return {"used": used_refs} if used_refs else {}


def sanitize_message_content(content: dict) -> dict:
    if not isinstance(content, dict):
        raise ValueError("Missing key: content")

    normalized = deepcopy(content)
    message_type = normalized.get("type")
    if message_type not in {"user", "bot"}:
        raise ValueError("Invalid key: content.type")

    message_parts = normalized.get("message")
    if not isinstance(message_parts, list):
        raise ValueError("Missing key: content.message")
    normalized["message"] = strip_message_parts_path_fields(message_parts)
    return normalized


def extract_platform_message_text(content: dict | None) -> str:
    if not isinstance(content, dict):
        return ""
    message_parts = content.get("message")
    if not isinstance(message_parts, list):
        return ""
    texts: list[str] = []
    for part in message_parts:
        if isinstance(part, dict) and part.get("type") == "plain":
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)
    return "".join(texts)


def build_webchat_unified_msg_origin(session) -> str:
    message_type = (
        MessageType.GROUP_MESSAGE.value
        if session.is_group
        else MessageType.FRIEND_MESSAGE.value
    )
    return (
        f"{session.platform_id}:{message_type}:"
        f"{session.platform_id}!{session.creator}!{session.session_id}"
    )


def build_thread_unified_msg_origin(creator: str, thread_id: str) -> str:
    return f"webchat:{MessageType.FRIEND_MESSAGE.value}:webchat!{creator}!{thread_id}"


def serialize_thread(thread) -> dict:
    from astrbot.core.utils.datetime_utils import to_utc_isoformat

    return {
        "thread_id": thread.thread_id,
        "parent_session_id": thread.parent_session_id,
        "parent_message_id": thread.parent_message_id,
        "base_checkpoint_id": thread.base_checkpoint_id,
        "selected_text": thread.selected_text,
        "created_at": to_utc_isoformat(thread.created_at),
        "updated_at": to_utc_isoformat(thread.updated_at),
    }


def serialize_history_entry(history) -> dict:
    """Serialize a PlatformMessageHistory record with UTC-aware timestamps.

    Args:
        history: A PlatformMessageHistory instance. Must not be None.

    Returns:
        Dict with all model fields plus created_at/updated_at serialized as
        UTC-aware ISO strings (e.g. ``2026-07-06T04:00:00+00:00``).
    """
    return {
        **history.model_dump(),
        "created_at": to_utc_isoformat(history.created_at),
        "updated_at": to_utc_isoformat(history.updated_at),
    }


def find_checkpoint_index(history: list[dict], checkpoint_id: str) -> int | None:
    for index, message in enumerate(history):
        if get_checkpoint_id(message) == checkpoint_id:
            return index
    return None


def find_turn_range(history: list[dict], checkpoint_id: str) -> tuple[int, int] | None:
    checkpoint_index = find_checkpoint_index(history, checkpoint_id)
    if checkpoint_index is None:
        return None

    start = 0
    for index in range(checkpoint_index - 1, -1, -1):
        if is_checkpoint_message(history[index]):
            start = index + 1
            break
    return start, checkpoint_index


def is_latest_checkpoint(history: list[dict], checkpoint_id: str) -> bool:
    for message in reversed(history):
        current_checkpoint_id = get_checkpoint_id(message)
        if current_checkpoint_id:
            return current_checkpoint_id == checkpoint_id
    return False


def replace_user_conversation_content(original_content, edited_text: str):
    if isinstance(original_content, str):
        return edited_text
    if not isinstance(original_content, list):
        return edited_text

    result: list[dict] = []
    inserted_text = False
    for part in original_content:
        if not isinstance(part, dict):
            result.append(part)
            continue
        if part.get("type") != "text":
            result.append(part)
            continue
        text = part.get("text")
        if isinstance(text, str) and text.startswith("<system_reminder>"):
            result.append(part)
            continue
        if not inserted_text and edited_text:
            result.append({"type": "text", "text": edited_text})
            inserted_text = True

    if not inserted_text and edited_text:
        result.insert(0, {"type": "text", "text": edited_text})
    return result


def replace_assistant_conversation_content(
    original_content,
    edited_text: str,
    reasoning: str,
):
    if isinstance(original_content, str):
        return edited_text
    if not isinstance(original_content, list):
        return [{"type": "text", "text": edited_text}] if edited_text else []

    result: list[dict] = []
    inserted_text = False
    inserted_think = False
    for part in original_content:
        if not isinstance(part, dict):
            result.append(part)
            continue
        if part.get("type") == "text":
            if not inserted_text and edited_text:
                result.append({"type": "text", "text": edited_text})
                inserted_text = True
            continue
        if part.get("type") == "think":
            if not inserted_think and reasoning:
                result.append({"type": "think", "think": reasoning})
                inserted_think = True
            continue
        result.append(part)

    if reasoning and not inserted_think:
        result.insert(0, {"type": "think", "think": reasoning})
    if edited_text and not inserted_text:
        result.append({"type": "text", "text": edited_text})
    return result


def find_turn_user_index(history: list[dict], start: int, end: int) -> int | None:
    for index in range(start, end):
        message = history[index]
        if isinstance(message, dict) and message.get("role") == "user":
            return index
    return None


def find_turn_final_assistant_index(
    history: list[dict], start: int, end: int
) -> int | None:
    for index in range(end - 1, start - 1, -1):
        message = history[index]
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        if message.get("tool_calls") and not message.get("content"):
            continue
        return index
    return None


def extract_attachment_ids(history_list) -> list[str]:
    attachment_ids = []
    for history in history_list:
        content = history.content
        if not content or "message" not in content:
            continue
        message_parts = content.get("message", [])
        for part in message_parts:
            if isinstance(part, dict) and "attachment_id" in part:
                attachment_ids.append(part["attachment_id"])
    return attachment_ids


class ChatServiceError(Exception):
    pass


@dataclass(slots=True)
class ChatRunState:
    """State owned by a WebChat generation independently of its subscribers."""

    run_id: str
    username: str
    session_id: str
    llm_checkpoint_id: str
    platform_history_id: str
    back_queue: asyncio.Queue
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    message_parts: list[dict] = field(default_factory=list)
    agent_stats: dict = field(default_factory=dict)
    refs: dict = field(default_factory=dict)
    revision: int = 0
    status: str = "running"
    task: asyncio.Task[None] | None = None


class ChatService:
    def __init__(
        self,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        self.db = db
        self.core_lifecycle = core_lifecycle
        self.attachments_dir = os.path.join(get_astrbot_data_path(), "attachments")
        self.webchat_img_dir = os.path.join(get_astrbot_data_path(), "webchat", "imgs")
        os.makedirs(self.attachments_dir, exist_ok=True)

        self.supported_imgs = ["jpg", "jpeg", "png", "gif", "webp"]
        self.conv_mgr = core_lifecycle.conversation_manager
        self.platform_history_mgr = core_lifecycle.platform_message_history_manager
        self.umop_config_router = core_lifecycle.umop_config_router
        self.running_convs: dict[str, bool] = {}
        self.chat_runs: dict[str, ChatRunState] = {}
        self.chat_runs_by_session: dict[str, set[str]] = {}

    async def build_user_message_parts(self, message: str | list) -> list[dict]:
        return await build_webchat_message_parts(
            message,
            get_attachment_by_id=self.db.get_attachment_by_id,
            strict=False,
        )

    async def create_attachment_from_file(
        self, filename: str, attach_type: str, display_name: str | None = None
    ) -> dict | None:
        return await create_attachment_part_from_existing_file(
            filename,
            attach_type=attach_type,
            insert_attachment=self.db.insert_attachment,
            attachments_dir=self.attachments_dir,
            fallback_dirs=[self.webchat_img_dir],
            display_name=display_name,
        )

    async def resolve_webchat_file(
        self, filename: str | None
    ) -> tuple[str, str | None]:
        if not filename:
            raise ChatServiceError("Missing key: filename")

        safe_name = os.path.basename(filename)
        attachments_dir = Path(self.attachments_dir).resolve(strict=False)
        file_path = (attachments_dir / safe_name).resolve(strict=False)
        file_root = attachments_dir

        if not file_path.exists():
            webchat_img_dir = Path(self.webchat_img_dir).resolve(strict=False)
            webchat_file_path = (webchat_img_dir / safe_name).resolve(strict=False)
            if webchat_file_path.exists():
                file_path = webchat_file_path
                file_root = webchat_img_dir

        if not file_path.is_relative_to(file_root):
            raise ChatServiceError("Invalid file path")
        if not file_path.exists():
            raise ChatServiceError("File access error")

        filename_ext = file_path.suffix.lower()
        if filename_ext == ".wav":
            return str(file_path), "audio/wav"
        if filename_ext[1:] in self.supported_imgs:
            return str(file_path), "image/jpeg"
        return str(file_path), None

    async def resolve_webchat_file_from_dashboard_query(
        self,
        filename: str | None,
    ) -> tuple[str, str | None]:
        return await self.resolve_webchat_file(filename)

    async def resolve_attachment_file(
        self,
        attachment_id: str | None,
    ) -> tuple[str, str | None]:
        if not attachment_id:
            raise ChatServiceError("Missing key: attachment_id")

        attachment = await self.db.get_attachment_by_id(attachment_id)
        if not attachment:
            raise ChatServiceError("Attachment not found")

        file_path = Path(attachment.path).resolve(strict=False)
        if not file_path.exists():
            raise ChatServiceError("File access error")
        return str(file_path), attachment.mime_type

    async def resolve_attachment_file_from_dashboard_query(
        self,
        attachment_id: str | None,
    ) -> tuple[str, str | None]:
        return await self.resolve_attachment_file(attachment_id)

    async def save_uploaded_file(self, file) -> dict:
        filename = sanitize_upload_filename(file.filename)
        content_type = file.content_type or "application/octet-stream"

        if content_type.startswith("image"):
            attach_type = "image"
        elif content_type.startswith("audio"):
            attach_type = "record"
        elif content_type.startswith("video"):
            attach_type = "video"
        else:
            attach_type = "file"

        attachments_dir = Path(self.attachments_dir).resolve(strict=False)
        file_path = (attachments_dir / filename).resolve(strict=False)
        if not file_path.is_relative_to(attachments_dir):
            raise ChatServiceError("Invalid filename")

        await file.save(str(file_path))
        if attach_type == "image":
            detected_mime_type = await detect_image_mime_type_async(
                file_path,
                default_mime_type=None,
            )
            if detected_mime_type:
                content_type = detected_mime_type
                detected_suffix = MEDIA_MIME_EXTENSIONS.get(detected_mime_type)
                if detected_suffix and file_path.suffix.lower() != detected_suffix:
                    target_path = file_path.with_suffix(detected_suffix)
                    if target_path.exists():
                        target_path = (
                            attachments_dir / f"{uuid.uuid4().hex}{detected_suffix}"
                        )
                    await asyncio.to_thread(file_path.rename, target_path)
                    file_path = target_path
        attachment = await self.db.insert_attachment(
            path=str(file_path),
            type=attach_type,
            mime_type=content_type,
        )

        if not attachment:
            raise ChatServiceError("Failed to create attachment")

        return {
            "attachment_id": attachment.attachment_id,
            "filename": os.path.basename(attachment.path),
            "type": attach_type,
        }

    async def save_uploaded_file_from_dashboard_files(self, files) -> dict:
        if "file" not in files:
            raise ChatServiceError("Missing key: file")
        return await self.save_uploaded_file(files["file"])

    async def delete_threads_by_ids(self, thread_ids: list[str], creator: str) -> None:
        for thread_id in thread_ids:
            unified_msg_origin = build_thread_unified_msg_origin(creator, thread_id)
            active_event_registry.request_agent_stop_all(unified_msg_origin)
            tasks = []
            for run_id in list(self.chat_runs_by_session.get(thread_id, set())):
                run = self.chat_runs.get(run_id)
                if run and run.task and not run.task.done():
                    run.task.cancel()
                    tasks.append(run.task)
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await self.conv_mgr.delete_conversations_by_user_id(unified_msg_origin)
            await self.platform_history_mgr.delete(
                platform_id="webchat_thread",
                user_id=thread_id,
                offset_sec=99999999,
            )
            webchat_queue_mgr.remove_queues(thread_id)
            self.running_convs.pop(thread_id, None)

    async def load_current_conversation_history(self, session) -> tuple[str, list]:
        unified_msg_origin = build_webchat_unified_msg_origin(session)
        conversation_id = await self.conv_mgr.get_curr_conversation_id(
            unified_msg_origin
        )
        if not conversation_id:
            return "", []

        conversation = await self.conv_mgr.get_conversation(
            unified_msg_origin=unified_msg_origin,
            conversation_id=conversation_id,
        )
        if not conversation:
            return "", []

        try:
            history = json.loads(conversation.history or "[]")
        except json.JSONDecodeError:
            return "", []
        return conversation_id, history if isinstance(history, list) else []

    async def get_sorted_platform_history(self, session) -> list:
        history_list = await self.platform_history_mgr.get(
            platform_id=session.platform_id,
            user_id=session.session_id,
            page=1,
            page_size=100000,
        )
        history_list.sort(key=lambda item: (item.created_at, item.id))
        return history_list

    async def delete_platform_history_after(
        self, session, message_id: int
    ) -> list[int]:
        history_list = await self.get_sorted_platform_history(session)
        should_delete = False
        deleted_ids: list[int] = []
        for item in history_list:
            if should_delete:
                if item.id is not None:
                    deleted_ids.append(item.id)
                    await self.platform_history_mgr.delete_by_id(item.id)
                continue
            if item.id == message_id:
                should_delete = True
        return deleted_ids

    async def save_bot_message(
        self,
        webchat_conv_id: str,
        message_parts: list[dict],
        agent_stats: dict,
        refs: dict,
        llm_checkpoint_id: str | None = None,
        platform_history_id: str = "webchat",
    ):
        return await self.platform_history_mgr.insert(
            platform_id=platform_history_id,
            user_id=webchat_conv_id,
            content=build_bot_history_content(
                message_parts,
                agent_stats=agent_stats,
                refs=refs,
            ),
            sender_id="bot",
            sender_name="bot",
            llm_checkpoint_id=llm_checkpoint_id,
        )

    def get_active_chat_runs(self, username: str, session_id: str) -> list[dict]:
        """Return resumable runs owned by a user in one chat session.

        Args:
            username: Authenticated run owner.
            session_id: WebChat session or thread identifier.

        Returns:
            Active run snapshots in creation order.
        """
        snapshots = []
        for run in self.chat_runs.values():
            if run.username != username or run.session_id != session_id:
                continue
            snapshots.append(
                {
                    "run_id": run.run_id,
                    "session_id": run.session_id,
                    "llm_checkpoint_id": run.llm_checkpoint_id,
                    "status": run.status,
                    "revision": run.revision,
                    "content": build_bot_history_content(
                        deepcopy(run.message_parts),
                        agent_stats=deepcopy(run.agent_stats),
                        refs=deepcopy(run.refs),
                    ),
                }
            )
        return snapshots

    @staticmethod
    def _publish_chat_run(run: ChatRunState, payload: dict) -> None:
        """Publish one output event without coupling the run to subscribers.

        Args:
            run: Chat run producing the event.
            payload: Existing WebChat event payload.
        """
        run.revision += 1
        item = (run.revision, payload)
        for subscriber in list(run.subscribers):
            try:
                subscriber.put_nowait(item)
            except asyncio.QueueFull:
                # End slow streams so they can reconnect from a fresh snapshot.
                run.subscribers.discard(subscriber)
                while not subscriber.empty():
                    subscriber.get_nowait()
                subscriber.put_nowait(None)

    def _subscribe_chat_run(
        self,
        run: ChatRunState,
        *,
        include_snapshot: bool,
        saved_user_record=None,
    ) -> AsyncIterator[str]:
        """Create an SSE subscriber for a running chat generation.

        Args:
            run: Chat run to observe.
            include_snapshot: Whether to begin with accumulated run state.
            saved_user_record: Newly persisted user record for the legacy stream.

        Returns:
            SSE iterator detached from the generation task lifecycle.
        """
        subscriber: asyncio.Queue = asyncio.Queue(
            maxsize=CHAT_RUN_SUBSCRIBER_QUEUE_SIZE
        )
        run.subscribers.add(subscriber)
        snapshot = None
        if include_snapshot:
            snapshot = {
                "run_id": run.run_id,
                "session_id": run.session_id,
                "llm_checkpoint_id": run.llm_checkpoint_id,
                "status": run.status,
                "revision": run.revision,
                "content": build_bot_history_content(
                    deepcopy(run.message_parts),
                    agent_stats=deepcopy(run.agent_stats),
                    refs=deepcopy(run.refs),
                ),
            }
        snapshot_revision = run.revision

        async def stream():
            try:
                if snapshot is not None:
                    payload = {"type": "run_snapshot", "data": snapshot}
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                else:
                    session_info = {
                        "type": "session_id",
                        "data": None,
                        "session_id": run.session_id,
                    }
                    yield f"data: {json.dumps(session_info, ensure_ascii=False)}\n\n"
                    if saved_user_record:
                        user_saved_info = {
                            "type": "user_message_saved",
                            "data": {
                                "id": saved_user_record.id,
                                "created_at": to_utc_isoformat(
                                    saved_user_record.created_at
                                ),
                                "llm_checkpoint_id": run.llm_checkpoint_id,
                            },
                        }
                        yield f"data: {json.dumps(user_saved_info, ensure_ascii=False)}\n\n"

                while True:
                    try:
                        item = await asyncio.wait_for(subscriber.get(), timeout=1)
                    except asyncio.TimeoutError:
                        yield SSE_HEARTBEAT
                        continue
                    if item is None:
                        break
                    revision, payload = item
                    if include_snapshot and revision <= snapshot_revision:
                        continue
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            finally:
                run.subscribers.discard(subscriber)

        return stream()

    async def build_chat_run_stream(
        self,
        username: str,
        run_id: str,
    ) -> AsyncIterator[str]:
        """Attach a new SSE subscriber to an active chat run.

        Args:
            username: Authenticated run owner.
            run_id: Active run identifier.

        Returns:
            SSE iterator beginning with a full accumulated snapshot.

        Raises:
            ChatServiceError: If the run is absent or owned by another user.
        """
        run = self.chat_runs.get(run_id)
        if run is None:
            raise ChatServiceError(f"Chat run {run_id} not found")
        if run.username != username:
            raise ChatServiceError("Permission denied")
        return self._subscribe_chat_run(run, include_snapshot=True)

    async def _consume_chat_run(self, run: ChatRunState) -> None:
        """Drain runner output, persist it, and fan it out to subscribers.

        Args:
            run: Chat run owning the producer queue and durable state.
        """
        pending_accumulator = BotMessageAccumulator()
        display_accumulator = BotMessageAccumulator()
        pending_agent_stats = {}
        pending_refs = {}

        async def flush_pending_bot_message():
            nonlocal pending_accumulator, pending_agent_stats, pending_refs
            if not (
                pending_accumulator.has_content() or pending_refs or pending_agent_stats
            ):
                return None

            message_parts_to_save = pending_accumulator.build_message_parts(
                include_pending_tool_calls=True
            )
            plain_text = collect_plain_text_from_message_parts(message_parts_to_save)
            try:
                extracted_refs = extract_web_search_refs(
                    plain_text,
                    message_parts_to_save,
                )
            except Exception as exc:
                logger.exception(
                    f"Failed to extract web search refs: {exc}",
                    exc_info=True,
                )
                extracted_refs = pending_refs

            run.refs = extracted_refs
            saved_record = await self.save_bot_message(
                run.session_id,
                message_parts_to_save,
                pending_agent_stats,
                extracted_refs,
                run.llm_checkpoint_id,
                run.platform_history_id,
            )
            pending_accumulator = BotMessageAccumulator()
            pending_agent_stats = {}
            pending_refs = {}
            return saved_record

        self.running_convs[run.session_id] = True
        try:
            while True:
                result = await run.back_queue.get()
                if not result:
                    continue
                if result.get("message_id") and str(result["message_id"]) != run.run_id:
                    logger.warning("webchat stream message_id mismatch")
                    continue

                result_text = result.get("data", "")
                msg_type = result.get("type")
                streaming = result.get("streaming", False)
                chain_type = result.get("chain_type")

                if chain_type == "agent_stats":
                    try:
                        run.agent_stats = json.loads(result_text)
                    except (TypeError, json.JSONDecodeError):
                        run.agent_stats = {}
                    pending_agent_stats = run.agent_stats
                    self._publish_chat_run(
                        run,
                        {"type": "agent_stats", "data": run.agent_stats},
                    )
                    continue

                attachment_saved_payload = None
                if msg_type == "plain":
                    for accumulator in (pending_accumulator, display_accumulator):
                        accumulator.add_plain(
                            result_text,
                            chain_type=chain_type,
                            streaming=streaming,
                        )
                elif msg_type in {"image", "record", "file", "video"}:
                    prefix = {
                        "image": "[IMAGE]",
                        "record": "[RECORD]",
                        "file": "[FILE]",
                        "video": "[VIDEO]",
                    }[msg_type]
                    filename = str(result_text).replace(prefix, "", 1)
                    display_name = None
                    if msg_type in {"file", "video"} and "|" in filename:
                        filename, display_name = filename.split("|", 1)
                    part = await self.create_attachment_from_file(
                        filename,
                        msg_type,
                        display_name=display_name,
                    )
                    for accumulator in (pending_accumulator, display_accumulator):
                        accumulator.add_attachment(part)
                    if part and part.get("attachment_id") and part.get("type"):
                        attachment_saved_payload = {
                            "type": "attachment_saved",
                            "data": {
                                "id": part["attachment_id"],
                                "type": part["type"],
                            },
                        }

                snapshot_accumulator = deepcopy(display_accumulator)
                run.message_parts = snapshot_accumulator.build_message_parts(
                    include_pending_tool_calls=True
                )
                self._publish_chat_run(run, result)
                if attachment_saved_payload:
                    self._publish_chat_run(run, attachment_saved_payload)

                should_save = False
                if msg_type == "end":
                    should_save = bool(
                        pending_accumulator.has_content()
                        or pending_refs
                        or pending_agent_stats
                    )
                elif (streaming and msg_type == "complete") or not streaming:
                    if chain_type not in ("tool_call", "tool_call_result"):
                        should_save = True

                if should_save:
                    saved_record = await flush_pending_bot_message()
                    if saved_record:
                        self._publish_chat_run(
                            run,
                            {
                                "type": "message_saved",
                                "data": {
                                    "id": saved_record.id,
                                    "created_at": to_utc_isoformat(
                                        saved_record.created_at
                                    ),
                                    "llm_checkpoint_id": run.llm_checkpoint_id,
                                },
                            },
                        )
                if msg_type == "end":
                    run.status = "completed"
                    break
        except asyncio.CancelledError:
            run.status = "stopped"
        except Exception as exc:
            run.status = "failed"
            logger.exception(f"WebChat run unexpected error: {exc}", exc_info=True)
            self._publish_chat_run(
                run,
                {"type": "error", "data": "WebChat run failed"},
            )
        finally:
            try:
                saved_record = await asyncio.shield(flush_pending_bot_message())
                if saved_record:
                    self._publish_chat_run(
                        run,
                        {
                            "type": "message_saved",
                            "data": {
                                "id": saved_record.id,
                                "created_at": to_utc_isoformat(saved_record.created_at),
                                "llm_checkpoint_id": run.llm_checkpoint_id,
                            },
                        },
                    )
            except Exception as exc:
                logger.exception(
                    f"Failed to persist pending webchat message: {exc}",
                    exc_info=True,
                )

            webchat_queue_mgr.remove_back_queue(run.run_id)
            if self.chat_runs.get(run.run_id) is run:
                self.chat_runs.pop(run.run_id, None)
            run_ids = self.chat_runs_by_session.get(run.session_id)
            if run_ids is not None:
                run_ids.discard(run.run_id)
                if not run_ids:
                    self.chat_runs_by_session.pop(run.session_id, None)
                    self.running_convs.pop(run.session_id, None)
            for subscriber in list(run.subscribers):
                while not subscriber.empty():
                    subscriber.get_nowait()
                subscriber.put_nowait(None)
            run.subscribers.clear()

    async def build_chat_stream(
        self,
        username: str,
        post_data: dict,
    ) -> AsyncIterator[str]:
        if "message" not in post_data and "files" not in post_data:
            raise ChatServiceError("Missing key: message or files")
        if "session_id" not in post_data and "conversation_id" not in post_data:
            raise ChatServiceError("Missing key: session_id or conversation_id")

        message = post_data.get("message", post_data.get("files", []))
        session_id = post_data.get("session_id", post_data.get("conversation_id"))
        selected_provider = post_data.get("selected_provider")
        selected_model = post_data.get("selected_model")
        enable_streaming = post_data.get("enable_streaming", True)
        platform_history_id = post_data.get("_platform_history_id") or "webchat"
        thread_selected_text = post_data.get("_thread_selected_text")

        if not session_id:
            raise ChatServiceError("session_id is empty")

        webchat_conv_id = session_id
        message_parts = await self.build_user_message_parts(message)
        if not webchat_message_parts_have_content(message_parts):
            raise ChatServiceError(
                "Message content is empty (reply only is not allowed)"
            )

        message_id = str(uuid.uuid4())
        llm_checkpoint_id = post_data.get("_llm_checkpoint_id") or str(uuid.uuid4())
        skip_user_history = bool(post_data.get("_skip_user_history"))
        saved_user_record = None

        message_parts_for_storage = strip_message_parts_path_fields(message_parts)
        if not skip_user_history:
            saved_user_record = await self.platform_history_mgr.insert(
                platform_id=platform_history_id,
                user_id=webchat_conv_id,
                content={"type": "user", "message": message_parts_for_storage},
                sender_id=username,
                sender_name=username,
                llm_checkpoint_id=llm_checkpoint_id,
            )

        back_queue = webchat_queue_mgr.get_or_create_back_queue(
            message_id,
            webchat_conv_id,
        )
        run = ChatRunState(
            run_id=message_id,
            username=username,
            session_id=webchat_conv_id,
            llm_checkpoint_id=llm_checkpoint_id,
            platform_history_id=platform_history_id,
            back_queue=back_queue,
        )
        self.chat_runs[message_id] = run
        self.chat_runs_by_session.setdefault(webchat_conv_id, set()).add(message_id)
        stream = self._subscribe_chat_run(
            run,
            include_snapshot=False,
            saved_user_record=saved_user_record,
        )
        run.task = asyncio.create_task(
            self._consume_chat_run(run),
            name=f"webchat_run_{message_id}",
        )

        try:
            chat_queue = webchat_queue_mgr.get_or_create_queue(webchat_conv_id)
            await chat_queue.put(
                (
                    username,
                    webchat_conv_id,
                    {
                        "message": message_parts,
                        "selected_provider": selected_provider,
                        "selected_model": selected_model,
                        "enable_streaming": enable_streaming,
                        "message_id": message_id,
                        "llm_checkpoint_id": llm_checkpoint_id,
                        "thread_selected_text": thread_selected_text,
                    },
                ),
            )
        except BaseException:
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
            raise

        return stream

    async def stop_session(self, username: str, session_id: str) -> dict:
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            raise ChatServiceError(f"Session {session_id} not found")
        if session.creator != username:
            raise ChatServiceError("Permission denied")

        unified_msg_origin = build_webchat_unified_msg_origin(session)
        stopped_count = active_event_registry.request_agent_stop_all(unified_msg_origin)
        return {"stopped_count": stopped_count}

    async def stop_session_from_dashboard_payload(
        self,
        username: str,
        payload: object,
    ) -> dict:
        data = self._dashboard_payload(payload)
        session_id = data.get("session_id")
        if not session_id:
            raise ChatServiceError("Missing key: session_id")
        return await self.stop_session(username, session_id)

    async def delete_session_internal(self, session, username: str) -> None:
        session_id = session.session_id
        message_type = "GroupMessage" if session.is_group else "FriendMessage"
        unified_msg_origin = (
            f"{session.platform_id}:{message_type}:"
            f"{session.platform_id}!{username}!{session_id}"
        )
        active_event_registry.request_agent_stop_all(unified_msg_origin)
        tasks = []
        for run_id in list(self.chat_runs_by_session.get(session_id, set())):
            run = self.chat_runs.get(run_id)
            if run and run.task and not run.task.done():
                run.task.cancel()
                tasks.append(run.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.conv_mgr.delete_conversations_by_user_id(unified_msg_origin)

        history_list = await self.platform_history_mgr.get(
            platform_id=session.platform_id,
            user_id=session_id,
            page=1,
            page_size=100000,
        )
        attachment_ids = extract_attachment_ids(history_list)
        if attachment_ids:
            await self.delete_attachments(attachment_ids)

        await self.platform_history_mgr.delete(
            platform_id=session.platform_id,
            user_id=session_id,
            offset_sec=99999999,
        )
        thread_ids = await self.db.delete_webchat_threads_by_parent_session(session_id)
        await self.delete_threads_by_ids(thread_ids, username)

        try:
            await self.umop_config_router.delete_route(unified_msg_origin)
        except ValueError as exc:
            logger.warning(
                "Failed to delete UMO route %s during session cleanup: %s",
                unified_msg_origin,
                exc,
            )

        if session.platform_id == "webchat":
            webchat_queue_mgr.remove_queues(session_id)

        await self.db.delete_platform_session(session_id)

    async def delete_webchat_session(self, username: str, session_id: str) -> None:
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            raise ChatServiceError(f"Session {session_id} not found")
        if session.creator != username:
            raise ChatServiceError("Permission denied")
        await self.delete_session_internal(session, username)

    async def delete_webchat_session_from_dashboard_query(
        self,
        username: str,
        session_id: str | None,
    ) -> None:
        if not session_id:
            raise ChatServiceError("Missing key: session_id")
        await self.delete_webchat_session(username, session_id)

    async def batch_delete_sessions(
        self,
        username: str,
        session_ids: list,
        delete_session=None,
    ) -> dict:
        delete_session = delete_session or self.delete_session_internal
        sessions = await self.db.get_platform_sessions_by_ids(session_ids)
        sessions_by_id = {session.session_id: session for session in sessions}
        deleted_count = 0
        failed_items = []

        for session_id in session_ids:
            session = sessions_by_id.get(session_id)
            if not session:
                failed_items.append({"session_id": session_id, "reason": "not found"})
                continue
            if session.creator != username:
                failed_items.append(
                    {"session_id": session_id, "reason": "permission denied"}
                )
                continue

            try:
                await delete_session(session, username)
                deleted_count += 1
                sessions_by_id.pop(session_id, None)
            except Exception:
                logger.warning("Failed to delete session %s", session_id)
                failed_items.append(
                    {"session_id": session_id, "reason": "internal_error"}
                )

        return {
            "deleted_count": deleted_count,
            "failed_count": len(failed_items),
            "failed_items": failed_items,
        }

    async def batch_delete_sessions_from_dashboard_payload(
        self,
        username: str,
        payload: object,
        delete_session=None,
    ) -> dict:
        data = self._dashboard_payload(payload)
        session_ids = data.get("session_ids")
        if not session_ids or not isinstance(session_ids, list):
            raise ChatServiceError("Missing or invalid key: session_ids")
        return await self.batch_delete_sessions(username, session_ids, delete_session)

    async def delete_attachments(self, attachment_ids: list[str]) -> None:
        try:
            attachments = await self.db.get_attachments(attachment_ids)
            for attachment in attachments:
                if not os.path.exists(attachment.path):
                    continue
                try:
                    os.remove(attachment.path)
                except OSError as e:
                    logger.warning(
                        f"Failed to delete attachment file {attachment.path}: {e}"
                    )
        except Exception as e:
            logger.warning(f"Failed to get attachments: {e}")

        try:
            await self.db.delete_attachments(attachment_ids)
        except Exception as e:
            logger.warning(f"Failed to delete attachments: {e}")

    async def new_session(self, username: str, platform_id: str) -> dict:
        session = await self.db.create_platform_session(
            creator=username,
            platform_id=platform_id,
            is_group=0,
        )
        return {
            "session_id": session.session_id,
            "platform_id": session.platform_id,
        }

    async def new_session_from_dashboard_query(
        self,
        username: str,
        platform_id: str | None,
    ) -> dict:
        return await self.new_session(username, platform_id or "webchat")

    async def get_sessions(self, username: str, platform_id: str | None) -> list[dict]:
        sessions, _ = await self.db.get_platform_sessions_by_creator_paginated(
            creator=username,
            platform_id=platform_id,
            page=1,
            page_size=100,
            exclude_project_sessions=True,
        )

        sessions_data = []
        for item in sessions:
            session = item["session"]
            sessions_data.append(
                {
                    "session_id": session.session_id,
                    "platform_id": session.platform_id,
                    "creator": session.creator,
                    "display_name": session.display_name,
                    "is_group": session.is_group,
                    "created_at": to_utc_isoformat(session.created_at),
                    "updated_at": to_utc_isoformat(session.updated_at),
                }
            )
        return sessions_data

    async def get_sessions_from_dashboard_query(
        self,
        username: str,
        platform_id: str | None,
    ) -> list[dict]:
        return await self.get_sessions(username, platform_id)

    async def get_session(self, username: str, session_id: str) -> dict:
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            raise ChatServiceError(f"Session {session_id} not found")
        if session.creator != username:
            raise ChatServiceError("Permission denied")
        platform_id = session.platform_id

        project_info = await self.db.get_project_by_session(
            session_id=session_id, creator=username
        )
        history_ls = await self.platform_history_mgr.get(
            platform_id=platform_id,
            user_id=session_id,
            page=1,
            page_size=1000,
        )
        threads = await self.db.get_webchat_threads_by_parent_session(
            parent_session_id=session_id,
            creator=username,
        )

        response_data = {
            "history": [serialize_history_entry(history) for history in history_ls],
            "threads": [serialize_thread(thread) for thread in threads],
            "is_running": self.running_convs.get(session_id, False),
            "active_runs": self.get_active_chat_runs(username, session_id),
        }
        if project_info:
            response_data["project"] = {
                "project_id": project_info.project_id,
                "title": project_info.title,
                "emoji": project_info.emoji,
            }
        return response_data

    async def get_session_from_dashboard_query(
        self,
        username: str,
        session_id: str | None,
    ) -> dict:
        if not session_id:
            raise ChatServiceError("Missing key: session_id")
        return await self.get_session(username, session_id)

    async def create_thread(self, username: str, data: dict) -> dict:
        session_id = data.get("session_id")
        parent_message_id = data.get("parent_message_id")
        selected_text = str(data.get("selected_text") or "").strip()
        if not session_id:
            raise ChatServiceError("Missing key: session_id")
        if parent_message_id is None:
            raise ChatServiceError("Missing key: parent_message_id")
        if not selected_text:
            raise ChatServiceError("Missing key: selected_text")

        try:
            parent_message_id = int(parent_message_id)
        except (TypeError, ValueError) as exc:
            raise ChatServiceError("Invalid key: parent_message_id") from exc

        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            raise ChatServiceError(f"Session {session_id} not found")
        if session.creator != username:
            raise ChatServiceError("Permission denied")

        parent_record = await self.db.get_platform_message_history_by_id(
            parent_message_id
        )
        if (
            not parent_record
            or parent_record.platform_id != session.platform_id
            or parent_record.user_id != session_id
        ):
            raise ChatServiceError("Parent message not found")
        if not isinstance(parent_record.content, dict):
            raise ChatServiceError("Invalid parent message content")
        if parent_record.content.get("type") != "bot":
            raise ChatServiceError("Only bot messages can create threads")

        checkpoint_id = parent_record.llm_checkpoint_id
        if not checkpoint_id:
            raise ChatServiceError("Parent message is not linked to LLM history")

        existing = await self.db.get_webchat_thread_by_parent_message_and_text(
            parent_session_id=session_id,
            parent_message_id=parent_message_id,
            selected_text=selected_text,
            creator=username,
        )
        if existing:
            return serialize_thread(existing)

        conversation_id, history = await self.load_current_conversation_history(session)
        turn_range = find_turn_range(history, checkpoint_id)
        if not conversation_id or not turn_range:
            raise ChatServiceError("Linked checkpoint not found")

        _start, end = turn_range
        base_history = history[: end + 1]
        thread = await self.db.create_webchat_thread(
            creator=username,
            parent_session_id=session_id,
            parent_message_id=parent_message_id,
            base_checkpoint_id=checkpoint_id,
            selected_text=selected_text,
        )
        await self.conv_mgr.new_conversation(
            unified_msg_origin=build_thread_unified_msg_origin(
                username,
                thread.thread_id,
            ),
            platform_id="webchat",
            content=base_history,
        )
        return serialize_thread(thread)

    async def create_thread_from_dashboard_payload(
        self,
        username: str,
        payload: object,
    ) -> dict:
        return await self.create_thread(username, self._dashboard_payload(payload))

    async def get_thread(self, username: str, thread_id: str) -> dict:
        thread = await self.db.get_webchat_thread_by_id(thread_id)
        if not thread:
            raise ChatServiceError(f"Thread {thread_id} not found")
        if thread.creator != username:
            raise ChatServiceError("Permission denied")

        history_ls = await self.platform_history_mgr.get(
            platform_id="webchat_thread",
            user_id=thread_id,
            page=1,
            page_size=1000,
        )
        return {
            "thread": serialize_thread(thread),
            "history": [serialize_history_entry(history) for history in history_ls],
            "is_running": self.running_convs.get(thread_id, False),
            "active_runs": self.get_active_chat_runs(username, thread_id),
        }

    async def get_thread_from_dashboard_query(
        self,
        username: str,
        thread_id: str | None,
    ) -> dict:
        if not thread_id:
            raise ChatServiceError("Missing key: thread_id")
        return await self.get_thread(username, thread_id)

    async def prepare_thread_chat_payload(self, username: str, data: dict) -> dict:
        thread_id = data.get("thread_id")
        if not thread_id:
            raise ChatServiceError("Missing key: thread_id")

        thread = await self.db.get_webchat_thread_by_id(thread_id)
        if not thread:
            raise ChatServiceError(f"Thread {thread_id} not found")
        if thread.creator != username:
            raise ChatServiceError("Permission denied")

        return {
            "session_id": thread.thread_id,
            "message": data.get("message", []),
            "enable_streaming": data.get("enable_streaming", True),
            "selected_provider": data.get("selected_provider"),
            "selected_model": data.get("selected_model"),
            "_platform_history_id": "webchat_thread",
            "_thread_selected_text": thread.selected_text,
        }

    async def prepare_thread_chat_payload_from_dashboard_payload(
        self,
        username: str,
        payload: object,
    ) -> dict:
        return await self.prepare_thread_chat_payload(
            username,
            self._dashboard_payload(payload),
        )

    async def delete_thread(self, username: str, thread_id: str) -> dict:
        thread = await self.db.get_webchat_thread_by_id(thread_id)
        if not thread:
            raise ChatServiceError(f"Thread {thread_id} not found")
        if thread.creator != username:
            raise ChatServiceError("Permission denied")

        await self.db.delete_webchat_thread(thread_id)
        await self.delete_threads_by_ids([thread_id], username)
        return {"thread_id": thread_id}

    async def delete_thread_from_dashboard_payload(
        self,
        username: str,
        payload: object,
    ) -> dict:
        data = self._dashboard_payload(payload)
        thread_id = data.get("thread_id")
        if not thread_id:
            raise ChatServiceError("Missing key: thread_id")
        return await self.delete_thread(username, thread_id)

    async def update_message(self, username: str, data: dict) -> dict:
        session_id = data.get("session_id")
        message_id = data.get("message_id")
        content = data.get("content")
        if not session_id:
            raise ChatServiceError("Missing key: session_id")
        if message_id is None:
            raise ChatServiceError("Missing key: message_id")

        try:
            message_id = int(message_id)
            if not isinstance(content, dict):
                raise ValueError("Missing key: content")
            content = sanitize_message_content(content)
        except (TypeError, ValueError) as exc:
            raise ChatServiceError(str(exc)) from exc

        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            raise ChatServiceError(f"Session {session_id} not found")
        if session.creator != username:
            raise ChatServiceError("Permission denied")

        record = await self.db.get_platform_message_history_by_id(message_id)
        if not record:
            raise ChatServiceError(f"Message {message_id} not found")
        if record.platform_id != session.platform_id or record.user_id != session_id:
            raise ChatServiceError("Message does not belong to the session")
        if not isinstance(record.content, dict):
            raise ChatServiceError("Invalid message content")
        if record.content.get("type") != content.get("type"):
            raise ChatServiceError("Message type cannot be changed")
        if content.get("type") != "user":
            raise ChatServiceError("Only user messages can be edited")

        platform_history = await self.get_sorted_platform_history(session)
        latest_user_record = next(
            (
                item
                for item in reversed(platform_history)
                if isinstance(item.content, dict) and item.content.get("type") == "user"
            ),
            None,
        )
        if not latest_user_record or latest_user_record.id != message_id:
            raise ChatServiceError("Only the latest user message can be edited")

        checkpoint_id = record.llm_checkpoint_id
        if not checkpoint_id:
            raise ChatServiceError(
                "This message is not linked to LLM history and cannot be edited"
            )

        conversation_id, history = await self.load_current_conversation_history(session)
        turn_range = find_turn_range(history, checkpoint_id)
        if not conversation_id or not turn_range:
            raise ChatServiceError("Linked checkpoint not found")
        if not is_latest_checkpoint(history, checkpoint_id):
            raise ChatServiceError("Only the latest turn can be edited")

        start, end = turn_range
        target_index = find_turn_user_index(history, start, end)
        if target_index is None:
            raise ChatServiceError("Linked user message not found")

        new_checkpoint_id = str(uuid.uuid4())
        truncated_history = history[:start]
        await self.platform_history_mgr.update(
            message_id=message_id,
            content=content,
            llm_checkpoint_id=new_checkpoint_id,
        )
        deleted_message_ids = await self.delete_platform_history_after(
            session, message_id
        )
        thread_ids = await self.db.delete_webchat_threads_by_parent_message_ids(
            session_id,
            deleted_message_ids,
        )
        await self.delete_threads_by_ids(thread_ids, username)
        await self.conv_mgr.update_conversation(
            unified_msg_origin=build_webchat_unified_msg_origin(session),
            conversation_id=conversation_id,
            history=truncated_history,
        )
        await self.db.update_platform_session(session_id=session_id)
        updated = await self.db.get_platform_message_history_by_id(message_id)
        return {
            "message": serialize_history_entry(updated) if updated else None,
            "needs_regenerate": True,
            "truncated_after_message": True,
        }

    async def update_message_from_dashboard_payload(
        self,
        username: str,
        payload: object,
    ) -> dict:
        return await self.update_message(username, self._dashboard_payload(payload))

    async def prepare_regenerate_message_payload(
        self,
        username: str,
        data: dict,
    ) -> dict:
        session_id = data.get("session_id")
        message_id = data.get("message_id")
        if not session_id:
            raise ChatServiceError("Missing key: session_id")
        if message_id is None:
            raise ChatServiceError("Missing key: message_id")

        try:
            message_id = int(message_id)
        except (TypeError, ValueError) as exc:
            raise ChatServiceError("Invalid key: message_id") from exc

        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            raise ChatServiceError(f"Session {session_id} not found")
        if session.creator != username:
            raise ChatServiceError("Permission denied")

        target_record = await self.db.get_platform_message_history_by_id(message_id)
        if not target_record:
            raise ChatServiceError(f"Message {message_id} not found")
        if (
            target_record.platform_id != session.platform_id
            or target_record.user_id != session_id
        ):
            raise ChatServiceError("Message does not belong to the session")
        if not isinstance(target_record.content, dict):
            raise ChatServiceError("Invalid message content")
        if target_record.content.get("type") != "bot":
            raise ChatServiceError("Only bot messages can be regenerated")

        checkpoint_id = target_record.llm_checkpoint_id
        if not checkpoint_id:
            raise ChatServiceError("Message is not linked to LLM history")

        conversation_id, history = await self.load_current_conversation_history(session)
        turn_range = find_turn_range(history, checkpoint_id)
        if not conversation_id or not turn_range:
            raise ChatServiceError("Linked checkpoint not found")
        if not is_latest_checkpoint(history, checkpoint_id):
            raise ChatServiceError("Regenerating older turns requires branching")

        start, end = turn_range
        user_index = find_turn_user_index(history, start, end)
        if user_index is None:
            raise ChatServiceError("Linked user message not found")

        platform_history = await self.get_sorted_platform_history(session)
        source_user_record = next(
            (
                item
                for item in reversed(platform_history)
                if item.llm_checkpoint_id == checkpoint_id
                and isinstance(item.content, dict)
                and item.content.get("type") == "user"
            ),
            None,
        )
        if not source_user_record:
            raise ChatServiceError("Linked user display message not found")

        old_bot_record_ids = [
            item.id
            for item in platform_history
            if item.id is not None
            and item.llm_checkpoint_id == checkpoint_id
            and isinstance(item.content, dict)
            and item.content.get("type") == "bot"
        ]
        if not old_bot_record_ids:
            raise ChatServiceError("Linked bot display message not found")

        new_checkpoint_id = str(uuid.uuid4())
        new_history = history[:start] + history[end + 1 :]
        await self.conv_mgr.update_conversation(
            unified_msg_origin=build_webchat_unified_msg_origin(session),
            conversation_id=conversation_id,
            history=new_history,
        )
        thread_ids = await self.db.delete_webchat_threads_by_parent_message_ids(
            session_id,
            old_bot_record_ids,
        )
        await self.delete_threads_by_ids(thread_ids, username)
        for old_bot_record_id in old_bot_record_ids:
            await self.platform_history_mgr.delete_by_id(old_bot_record_id)
        await self.platform_history_mgr.update(
            message_id=source_user_record.id,
            llm_checkpoint_id=new_checkpoint_id,
        )

        return {
            "session_id": session_id,
            "message": source_user_record.content.get("message", []),
            "enable_streaming": data.get("enable_streaming", True),
            "selected_provider": data.get("selected_provider"),
            "selected_model": data.get("selected_model"),
            "_skip_user_history": True,
            "_llm_checkpoint_id": new_checkpoint_id,
        }

    async def prepare_regenerate_message_payload_from_dashboard_payload(
        self,
        username: str,
        payload: object,
    ) -> dict:
        return await self.prepare_regenerate_message_payload(
            username,
            self._dashboard_payload(payload),
        )

    async def update_session_display_name(
        self,
        username: str,
        session_id: str,
        display_name,
    ) -> dict:
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            raise ChatServiceError(f"Session {session_id} not found")
        if session.creator != username:
            raise ChatServiceError("Permission denied")

        await self.db.update_platform_session(
            session_id=session_id,
            display_name=display_name,
        )
        return {}

    async def update_session_display_name_from_dashboard_payload(
        self,
        username: str,
        payload: object,
    ) -> dict:
        data = self._dashboard_payload(payload)
        session_id = data.get("session_id")
        display_name = data.get("display_name")
        if not session_id:
            raise ChatServiceError("Missing key: session_id")
        if display_name is None:
            raise ChatServiceError("Missing key: display_name")
        return await self.update_session_display_name(
            username, session_id, display_name
        )

    @staticmethod
    def _dashboard_payload(payload: object) -> dict:
        if payload is None:
            raise ChatServiceError("Missing JSON body")
        if not isinstance(payload, dict):
            raise ChatServiceError("Invalid JSON body: expected object")
        return payload
