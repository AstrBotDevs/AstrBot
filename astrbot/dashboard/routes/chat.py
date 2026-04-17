import asyncio
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import cast

from quart import Response as QuartResponse
from quart import g, make_response, request, send_file

from astrbot.core import logger, sp
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

from .chat_stream_events import build_message_saved_event
from .route import Response, Route, RouteContext

# SSE heartbeat message to keep the connection alive during long-running operations
SSE_HEARTBEAT = ": heartbeat\n\n"


@asynccontextmanager
async def track_conversation(convs: dict, conv_id: str):
    convs[conv_id] = True
    try:
        yield
    finally:
        convs.pop(conv_id, None)


async def _poll_webchat_stream_result(back_queue, username: str):
    try:
        result = await asyncio.wait_for(back_queue.get(), timeout=1)
    except asyncio.TimeoutError:
        # Return a sentinel so the caller can send an SSE heartbeat to
        # keep the connection alive during long-running operations (e.g.
        # context compression with reasoning models).  See #6938.
        return None, False
    except asyncio.CancelledError:
        logger.debug(f"[WebChat] 用户 {username} 断开聊天长连接。")
        return None, True
    except Exception as e:
        logger.error(f"WebChat stream error: {e}")
        return None, False
    return result, False


class ChatRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/chat/send": ("POST", self.chat),
            "/chat/new_session": ("GET", self.new_session),
            "/chat/sessions": ("GET", self.get_sessions),
            "/chat/get_session": ("GET", self.get_session),
            "/chat/stop": ("POST", self.stop_session),
            "/chat/delete_session": ("GET", self.delete_webchat_session),
            "/chat/batch_delete_sessions": ("POST", self.batch_delete_sessions),
            "/chat/update_session_display_name": (
                "POST",
                self.update_session_display_name,
            ),
            "/chat/update_message": ("POST", self.update_message),
            "/chat/branch_session": ("POST", self.branch_session),
            "/chat/regenerate_message": ("POST", self.regenerate_message),
            "/chat/get_file": ("GET", self.get_file),
            "/chat/get_attachment": ("GET", self.get_attachment),
            "/chat/post_file": ("POST", self.post_file),
        }
        self.core_lifecycle = core_lifecycle
        self.register_routes()
        self.attachments_dir = os.path.join(get_astrbot_data_path(), "attachments")
        self.legacy_img_dir = os.path.join(get_astrbot_data_path(), "webchat", "imgs")
        os.makedirs(self.attachments_dir, exist_ok=True)

        self.supported_imgs = ["jpg", "jpeg", "png", "gif", "webp"]
        self.conv_mgr = core_lifecycle.conversation_manager
        self.platform_history_mgr = core_lifecycle.platform_message_history_manager
        self.db = db
        self.umop_config_router = core_lifecycle.umop_config_router
        self.branch_meta_scope = "webchat_session"
        self.branch_meta_key = "branch_meta"

        self.running_convs: dict[str, bool] = {}

    async def get_file(self):
        filename = request.args.get("filename")
        if not filename:
            return Response().error("Missing key: filename").__dict__

        try:
            file_path = os.path.join(self.attachments_dir, os.path.basename(filename))
            real_file_path = os.path.realpath(file_path)
            real_imgs_dir = os.path.realpath(self.attachments_dir)

            if not os.path.exists(real_file_path):
                # try legacy
                file_path = os.path.join(
                    self.legacy_img_dir, os.path.basename(filename)
                )
                if os.path.exists(file_path):
                    real_file_path = os.path.realpath(file_path)
                    real_imgs_dir = os.path.realpath(self.legacy_img_dir)

            if not real_file_path.startswith(real_imgs_dir):
                return Response().error("Invalid file path").__dict__

            filename_ext = os.path.splitext(filename)[1].lower()
            if filename_ext == ".wav":
                return await send_file(real_file_path, mimetype="audio/wav")
            if filename_ext[1:] in self.supported_imgs:
                return await send_file(real_file_path, mimetype="image/jpeg")
            return await send_file(real_file_path)

        except (FileNotFoundError, OSError):
            return Response().error("File access error").__dict__

    async def get_attachment(self):
        """Get attachment file by attachment_id."""
        attachment_id = request.args.get("attachment_id")
        if not attachment_id:
            return Response().error("Missing key: attachment_id").__dict__

        try:
            attachment = await self.db.get_attachment_by_id(attachment_id)
            if not attachment:
                return Response().error("Attachment not found").__dict__

            file_path = attachment.path
            real_file_path = os.path.realpath(file_path)

            return await send_file(real_file_path, mimetype=attachment.mime_type)

        except (FileNotFoundError, OSError):
            return Response().error("File access error").__dict__

    async def post_file(self):
        """Upload a file and create an attachment record, return attachment_id."""
        post_data = await request.files
        if "file" not in post_data:
            return Response().error("Missing key: file").__dict__

        file = post_data["file"]
        filename = file.filename or f"{uuid.uuid4()!s}"
        content_type = file.content_type or "application/octet-stream"

        # 根据 content_type 判断文件类型并添加扩展名
        if content_type.startswith("image"):
            attach_type = "image"
        elif content_type.startswith("audio"):
            attach_type = "record"
        elif content_type.startswith("video"):
            attach_type = "video"
        else:
            attach_type = "file"

        path = os.path.join(self.attachments_dir, filename)
        await file.save(path)

        # 创建 attachment 记录
        attachment = await self.db.insert_attachment(
            path=path,
            type=attach_type,
            mime_type=content_type,
        )

        if not attachment:
            return Response().error("Failed to create attachment").__dict__

        filename = os.path.basename(attachment.path)

        return (
            Response()
            .ok(
                data={
                    "attachment_id": attachment.attachment_id,
                    "filename": filename,
                    "type": attach_type,
                }
            )
            .__dict__
        )

    async def _build_user_message_parts(self, message: str | list) -> list[dict]:
        """构建用户消息的部分列表。"""
        return await build_webchat_message_parts(
            message,
            get_attachment_by_id=self.db.get_attachment_by_id,
            strict=False,
        )

    async def _create_attachment_from_file(
        self, filename: str, attach_type: str
    ) -> dict | None:
        """从本地文件创建 attachment 并返回消息部分。"""
        return await create_attachment_part_from_existing_file(
            filename,
            attach_type=attach_type,
            insert_attachment=self.db.insert_attachment,
            attachments_dir=self.attachments_dir,
            fallback_dirs=[self.legacy_img_dir],
        )

    def _extract_web_search_refs(
        self, accumulated_text: str, accumulated_parts: list
    ) -> dict:
        """从消息中提取 web_search_tavily 的引用

        Args:
            accumulated_text: 累积的文本内容
            accumulated_parts: 累积的消息部分列表

        Returns:
            包含 used 列表的字典，记录被引用的搜索结果
        """
        supported = [
            "web_search_baidu",
            "web_search_tavily",
            "web_search_bocha",
            "web_search_brave",
        ]
        # 从 accumulated_parts 中找到所有 web_search_tavily 的工具调用结果
        web_search_results = {}
        tool_call_parts = [
            p
            for p in accumulated_parts
            if p.get("type") == "tool_call" and p.get("tool_calls")
        ]

        for part in tool_call_parts:
            for tool_call in part["tool_calls"]:
                if tool_call.get("name") not in supported or not tool_call.get(
                    "result"
                ):
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

        # 从文本中提取所有 <ref>xxx</ref> 标签并去重
        ref_indices = {
            m.strip() for m in re.findall(r"<ref>(.*?)</ref>", accumulated_text)
        }

        # 构建被引用的结果列表
        used_refs = []
        for ref_index in ref_indices:
            if ref_index not in web_search_results:
                continue
            payload = {"index": ref_index, **web_search_results[ref_index]}
            if favicon := sp.temporary_cache.get("_ws_favicon", {}).get(payload["url"]):
                payload["favicon"] = favicon
            used_refs.append(payload)

        return {"used": used_refs} if used_refs else {}

    async def _save_bot_message(
        self,
        webchat_conv_id: str,
        text: str,
        media_parts: list,
        reasoning: str,
        agent_stats: dict,
        refs: dict,
    ):
        """保存 bot 消息到历史记录，返回保存的记录"""
        bot_message_parts = []
        bot_message_parts.extend(media_parts)
        if text:
            bot_message_parts.append({"type": "plain", "text": text})

        new_his = {"type": "bot", "message": bot_message_parts}
        if reasoning:
            new_his["reasoning"] = reasoning
        if agent_stats:
            new_his["agent_stats"] = agent_stats
        if refs:
            new_his["refs"] = refs

        record = await self.platform_history_mgr.insert(
            platform_id="webchat",
            user_id=webchat_conv_id,
            content=new_his,
            sender_id="bot",
            sender_name="bot",
        )
        return record

    def _sanitize_message_content(self, content: dict) -> dict:
        """Normalize message content before persisting it."""
        if not isinstance(content, dict):
            raise ValueError("Missing key: content")

        normalized = deepcopy(content)
        message_type = normalized.get("type")
        if not isinstance(message_type, str) or not message_type:
            raise ValueError("Missing key: content.type")

        message_parts = normalized.get("message")
        if not isinstance(message_parts, list):
            raise ValueError("Missing key: content.message")
        normalized["message"] = strip_message_parts_path_fields(message_parts)
        return normalized

    def _remap_reply_message_ids(
        self, message_parts: list[dict], message_id_map: dict[str, int]
    ) -> None:
        for part in message_parts:
            if not isinstance(part, dict) or part.get("type") != "reply":
                continue
            message_id = part.get("message_id")
            if message_id is None:
                continue
            mapped_id = message_id_map.get(str(message_id))
            if mapped_id is not None:
                part["message_id"] = mapped_id

    def _build_webchat_unified_msg_origin(self, session) -> str:
        message_type = (
            MessageType.GROUP_MESSAGE
            if session.is_group
            else MessageType.FRIEND_MESSAGE
        )
        return f"{session.platform_id}:{message_type.value}:{session.platform_id}!{session.creator}!{session.session_id}"

    def _serialize_session(self, session, branch_meta: dict | None = None) -> dict:
        return {
            "session_id": session.session_id,
            "platform_id": session.platform_id,
            "creator": session.creator,
            "display_name": session.display_name,
            "is_group": session.is_group,
            "created_at": to_utc_isoformat(session.created_at),
            "updated_at": to_utc_isoformat(session.updated_at),
            "branch_meta": branch_meta,
        }

    def _extract_platform_message_text(self, content: dict | None) -> str:
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

    def _extract_conversation_text(self, message: dict) -> str:
        content = message.get("content")
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""

        texts: list[str] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "text":
                continue
            text = part.get("text")
            if not isinstance(text, str) or text.startswith("<system_reminder>"):
                continue
            texts.append(text)
        return "".join(texts)

    def _extract_conversation_think(self, message: dict) -> str:
        content = message.get("content")
        if not isinstance(content, list):
            return ""

        thinks: list[str] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "think":
                continue
            think = part.get("think")
            if isinstance(think, str):
                thinks.append(think)
        return "".join(thinks)

    def _is_displayable_conversation_message(self, message: dict, role: str) -> bool:
        if message.get("role") != role:
            return False
        if role == "user":
            return True
        content = message.get("content")
        if isinstance(content, str):
            return bool(content)
        if not isinstance(content, list):
            return False
        return any(
            isinstance(part, dict)
            and part.get("type") in {"text", "think", "image_url", "audio_url"}
            for part in content
        )

    def _replace_user_conversation_content(
        self, original_content, edited_text: str
    ) -> str | list[dict]:
        if isinstance(original_content, str):
            return edited_text
        if not isinstance(original_content, list):
            return edited_text

        result: list[dict] = []
        inserted_text = False
        pending_insert_at_end = edited_text

        for part in original_content:
            if not isinstance(part, dict):
                result.append(part)
                continue
            if part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str) and text.startswith("<system_reminder>"):
                    if not inserted_text and pending_insert_at_end:
                        result.append({"type": "text", "text": pending_insert_at_end})
                        inserted_text = True
                        pending_insert_at_end = ""
                    result.append(part)
                    continue
                if not inserted_text and edited_text:
                    result.append({"type": "text", "text": edited_text})
                    inserted_text = True
                    pending_insert_at_end = ""
                continue
            result.append(part)

        if not inserted_text and pending_insert_at_end:
            result.append({"type": "text", "text": pending_insert_at_end})
        return result

    def _replace_assistant_conversation_content(
        self, original_content, edited_text: str, reasoning: str
    ) -> str | list[dict]:
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
            part_type = part.get("type")
            if part_type == "text":
                if not inserted_text and edited_text:
                    result.append({"type": "text", "text": edited_text})
                    inserted_text = True
                continue
            if part_type == "think":
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

    def _find_conversation_history_index(
        self,
        history: list[dict],
        role: str,
        ordinal: int,
        old_text: str,
        old_reasoning: str,
    ) -> int | None:
        candidate_indexes = [
            index
            for index, message in enumerate(history)
            if isinstance(message, dict)
            and self._is_displayable_conversation_message(message, role)
        ]
        if not candidate_indexes:
            return None
        if 0 <= ordinal < len(candidate_indexes):
            return candidate_indexes[ordinal]

        for index in reversed(candidate_indexes):
            message = history[index]
            if old_text and self._extract_conversation_text(message) == old_text:
                return index
            if (
                old_reasoning
                and self._extract_conversation_think(message) == old_reasoning
            ):
                return index
        return candidate_indexes[-1]

    async def _sync_conversation_history_message(
        self,
        session,
        existing_record,
        updated_content: dict,
    ) -> None:
        unified_msg_origin = self._build_webchat_unified_msg_origin(session)
        conversation_id = await self.conv_mgr.get_curr_conversation_id(
            unified_msg_origin
        )
        if not conversation_id:
            return

        conversation = await self.conv_mgr.get_conversation(
            unified_msg_origin=unified_msg_origin,
            conversation_id=conversation_id,
        )
        if not conversation:
            return

        history = json.loads(conversation.history)
        if not isinstance(history, list):
            return

        platform_history = await self.platform_history_mgr.get(
            platform_id=session.platform_id,
            user_id=session.session_id,
            page=1,
            page_size=100000,
        )
        platform_history.sort(key=lambda item: (item.created_at, item.id))

        role_type = existing_record.content.get("type")
        platform_role_records = [
            item
            for item in platform_history
            if isinstance(item.content, dict) and item.content.get("type") == role_type
        ]
        ordinal = next(
            (
                index
                for index, item in enumerate(platform_role_records)
                if item.id == existing_record.id
            ),
            -1,
        )
        if ordinal < 0:
            return

        conversation_role = "user" if role_type == "user" else "assistant"
        target_index = self._find_conversation_history_index(
            history=history,
            role=conversation_role,
            ordinal=ordinal,
            old_text=self._extract_platform_message_text(existing_record.content),
            old_reasoning=existing_record.content.get("reasoning", ""),
        )
        if target_index is None:
            return

        target_message = history[target_index]
        original_content = target_message.get("content")
        edited_text = self._extract_platform_message_text(updated_content)

        if conversation_role == "user":
            target_message["content"] = self._replace_user_conversation_content(
                original_content, edited_text
            )
        else:
            target_message["content"] = self._replace_assistant_conversation_content(
                original_content,
                edited_text,
                updated_content.get("reasoning", ""),
            )

        await self.conv_mgr.update_conversation(
            unified_msg_origin=unified_msg_origin,
            conversation_id=conversation_id,
            history=history,
        )

    def _trim_conversation_history(
        self,
        history: list[dict],
        *,
        max_user_messages: int | None = None,
        max_assistant_messages: int | None = None,
    ) -> list[dict]:
        user_count = 0
        assistant_count = 0
        trimmed_history: list[dict] = []

        for message in history:
            if not isinstance(message, dict):
                trimmed_history.append(deepcopy(message))
                continue

            if self._is_displayable_conversation_message(message, "user"):
                if max_user_messages is None or user_count < max_user_messages:
                    trimmed_history.append(deepcopy(message))
                    user_count += 1
                continue

            if self._is_displayable_conversation_message(message, "assistant"):
                if (
                    max_assistant_messages is None
                    or assistant_count < max_assistant_messages
                ):
                    trimmed_history.append(deepcopy(message))
                    assistant_count += 1
                continue

            trimmed_history.append(deepcopy(message))

        return trimmed_history

    async def _clone_current_conversation(
        self,
        source_session,
        target_session,
        *,
        max_user_messages: int | None = None,
        max_assistant_messages: int | None = None,
    ) -> None:
        source_umo = self._build_webchat_unified_msg_origin(source_session)
        source_cid = await self.conv_mgr.get_curr_conversation_id(source_umo)
        if not source_cid:
            return

        source_conversation = await self.conv_mgr.get_conversation(
            unified_msg_origin=source_umo,
            conversation_id=source_cid,
        )
        if not source_conversation:
            return

        history = json.loads(source_conversation.history)
        if not isinstance(history, list):
            history = []
        trimmed_history = self._trim_conversation_history(
            history,
            max_user_messages=max_user_messages,
            max_assistant_messages=max_assistant_messages,
        )

        target_umo = self._build_webchat_unified_msg_origin(target_session)
        await self.conv_mgr.new_conversation(
            unified_msg_origin=target_umo,
            platform_id=target_session.platform_id,
            content=trimmed_history,
            title=source_conversation.title,
            persona_id=source_conversation.persona_id,
        )

    async def _rewrite_current_conversation(
        self,
        session,
        *,
        max_user_messages: int | None = None,
        max_assistant_messages: int | None = None,
    ) -> None:
        unified_msg_origin = self._build_webchat_unified_msg_origin(session)
        conversation_id = await self.conv_mgr.get_curr_conversation_id(
            unified_msg_origin
        )
        if not conversation_id:
            return

        conversation = await self.conv_mgr.get_conversation(
            unified_msg_origin=unified_msg_origin,
            conversation_id=conversation_id,
        )
        if not conversation:
            return

        history = json.loads(conversation.history)
        if not isinstance(history, list):
            history = []
        trimmed_history = self._trim_conversation_history(
            history,
            max_user_messages=max_user_messages,
            max_assistant_messages=max_assistant_messages,
        )
        await self.conv_mgr.update_conversation(
            unified_msg_origin=unified_msg_origin,
            conversation_id=conversation_id,
            history=trimmed_history,
        )

    async def _get_branch_meta(self, session_id: str) -> dict | None:
        preference = await self.db.get_preference(
            self.branch_meta_scope,
            session_id,
            self.branch_meta_key,
        )
        if not preference or not isinstance(preference.value, dict):
            return None
        return preference.value

    async def _set_branch_meta(
        self,
        session_id: str,
        *,
        source_session,
        branch_type: str,
        source_message_id: int | None = None,
    ) -> dict:
        source_title = source_session.display_name or "New Conversation"
        branch_meta = {
            "type": branch_type,
            "source_session_id": source_session.session_id,
            "source_display_name": source_title,
        }
        if source_message_id is not None:
            branch_meta["source_message_id"] = source_message_id
        await self.db.insert_preference_or_update(
            self.branch_meta_scope,
            session_id,
            self.branch_meta_key,
            branch_meta,
        )
        return branch_meta

    async def _clone_session_route(self, source_session, target_session) -> None:
        source_umo = self._build_webchat_unified_msg_origin(source_session)
        target_umo = self._build_webchat_unified_msg_origin(target_session)
        source_conf_id = self.umop_config_router.get_conf_id_for_umop(source_umo)
        if source_conf_id:
            await self.umop_config_router.update_route(target_umo, source_conf_id)

    async def _get_sorted_platform_history(self, session) -> list:
        history_list = await self.platform_history_mgr.get(
            platform_id=session.platform_id,
            user_id=session.session_id,
            page=1,
            page_size=100000,
        )
        history_list.sort(key=lambda history: (history.created_at, history.id))
        return history_list

    def _find_message_index(self, history_list: list, message_id: int) -> int | None:
        for index, history in enumerate(history_list):
            if history.id == message_id:
                return index
        return None

    def _build_branch_display_name(self, source_session, branch_type: str) -> str:
        base_name = (source_session.display_name or "New Conversation").strip()
        suffix = " - Regenerated" if branch_type == "regenerate" else " - Branch"
        return f"{base_name}{suffix}"

    async def _create_branch_session(
        self,
        source_session,
        username: str,
        *,
        display_name: str | None = None,
        branch_type: str = "branch",
        source_message_id: int | None = None,
        max_user_messages: int | None = None,
        max_assistant_messages: int | None = None,
    ) -> tuple[object, dict | None, dict]:
        project_info = await self.db.get_project_by_session(
            session_id=source_session.session_id,
            creator=username,
        )
        cloned_session = await self.db.create_platform_session(
            creator=username,
            platform_id=source_session.platform_id,
            display_name=display_name
            if display_name is not None
            else self._build_branch_display_name(source_session, branch_type),
            is_group=source_session.is_group,
        )

        if project_info:
            await self.db.add_session_to_project(
                session_id=cloned_session.session_id,
                project_id=project_info.project_id,
            )
        await self._clone_session_route(source_session, cloned_session)
        await self._clone_current_conversation(
            source_session,
            cloned_session,
            max_user_messages=max_user_messages,
            max_assistant_messages=max_assistant_messages,
        )

        branch_meta = await self._set_branch_meta(
            cloned_session.session_id,
            source_session=source_session,
            branch_type=branch_type,
            source_message_id=source_message_id,
        )
        return cloned_session, project_info, branch_meta

    async def chat(self, post_data: dict | None = None):
        username = g.get("username", "guest")

        if post_data is None:
            post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").__dict__
        if "message" not in post_data and "files" not in post_data:
            return Response().error("Missing key: message or files").__dict__

        if "session_id" not in post_data and "conversation_id" not in post_data:
            return (
                Response().error("Missing key: session_id or conversation_id").__dict__
            )

        message = post_data["message"]
        session_id = post_data.get("session_id", post_data.get("conversation_id"))
        selected_provider = post_data.get("selected_provider")
        selected_model = post_data.get("selected_model")
        enable_streaming = post_data.get("enable_streaming", True)

        if not session_id:
            return Response().error("session_id is empty").__dict__

        webchat_conv_id = session_id

        # 构建用户消息段（包含 path 用于传递给 adapter）
        message_parts = await self._build_user_message_parts(message)
        if not webchat_message_parts_have_content(message_parts):
            return (
                Response()
                .error("Message content is empty (reply only is not allowed)")
                .__dict__
            )

        message_id = str(uuid.uuid4())
        back_queue = webchat_queue_mgr.get_or_create_back_queue(
            message_id,
            webchat_conv_id,
        )

        async def stream():
            client_disconnected = False
            accumulated_parts = []
            accumulated_text = ""
            accumulated_reasoning = ""
            tool_calls = {}
            agent_stats = {}
            refs = {}
            try:
                # Emit session_id first so clients can bind the stream immediately.
                session_info = {
                    "type": "session_id",
                    "data": None,
                    "session_id": webchat_conv_id,
                }
                yield f"data: {json.dumps(session_info, ensure_ascii=False)}\n\n"
                if saved_user_record:
                    user_saved_info = build_message_saved_event(
                        saved_user_record,
                        "user",
                    )
                    yield f"data: {json.dumps(user_saved_info, ensure_ascii=False)}\n\n"

                async with track_conversation(self.running_convs, webchat_conv_id):
                    while True:
                        result, should_break = await _poll_webchat_stream_result(
                            back_queue, username
                        )
                        if should_break:
                            client_disconnected = True
                            break
                        if not result:
                            # Send an SSE comment as keep-alive so the client
                            # doesn't time out during slow backend ops like
                            # context compression with reasoning models (#6938).
                            if not client_disconnected:
                                yield SSE_HEARTBEAT
                            continue

                        if (
                            "message_id" in result
                            and result["message_id"] != message_id
                        ):
                            logger.warning("webchat stream message_id mismatch")
                            continue

                        result_text = result["data"]
                        msg_type = result.get("type")
                        streaming = result.get("streaming", False)
                        chain_type = result.get("chain_type")

                        if chain_type == "agent_stats":
                            stats_info = {
                                "type": "agent_stats",
                                "data": json.loads(result_text),
                            }
                            yield f"data: {json.dumps(stats_info, ensure_ascii=False)}\n\n"
                            agent_stats = stats_info["data"]
                            continue

                        # 发送 SSE 数据
                        try:
                            if not client_disconnected:
                                yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
                        except Exception as e:
                            if not client_disconnected:
                                logger.debug(
                                    f"[WebChat] 用户 {username} 断开聊天长连接。 {e}"
                                )
                            client_disconnected = True

                        try:
                            if not client_disconnected:
                                await asyncio.sleep(0.05)
                        except asyncio.CancelledError:
                            logger.debug(f"[WebChat] 用户 {username} 断开聊天长连接。")
                            client_disconnected = True

                        # 累积消息部分
                        if msg_type == "plain":
                            chain_type = result.get("chain_type")
                            if chain_type == "tool_call":
                                tool_call = json.loads(result_text)
                                tool_calls[tool_call.get("id")] = tool_call
                                if accumulated_text:
                                    # 如果累积了文本，则先保存文本
                                    accumulated_parts.append(
                                        {"type": "plain", "text": accumulated_text}
                                    )
                                    accumulated_text = ""
                            elif chain_type == "tool_call_result":
                                tcr = json.loads(result_text)
                                tc_id = tcr.get("id")
                                if tc_id in tool_calls:
                                    tool_calls[tc_id]["result"] = tcr.get("result")
                                    tool_calls[tc_id]["finished_ts"] = tcr.get("ts")
                                    accumulated_parts.append(
                                        {
                                            "type": "tool_call",
                                            "tool_calls": [tool_calls[tc_id]],
                                        }
                                    )
                                    tool_calls.pop(tc_id, None)
                            elif chain_type == "reasoning":
                                accumulated_reasoning += result_text
                            elif streaming:
                                accumulated_text += result_text
                            else:
                                accumulated_text = result_text
                        elif msg_type == "image":
                            filename = result_text.replace("[IMAGE]", "")
                            part = await self._create_attachment_from_file(
                                filename, "image"
                            )
                            if part:
                                accumulated_parts.append(part)
                        elif msg_type == "record":
                            filename = result_text.replace("[RECORD]", "")
                            part = await self._create_attachment_from_file(
                                filename, "record"
                            )
                            if part:
                                accumulated_parts.append(part)
                        elif msg_type == "file":
                            # 格式: [FILE]filename
                            filename = result_text.replace("[FILE]", "")
                            part = await self._create_attachment_from_file(
                                filename, "file"
                            )
                            if part:
                                accumulated_parts.append(part)

                        # 消息结束处理
                        if msg_type == "end":
                            break
                        elif (
                            (streaming and msg_type == "complete") or not streaming
                            # or msg_type == "break"
                        ):
                            if (
                                chain_type == "tool_call"
                                or chain_type == "tool_call_result"
                            ):
                                continue

                            # 提取 web_search_tavily 引用
                            try:
                                refs = self._extract_web_search_refs(
                                    accumulated_text,
                                    accumulated_parts,
                                )
                            except Exception as e:
                                logger.exception(
                                    f"Failed to extract web search refs: {e}",
                                    exc_info=True,
                                )

                            saved_record = await self._save_bot_message(
                                webchat_conv_id,
                                accumulated_text,
                                accumulated_parts,
                                accumulated_reasoning,
                                agent_stats,
                                refs,
                            )
                            # 发送保存的消息信息给前端
                            if saved_record and not client_disconnected:
                                saved_info = build_message_saved_event(
                                    saved_record,
                                    "bot",
                                )
                                try:
                                    yield f"data: {json.dumps(saved_info, ensure_ascii=False)}\n\n"
                                except Exception:
                                    pass
                            accumulated_parts = []
                            accumulated_text = ""
                            accumulated_reasoning = ""
                            # tool_calls = {}
                            agent_stats = {}
                            refs = {}
            except BaseException as e:
                logger.exception(f"WebChat stream unexpected error: {e}", exc_info=True)
            finally:
                webchat_queue_mgr.remove_back_queue(message_id)

        # 将消息放入会话特定的队列
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
                },
            ),
        )

        message_parts_for_storage = strip_message_parts_path_fields(message_parts)

        saved_user_record = await self.platform_history_mgr.insert(
            platform_id="webchat",
            user_id=webchat_conv_id,
            content={"type": "user", "message": message_parts_for_storage},
            sender_id=username,
            sender_name=username,
        )

        response = cast(
            QuartResponse,
            await make_response(
                stream(),
                {
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Transfer-Encoding": "chunked",
                    "Connection": "keep-alive",
                },
            ),
        )
        response.timeout = None  # fix SSE auto disconnect issue
        return response

    async def stop_session(self):
        """Stop active agent runs for a session."""
        post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").__dict__

        session_id = post_data.get("session_id")
        if not session_id:
            return Response().error("Missing key: session_id").__dict__

        username = g.get("username", "guest")
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").__dict__
        if session.creator != username:
            return Response().error("Permission denied").__dict__

        message_type = (
            MessageType.GROUP_MESSAGE.value
            if session.is_group
            else MessageType.FRIEND_MESSAGE.value
        )
        umo = (
            f"{session.platform_id}:{message_type}:"
            f"{session.platform_id}!{username}!{session_id}"
        )
        stopped_count = active_event_registry.request_agent_stop_all(umo)

        return Response().ok(data={"stopped_count": stopped_count}).__dict__

    async def _delete_session_internal(self, session, username: str) -> None:
        """Delete a single session and all its related data."""
        session_id = session.session_id

        # 删除该会话下的所有对话
        message_type = "GroupMessage" if session.is_group else "FriendMessage"
        unified_msg_origin = f"{session.platform_id}:{message_type}:{session.platform_id}!{username}!{session_id}"
        await self.conv_mgr.delete_conversations_by_user_id(unified_msg_origin)

        # 获取消息历史中的所有附件 ID 并删除附件
        history_list = await self.platform_history_mgr.get(
            platform_id=session.platform_id,
            user_id=session_id,
            page=1,
            page_size=100000,  # 获取足够多的记录
        )
        attachment_ids = self._extract_attachment_ids(history_list)
        if attachment_ids:
            await self._delete_attachments(attachment_ids)

        # 删除消息历史
        await self.platform_history_mgr.delete(
            platform_id=session.platform_id,
            user_id=session_id,
            offset_sec=99999999,
        )

        # 删除与会话关联的配置路由
        try:
            await self.umop_config_router.delete_route(unified_msg_origin)
        except ValueError as exc:
            logger.warning(
                "Failed to delete UMO route %s during session cleanup: %s",
                unified_msg_origin,
                exc,
            )

        # 清理队列（仅对 webchat）
        if session.platform_id == "webchat":
            webchat_queue_mgr.remove_queues(session_id)

        await self.db.remove_preference(
            self.branch_meta_scope,
            session_id,
            self.branch_meta_key,
        )

        # 删除会话
        await self.db.delete_platform_session(session_id)

    async def delete_webchat_session(self):
        """Delete a Platform session and all its related data."""
        session_id = request.args.get("session_id")
        if not session_id:
            return Response().error("Missing key: session_id").__dict__
        username = g.get("username", "guest")

        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").__dict__
        if session.creator != username:
            return Response().error("Permission denied").__dict__

        await self._delete_session_internal(session, username)

        return Response().ok().__dict__

    async def batch_delete_sessions(self):
        """Batch delete multiple Platform sessions."""
        post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").__dict__
        if not isinstance(post_data, dict):
            return Response().error("Invalid JSON body: expected object").__dict__

        session_ids = post_data.get("session_ids")
        if not session_ids or not isinstance(session_ids, list):
            return Response().error("Missing or invalid key: session_ids").__dict__

        username = g.get("username", "guest")
        sessions = await self.db.get_platform_sessions_by_ids(session_ids)
        sessions_by_id = {session.session_id: session for session in sessions}
        deleted_count = 0
        failed_items = []

        for sid in session_ids:
            session = sessions_by_id.get(sid)
            if not session:
                failed_items.append({"session_id": sid, "reason": "not found"})
                continue
            if session.creator != username:
                failed_items.append({"session_id": sid, "reason": "permission denied"})
                continue

            try:
                await self._delete_session_internal(session, username)
                deleted_count += 1
                sessions_by_id.pop(sid, None)
            except Exception:
                logger.warning("Failed to delete session %s", sid)
                failed_items.append({"session_id": sid, "reason": "internal_error"})

        return (
            Response()
            .ok(
                data={
                    "deleted_count": deleted_count,
                    "failed_count": len(failed_items),
                    "failed_items": failed_items,
                }
            )
            .__dict__
        )

    def _extract_attachment_ids(self, history_list) -> list[str]:
        """从消息历史中提取所有 attachment_id"""
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

    async def _delete_attachments(self, attachment_ids: list[str]) -> None:
        """删除附件（包括数据库记录和磁盘文件）"""
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

        # 批量删除数据库记录
        try:
            await self.db.delete_attachments(attachment_ids)
        except Exception as e:
            logger.warning(f"Failed to delete attachments: {e}")

    async def new_session(self):
        """Create a new Platform session (default: webchat)."""
        username = g.get("username", "guest")

        # 获取可选的 platform_id 参数，默认为 webchat
        platform_id = request.args.get("platform_id", "webchat")

        # 创建新会话
        session = await self.db.create_platform_session(
            creator=username,
            platform_id=platform_id,
            is_group=0,
        )

        return (
            Response()
            .ok(
                data={
                    "session_id": session.session_id,
                    "platform_id": session.platform_id,
                }
            )
            .__dict__
        )

    async def get_sessions(self):
        """Get all Platform sessions for the current user."""
        username = g.get("username", "guest")

        # 获取可选的 platform_id 参数
        platform_id = request.args.get("platform_id")

        sessions, _ = await self.db.get_platform_sessions_by_creator_paginated(
            creator=username,
            platform_id=platform_id,
            page=1,
            page_size=100,  # 暂时返回前100个
            exclude_project_sessions=True,
        )

        session_ids = [item["session"].session_id for item in sessions]
        branch_preferences = await self.db.get_preferences_by_scope_ids(
            self.branch_meta_scope,
            session_ids,
            key=self.branch_meta_key,
        )
        branch_meta_map = {
            preference.scope_id: preference.value
            for preference in branch_preferences
            if isinstance(preference.value, dict)
        }

        # 转换为字典格式
        sessions_data = []
        for item in sessions:
            session = item["session"]
            sessions_data.append(
                self._serialize_session(
                    session,
                    branch_meta_map.get(session.session_id),
                )
            )

        return Response().ok(data=sessions_data).__dict__

    async def get_session(self):
        """Get session information and message history by session_id."""
        session_id = request.args.get("session_id")
        if not session_id:
            return Response().error("Missing key: session_id").__dict__

        username = g.get("username", "guest")

        # 获取会话信息以确定 platform_id
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").__dict__
        if session.creator != username:
            return Response().error("Permission denied").__dict__

        platform_id = session.platform_id if session else "webchat"
        branch_meta = await self._get_branch_meta(session_id)

        # 获取项目信息（如果会话属于某个项目）
        project_info = await self.db.get_project_by_session(
            session_id=session_id, creator=username
        )

        # Get platform message history using session_id
        history_ls = await self.platform_history_mgr.get(
            platform_id=platform_id,
            user_id=session_id,
            page=1,
            page_size=1000,
        )

        history_res = [history.model_dump() for history in history_ls]

        response_data = {
            "history": history_res,
            "is_running": self.running_convs.get(session_id, False),
            "branch_meta": branch_meta,
        }

        # 如果会话属于项目，添加项目信息
        if project_info:
            response_data["project"] = {
                "project_id": project_info.project_id,
                "title": project_info.title,
                "emoji": project_info.emoji,
            }

        return Response().ok(data=response_data).__dict__

    async def update_session_display_name(self):
        """Update a Platform session's display name."""
        post_data = await request.json

        session_id = post_data.get("session_id")
        display_name = post_data.get("display_name")

        if not session_id:
            return Response().error("Missing key: session_id").__dict__
        if display_name is None:
            return Response().error("Missing key: display_name").__dict__

        username = g.get("username", "guest")

        # 验证会话是否存在且属于当前用户
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").__dict__
        if session.creator != username:
            return Response().error("Permission denied").__dict__

        # 更新 display_name
        await self.db.update_platform_session(
            session_id=session_id,
            display_name=display_name,
        )

        return Response().ok().__dict__

    async def update_message(self):
        """Update a persisted WebChat message."""
        post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").__dict__

        session_id = post_data.get("session_id")
        message_id = post_data.get("message_id")
        content = post_data.get("content")

        if not session_id:
            return Response().error("Missing key: session_id").__dict__
        if message_id is None:
            return Response().error("Missing key: message_id").__dict__

        try:
            message_id = int(message_id)
            content = self._sanitize_message_content(content)
        except (TypeError, ValueError) as exc:
            return Response().error(str(exc)).__dict__

        username = g.get("username", "guest")
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").__dict__
        if session.creator != username:
            return Response().error("Permission denied").__dict__

        record = await self.db.get_platform_message_history_by_id(message_id)
        if not record:
            return Response().error(f"Message {message_id} not found").__dict__
        if record.platform_id != session.platform_id or record.user_id != session_id:
            return Response().error("Message does not belong to the session").__dict__
        original_type = (
            record.content.get("type") if isinstance(record.content, dict) else None
        )
        if original_type not in {"user", "bot"}:
            return Response().error("Unsupported message type").__dict__
        if content.get("type") != original_type:
            return Response().error("Message type cannot be changed").__dict__

        await self.db.update_platform_message_history(
            message_id=message_id, content=content
        )
        await self._sync_conversation_history_message(
            session=session,
            existing_record=record,
            updated_content=content,
        )
        await self.db.update_platform_session(session_id=session_id)
        updated_record = await self.db.get_platform_message_history_by_id(message_id)
        if not updated_record:
            return Response().error(f"Message {message_id} not found").__dict__
        return Response().ok(data=updated_record.model_dump()).__dict__

    async def branch_session(self):
        """Duplicate a WebChat session and its persisted message history."""
        post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").__dict__

        session_id = post_data.get("session_id")
        display_name = post_data.get("display_name")
        if not session_id:
            return Response().error("Missing key: session_id").__dict__
        if display_name is not None and not isinstance(display_name, str):
            return Response().error("Invalid key: display_name").__dict__

        username = g.get("username", "guest")
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").__dict__
        if session.creator != username:
            return Response().error("Permission denied").__dict__
        history_list = await self._get_sorted_platform_history(session)
        cloned_session, project_info, branch_meta = await self._create_branch_session(
            session,
            username,
            display_name=display_name,
            branch_type="branch",
        )

        old_to_new_message_ids: dict[str, int] = {}
        for history in history_list:
            cloned_content = deepcopy(history.content or {})
            message_parts = cloned_content.get("message")
            if isinstance(message_parts, list):
                self._remap_reply_message_ids(message_parts, old_to_new_message_ids)
                cloned_content["message"] = strip_message_parts_path_fields(
                    message_parts
                )

            new_record = await self.platform_history_mgr.insert(
                platform_id=cloned_session.platform_id,
                user_id=cloned_session.session_id,
                content=cloned_content,
                sender_id=history.sender_id,
                sender_name=history.sender_name,
            )
            old_to_new_message_ids[str(history.id)] = new_record.id

        response_data = self._serialize_session(cloned_session, branch_meta)
        if project_info:
            response_data["project"] = {
                "project_id": project_info.project_id,
                "title": project_info.title,
                "emoji": project_info.emoji,
            }
        return Response().ok(data=response_data).__dict__

    async def regenerate_message(self):
        """Regenerate the latest bot message in the current session."""
        post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").__dict__

        session_id = post_data.get("session_id")
        message_id = post_data.get("message_id")

        if not session_id:
            return Response().error("Missing key: session_id").__dict__
        if message_id is None:
            return Response().error("Missing key: message_id").__dict__

        try:
            message_id = int(message_id)
        except (TypeError, ValueError):
            return Response().error("Invalid key: message_id").__dict__

        username = g.get("username", "guest")
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").__dict__
        if session.creator != username:
            return Response().error("Permission denied").__dict__

        history_list = await self._get_sorted_platform_history(session)
        target_index = self._find_message_index(history_list, message_id)
        if target_index is None:
            return Response().error(f"Message {message_id} not found").__dict__

        target_record = history_list[target_index]
        if target_record.content.get("type") != "bot":
            return Response().error("Only bot messages can be regenerated").__dict__
        if target_index != len(history_list) - 1:
            return (
                Response()
                .error("Only the latest bot message can be regenerated in place")
                .__dict__
            )

        user_index = None
        for index in range(target_index - 1, -1, -1):
            content = history_list[index].content
            if isinstance(content, dict) and content.get("type") == "user":
                user_index = index
                break
        if user_index is None:
            return Response().error("No user message found for regeneration").__dict__

        source_user_record = history_list[user_index]
        if user_index != len(history_list) - 2:
            return (
                Response()
                .error("Only the latest user/bot turn can be regenerated in place")
                .__dict__
            )

        preserved_history = history_list[:user_index]
        preserved_user_count = sum(
            1
            for history in preserved_history
            if isinstance(history.content, dict)
            and history.content.get("type") == "user"
        )
        preserved_bot_count = sum(
            1
            for history in preserved_history
            if isinstance(history.content, dict)
            and history.content.get("type") == "bot"
        )

        await self.db.delete_platform_message_histories(
            [source_user_record.id, target_record.id]
        )
        await self._rewrite_current_conversation(
            session,
            max_user_messages=preserved_user_count,
            max_assistant_messages=preserved_bot_count,
        )
        regenerated_parts = deepcopy(source_user_record.content.get("message", []))
        response_data = {
            "session_id": session.session_id,
            "removed_message_ids": [source_user_record.id, target_record.id],
            "replay_message": {
                "content": {
                    "type": "user",
                    "message": strip_message_parts_path_fields(regenerated_parts)
                    if isinstance(regenerated_parts, list)
                    else [],
                },
                "source_message_id": source_user_record.id,
            },
        }
        return Response().ok(data=response_data).__dict__
