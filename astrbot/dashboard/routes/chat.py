import asyncio
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from typing import cast

import anyio
from quart import g, make_response, request, send_file

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
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.datetime_utils import to_utc_isoformat

from .route import Response, Route, RouteContext

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
        return (None, False)
    except asyncio.CancelledError:
        logger.debug(f"[WebChat] 用户 {username} 断开聊天长连接｡")
        return (None, True)
    except Exception as e:
        logger.error(f"WebChat stream error: {e}")
        return (None, False)
    return (result, False)


def _resolve_path(path: str) -> Path:
    return Path(path).resolve(strict=False)


class ChatRoute(Route):
    platform_history_mgr: PlatformMessageHistoryManager

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
            "/chat/message/edit": ("POST", self.update_message),
            "/chat/message/regenerate": ("POST", self.regenerate_message),
            "/chat/thread/create": ("POST", self.create_thread),
            "/chat/thread/get": ("GET", self.get_thread),
            "/chat/thread/send": ("POST", self.send_thread_message),
            "/chat/thread/delete": ("POST", self.delete_thread),
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
        mgr = core_lifecycle.platform_message_history_manager
        assert mgr is not None
        self.platform_history_mgr = mgr
        self.db = db
        self.umop_config_router = core_lifecycle.umop_config_router
        assert self.umop_config_router
        self.running_convs: dict[str, bool] = {}

    async def get_file(self):
        filename = request.args.get("filename")
        if not filename:
            return Response().error("Missing key: filename").to_json()
        try:
            file_path = os.path.join(self.attachments_dir, os.path.basename(filename))
            resolved_file_path = _resolve_path(file_path)
            resolved_base_dir = _resolve_path(self.attachments_dir)
            if not await anyio.Path(resolved_file_path).exists():
                file_path = os.path.join(
                    self.legacy_img_dir,
                    os.path.basename(filename),
                )
                if await anyio.Path(file_path).exists():
                    resolved_file_path = _resolve_path(file_path)
                    resolved_base_dir = _resolve_path(self.legacy_img_dir)
            try:
                resolved_file_path.relative_to(resolved_base_dir)
            except ValueError:
                return Response().error("Invalid file path").to_json()
            filename_ext = os.path.splitext(filename)[1].lower()
            if filename_ext == ".wav":
                return await send_file(str(resolved_file_path), mimetype="audio/wav")
            if filename_ext[1:] in self.supported_imgs:
                return await send_file(str(resolved_file_path), mimetype="image/jpeg")
            return await send_file(str(resolved_file_path))
        except (FileNotFoundError, OSError):
            return Response().error("File access error").to_json()

    async def get_attachment(self):
        """Get attachment file by attachment_id."""
        attachment_id = request.args.get("attachment_id")
        if not attachment_id:
            return Response().error("Missing key: attachment_id").to_json()
        try:
            attachment = await self.db.get_attachment_by_id(attachment_id)
            if not attachment:
                return Response().error("Attachment not found").to_json()
            file_path = attachment.path
            resolved_file_path = _resolve_path(file_path)
            return await send_file(
                str(resolved_file_path),
                mimetype=attachment.mime_type,
            )
        except (FileNotFoundError, OSError):
            return Response().error("File access error").to_json()

    async def post_file(self):
        """Upload a file and create an attachment record, return attachment_id."""
        post_data = await request.files
        if "file" not in post_data:
            return Response().error("Missing key: file").to_json()
        file = post_data["file"]
        filename = file.filename or f"{uuid.uuid4()!s}"
        content_type = file.content_type or "application/octet-stream"
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
        attachment = await self.db.insert_attachment(
            path=path,
            type=attach_type,
            mime_type=content_type,
        )
        if not attachment:
            return Response().error("Failed to create attachment").to_json()
        filename = os.path.basename(attachment.path)
        return (
            Response()
            .ok(
                data={
                    "attachment_id": attachment.attachment_id,
                    "filename": filename,
                    "type": attach_type,
                },
            )
            .to_json()
        )

    async def _build_user_message_parts(self, message: str | list) -> list[dict]:
        """构建用户消息的部分列表｡"""
        return await build_webchat_message_parts(
            message,
            get_attachment_by_id=self.db.get_attachment_by_id,
            strict=False,
        )

    async def _create_attachment_from_file(
        self,
        filename: str,
        attach_type: str,
    ) -> dict | None:
        """从本地文件创建 attachment 并返回消息部分｡"""
        return await create_attachment_part_from_existing_file(
            filename,
            attach_type=attach_type,
            insert_attachment=self.db.insert_attachment,
            attachments_dir=self.attachments_dir,
            fallback_dirs=[self.legacy_img_dir],
        )

    def _extract_web_search_refs(
        self,
        accumulated_text: str,
        accumulated_parts: list,
    ) -> dict:
        """从消息中提取 web_search_tavily 的引用

        Args:
            accumulated_text: 累积的文本内容
            accumulated_parts: 累积的消息部分列表

        Returns:
            包含 used 列表的字典,记录被引用的搜索结果

        """
        supported = ["web_search_tavily", "web_search_bocha"]
        web_search_results = {}
        tool_call_parts = [
            p
            for p in accumulated_parts
            if p.get("type") == "tool_call" and p.get("tool_calls")
        ]
        for part in tool_call_parts:
            for tool_call in part["tool_calls"]:
                if tool_call.get("name") not in supported or not tool_call.get(
                    "result",
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
        ref_indices = {
            m.strip() for m in re.findall("<ref>(.*?)</ref>", accumulated_text)
        }
        used_refs = []
        for ref_index in ref_indices:
            if ref_index not in web_search_results:
                continue
            payload = {"index": ref_index, **web_search_results[ref_index]}
            if favicon := sp.temporary_cache.get("_ws_favicon", {}).get(payload["url"]):
                payload["favicon"] = favicon
            used_refs.append(payload)
        return {"used": used_refs} if used_refs else {}

    def _sanitize_message_content(self, content: dict) -> dict:
        """Normalize editable WebChat message content before persisting."""
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

    def _build_webchat_unified_msg_origin(self, session) -> str:
        message_type = (
            MessageType.GROUP_MESSAGE.value
            if session.is_group
            else MessageType.FRIEND_MESSAGE.value
        )
        return (
            f"{session.platform_id}:{message_type}:"
            f"{session.platform_id}!{session.creator}!{session.session_id}"
        )

    def _build_thread_unified_msg_origin(self, creator: str, thread_id: str) -> str:
        return (
            f"webchat:{MessageType.FRIEND_MESSAGE.value}:webchat!{creator}!{thread_id}"
        )

    def _serialize_thread(self, thread) -> dict:
        return {
            "thread_id": thread.thread_id,
            "parent_session_id": thread.parent_session_id,
            "parent_message_id": thread.parent_message_id,
            "base_checkpoint_id": thread.base_checkpoint_id,
            "selected_text": thread.selected_text,
            "created_at": to_utc_isoformat(thread.created_at),
            "updated_at": to_utc_isoformat(thread.updated_at),
        }

    async def _delete_threads_by_ids(self, thread_ids: list[str], creator: str) -> None:
        for thread_id in thread_ids:
            unified_msg_origin = self._build_thread_unified_msg_origin(
                creator,
                thread_id,
            )
            active_event_registry.request_agent_stop_all(unified_msg_origin)
            await self.conv_mgr.delete_conversations_by_user_id(unified_msg_origin)
            await self.platform_history_mgr.delete(
                platform_id="webchat_thread",
                user_id=thread_id,
                offset_sec=99999999,
            )
            webchat_queue_mgr.remove_queues(thread_id)
            self.running_convs.pop(thread_id, None)

    async def _load_current_conversation_history(self, session) -> tuple[str, list]:
        unified_msg_origin = self._build_webchat_unified_msg_origin(session)
        conversation_id = await self.conv_mgr.get_curr_conversation_id(
            unified_msg_origin,
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

    def _find_checkpoint_index(
        self,
        history: list[dict],
        checkpoint_id: str,
    ) -> int | None:
        for index, message in enumerate(history):
            if get_checkpoint_id(message) == checkpoint_id:
                return index
        return None

    def _find_turn_range(
        self,
        history: list[dict],
        checkpoint_id: str,
    ) -> tuple[int, int] | None:
        checkpoint_index = self._find_checkpoint_index(history, checkpoint_id)
        if checkpoint_index is None:
            return None

        start = 0
        for index in range(checkpoint_index - 1, -1, -1):
            if is_checkpoint_message(history[index]):
                start = index + 1
                break
        return start, checkpoint_index

    def _is_latest_checkpoint(self, history: list[dict], checkpoint_id: str) -> bool:
        for message in reversed(history):
            current_checkpoint_id = get_checkpoint_id(message)
            if current_checkpoint_id:
                return current_checkpoint_id == checkpoint_id
        return False

    def _replace_user_conversation_content(self, original_content, edited_text: str):
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

    def _replace_assistant_conversation_content(
        self,
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

    def _find_turn_user_index(
        self,
        history: list[dict],
        start: int,
        end: int,
    ) -> int | None:
        for index in range(start, end):
            message = history[index]
            if isinstance(message, dict) and message.get("role") == "user":
                return index
        return None

    def _find_turn_final_assistant_index(
        self,
        history: list[dict],
        start: int,
        end: int,
    ) -> int | None:
        for index in range(end - 1, start - 1, -1):
            message = history[index]
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            if message.get("tool_calls") and not message.get("content"):
                continue
            return index
        return None

    async def _get_sorted_platform_history(self, session) -> list:
        history_list = await self.platform_history_mgr.get(
            platform_id=session.platform_id,
            user_id=session.session_id,
            page=1,
            page_size=100000,
        )
        history_list.sort(key=lambda item: (item.created_at, item.id))
        return history_list

    async def _delete_platform_history_after(
        self,
        session,
        message_id: int,
    ) -> list[int]:
        history_list = await self._get_sorted_platform_history(session)
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

    async def _save_bot_message(
        self,
        webchat_conv_id: str,
        text: str,
        media_parts: list,
        reasoning: str,
        agent_stats: dict,
        refs: dict,
        llm_checkpoint_id: str | None = None,
        platform_history_id: str = "webchat",
    ):
        """保存 bot 消息到历史记录,返回保存的记录"""
        bot_message_parts = []
        bot_message_parts.extend(media_parts)
        if text:
            bot_message_parts.append({"type": "plain", "text": text})
        new_his: dict[str, Any] = {"type": "bot", "message": bot_message_parts}
        if reasoning:
            new_his["reasoning"] = reasoning
        if agent_stats:
            new_his["agent_stats"] = agent_stats
        if refs:
            new_his["refs"] = refs
        record = await self.platform_history_mgr.insert(
            platform_id=platform_history_id,
            user_id=webchat_conv_id,
            content=new_his,
            sender_id="bot",
            sender_name="bot",
            llm_checkpoint_id=llm_checkpoint_id,
        )
        return record

    async def chat(self, post_data: dict | None = None):
        username = g.get("username", "guest")
        if post_data is None:
            post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").to_json()
        if "message" not in post_data and "files" not in post_data:
            return Response().error("Missing key: message or files").to_json()
        if "session_id" not in post_data and "conversation_id" not in post_data:
            return (
                Response().error("Missing key: session_id or conversation_id").to_json()
            )
        message = post_data["message"]
        session_id = post_data.get("session_id", post_data.get("conversation_id"))
        selected_provider = post_data.get("selected_provider")
        selected_model = post_data.get("selected_model")
        enable_streaming = post_data.get("enable_streaming", True)
        platform_history_id = post_data.get("_platform_history_id") or "webchat"
        thread_selected_text = post_data.get("_thread_selected_text")

        if not session_id:
            return Response().error("session_id is empty").to_json()
        webchat_conv_id = session_id
        message_parts = await self._build_user_message_parts(message)
        if not webchat_message_parts_have_content(message_parts):
            return (
                Response()
                .error("Message content is empty (reply only is not allowed)")
                .to_json()
            )
        message_id = str(uuid.uuid4())
        llm_checkpoint_id = post_data.get("_llm_checkpoint_id") or str(uuid.uuid4())
        skip_user_history = bool(post_data.get("_skip_user_history"))
        back_queue = webchat_queue_mgr.get_or_create_back_queue(
            message_id,
            webchat_conv_id,
        )
        saved_user_record = None

        async def stream():
            client_disconnected = False
            accumulated_parts = []
            accumulated_text = ""
            accumulated_reasoning = ""
            tool_calls = {}
            agent_stats = {}
            refs = {}
            try:
                session_info = {
                    "type": "session_id",
                    "data": None,
                    "session_id": webchat_conv_id,
                }
                yield f"data: {json.dumps(session_info, ensure_ascii=False)}\n\n"
                if saved_user_record and not client_disconnected:
                    user_saved_info = {
                        "type": "user_message_saved",
                        "data": {
                            "id": saved_user_record.id,
                            "created_at": to_utc_isoformat(
                                saved_user_record.created_at,
                            ),
                            "llm_checkpoint_id": llm_checkpoint_id,
                        },
                    }
                    yield f"data: {json.dumps(user_saved_info, ensure_ascii=False)}\n\n"

                async with track_conversation(self.running_convs, webchat_conv_id):
                    while True:
                        result, should_break = await _poll_webchat_stream_result(
                            back_queue,
                            username,
                        )
                        if should_break:
                            client_disconnected = True
                            break
                        if not result:
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
                        try:
                            if not client_disconnected:
                                yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
                        except Exception as e:
                            if not client_disconnected:
                                logger.debug(
                                    f"[WebChat] 用户 {username} 断开聊天长连接｡ {e}",
                                )
                            client_disconnected = True
                        try:
                            if not client_disconnected:
                                await asyncio.sleep(0.05)
                        except asyncio.CancelledError:
                            logger.debug(f"[WebChat] 用户 {username} 断开聊天长连接｡")
                            client_disconnected = True
                        if msg_type == "plain":
                            chain_type = result.get("chain_type")
                            if chain_type == "tool_call":
                                tool_call = json.loads(result_text)
                                tool_calls[tool_call.get("id")] = tool_call
                                if accumulated_text:
                                    accumulated_parts.append(
                                        {"type": "plain", "text": accumulated_text},
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
                                        },
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
                                filename,
                                "image",
                            )
                            if part:
                                accumulated_parts.append(part)
                        elif msg_type == "record":
                            filename = result_text.replace("[RECORD]", "")
                            part = await self._create_attachment_from_file(
                                filename,
                                "record",
                            )
                            if part:
                                accumulated_parts.append(part)
                        elif msg_type == "file":
                            filename = result_text.replace("[FILE]", "")
                            part = await self._create_attachment_from_file(
                                filename,
                                "file",
                            )
                            if part:
                                accumulated_parts.append(part)
                        if msg_type == "end":
                            break
                        elif (streaming and msg_type == "complete") or not streaming:
                            if (
                                chain_type == "tool_call"
                                or chain_type == "tool_call_result"
                            ):
                                continue
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
                                llm_checkpoint_id,
                                platform_history_id,
                            )
                            if saved_record and (not client_disconnected):
                                saved_info = {
                                    "type": "message_saved",
                                    "data": {
                                        "id": saved_record.id,
                                        "created_at": to_utc_isoformat(
                                            saved_record.created_at,
                                        ),
                                        "llm_checkpoint_id": llm_checkpoint_id,
                                    },
                                }
                                try:
                                    yield f"data: {json.dumps(saved_info, ensure_ascii=False)}\n\n"
                                except Exception:
                                    pass
                            accumulated_parts = []
                            accumulated_text = ""
                            accumulated_reasoning = ""
                            agent_stats = {}
                            refs = {}
            except BaseException as e:
                logger.exception(f"WebChat stream unexpected error: {e}", exc_info=True)
            finally:
                webchat_queue_mgr.remove_back_queue(message_id)

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

        response = cast(
            "QuartResponse",
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
        response.timeout = None
        return response

    async def stop_session(self):
        """Stop active agent runs for a session."""
        post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").to_json()
        session_id = post_data.get("session_id")
        if not session_id:
            return Response().error("Missing key: session_id").to_json()
        username = g.get("username", "guest")
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").to_json()
        if session.creator != username:
            return Response().error("Permission denied").to_json()
        message_type = (
            MessageType.GROUP_MESSAGE.value
            if session.is_group
            else MessageType.FRIEND_MESSAGE.value
        )
        umo = f"{session.platform_id}:{message_type}:{session.platform_id}!{username}!{session_id}"
        stopped_count = active_event_registry.request_agent_stop_all(umo)
        return Response().ok(data={"stopped_count": stopped_count}).to_json()

    async def _delete_session_internal(self, session, username: str) -> None:
        """Delete a single session and all its related data."""
        session_id = session.session_id
        message_type = "GroupMessage" if session.is_group else "FriendMessage"
        unified_msg_origin = f"{session.platform_id}:{message_type}:{session.platform_id}!{username}!{session_id}"
        conv_mgr = self.conv_mgr
        assert conv_mgr is not None
        await conv_mgr.delete_conversations_by_user_id(unified_msg_origin)
        mgr = self.platform_history_mgr
        assert mgr is not None
        history_list = await mgr.get(
            platform_id=session.platform_id,
            user_id=session_id,
            page=1,
            page_size=100000,
        )
        attachment_ids = self._extract_attachment_ids(history_list)
        if attachment_ids:
            await self._delete_attachments(attachment_ids)
        await mgr.delete(
            platform_id=session.platform_id,
            user_id=session_id,
            offset_sec=99999999,
        )
        thread_ids = await self.db.delete_webchat_threads_by_parent_session(session_id)
        await self._delete_threads_by_ids(thread_ids, username)

        # 删除与会话关联的配置路由
        try:
            router = self.umop_config_router
            assert router is not None
            await router.delete_route(unified_msg_origin)
        except ValueError as exc:
            logger.warning(
                "Failed to delete UMO route %s during session cleanup: %s",
                unified_msg_origin,
                exc,
            )
        if session.platform_id == "webchat":
            webchat_queue_mgr.remove_queues(session_id)
        await self.db.delete_platform_session(session_id)

    async def delete_webchat_session(self):
        """Delete a Platform session and all its related data."""
        session_id = request.args.get("session_id")
        if not session_id:
            return Response().error("Missing key: session_id").to_json()
        username = g.get("username", "guest")
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").to_json()
        if session.creator != username:
            return Response().error("Permission denied").to_json()
        await self._delete_session_internal(session, username)
        return Response().ok().to_json()

    async def batch_delete_sessions(self):
        """Batch delete multiple Platform sessions."""
        post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").to_json()
        if not isinstance(post_data, dict):
            return Response().error("Invalid JSON body: expected object").to_json()
        session_ids = post_data.get("session_ids")
        if not session_ids or not isinstance(session_ids, list):
            return Response().error("Missing or invalid key: session_ids").to_json()
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
                },
            )
            .to_json()
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
        """删除附件(包括数据库记录和磁盘文件)"""
        try:
            attachments = await self.db.get_attachments(attachment_ids)
            for attachment in attachments:
                if not await anyio.Path(attachment.path).exists():
                    continue
                try:
                    await anyio.Path(attachment.path).unlink()
                except OSError as e:
                    logger.warning(
                        f"Failed to delete attachment file {attachment.path}: {e}",
                    )
        except Exception as e:
            logger.warning(f"Failed to get attachments: {e}")
        try:
            await self.db.delete_attachments(attachment_ids)
        except Exception as e:
            logger.warning(f"Failed to delete attachments: {e}")

    async def new_session(self):
        """Create a new Platform session (default: webchat)."""
        username = g.get("username", "guest")
        platform_id = request.args.get("platform_id", "webchat")
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
                },
            )
            .to_json()
        )

    async def get_sessions(self):
        """Get all Platform sessions for the current user."""
        username = g.get("username", "guest")
        platform_id = request.args.get("platform_id")
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
                },
            )
        return Response().ok(data=sessions_data).to_json()

    async def get_session(self):
        """Get session information and message history by session_id."""
        session_id = request.args.get("session_id")
        if not session_id:
            return Response().error("Missing key: session_id").to_json()
        session = await self.db.get_platform_session_by_id(session_id)
        platform_id = session.platform_id if session else "webchat"
        username = g.get("username", "guest")
        project_info = await self.db.get_project_by_session(
            session_id=session_id,
            creator=username,
        )
        mgr = self.platform_history_mgr
        assert mgr is not None
        history_ls = await mgr.get(
            platform_id=platform_id,
            user_id=session_id,
            page=1,
            page_size=1000,
        )
        history_res = [history.model_dump() for history in history_ls]
        threads = await self.db.get_webchat_threads_by_parent_session(
            parent_session_id=session_id,
            creator=username,
        )

        response_data = {
            "history": history_res,
            "threads": [self._serialize_thread(thread) for thread in threads],
            "is_running": self.running_convs.get(session_id, False),
        }
        if project_info:
            response_data["project"] = {
                "project_id": project_info.project_id,
                "title": project_info.title,
                "emoji": project_info.emoji,
            }
        return Response().ok(data=response_data).to_json()

    async def create_thread(self):
        """Create or reuse a side thread from a selected assistant message."""
        post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").__dict__

        session_id = post_data.get("session_id")
        parent_message_id = post_data.get("parent_message_id")
        selected_text = str(post_data.get("selected_text") or "").strip()
        if not session_id:
            return Response().error("Missing key: session_id").__dict__
        if parent_message_id is None:
            return Response().error("Missing key: parent_message_id").__dict__
        if not selected_text:
            return Response().error("Missing key: selected_text").__dict__

        try:
            parent_message_id = int(parent_message_id)
        except (TypeError, ValueError):
            return Response().error("Invalid key: parent_message_id").__dict__

        username = g.get("username", "guest")
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").__dict__
        if session.creator != username:
            return Response().error("Permission denied").__dict__

        parent_record = await self.db.get_platform_message_history_by_id(
            parent_message_id,
        )
        if (
            not parent_record
            or parent_record.platform_id != session.platform_id
            or parent_record.user_id != session_id
        ):
            return Response().error("Parent message not found").__dict__
        if not isinstance(parent_record.content, dict):
            return Response().error("Invalid parent message content").__dict__
        if parent_record.content.get("type") != "bot":
            return Response().error("Only bot messages can create threads").__dict__

        checkpoint_id = parent_record.llm_checkpoint_id
        if not checkpoint_id:
            return (
                Response().error("Parent message is not linked to LLM history").__dict__
            )

        existing = await self.db.get_webchat_thread_by_parent_message_and_text(
            parent_session_id=session_id,
            parent_message_id=parent_message_id,
            selected_text=selected_text,
            creator=username,
        )
        if existing:
            return Response().ok(data=self._serialize_thread(existing)).__dict__

        conversation_id, history = await self._load_current_conversation_history(
            session,
        )
        turn_range = self._find_turn_range(history, checkpoint_id)
        if not conversation_id or not turn_range:
            return Response().error("Linked checkpoint not found").__dict__

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
            unified_msg_origin=self._build_thread_unified_msg_origin(
                username,
                thread.thread_id,
            ),
            platform_id="webchat",
            content=base_history,
        )
        return Response().ok(data=self._serialize_thread(thread)).__dict__

    async def get_thread(self):
        """Get a side thread and its message history."""
        thread_id = request.args.get("thread_id")
        if not thread_id:
            return Response().error("Missing key: thread_id").__dict__

        username = g.get("username", "guest")
        thread = await self.db.get_webchat_thread_by_id(thread_id)
        if not thread:
            return Response().error(f"Thread {thread_id} not found").__dict__
        if thread.creator != username:
            return Response().error("Permission denied").__dict__

        history_ls = await self.platform_history_mgr.get(
            platform_id="webchat_thread",
            user_id=thread_id,
            page=1,
            page_size=1000,
        )
        return (
            Response()
            .ok(
                data={
                    "thread": self._serialize_thread(thread),
                    "history": [history.model_dump() for history in history_ls],
                    "is_running": self.running_convs.get(thread_id, False),
                },
            )
            .__dict__
        )

    async def send_thread_message(self):
        """Send a message inside a WebChat side thread."""
        post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").__dict__

        thread_id = post_data.get("thread_id")
        if not thread_id:
            return Response().error("Missing key: thread_id").__dict__

        username = g.get("username", "guest")
        thread = await self.db.get_webchat_thread_by_id(thread_id)
        if not thread:
            return Response().error(f"Thread {thread_id} not found").__dict__
        if thread.creator != username:
            return Response().error("Permission denied").__dict__

        return await self.chat(
            {
                "session_id": thread.thread_id,
                "message": post_data.get("message", []),
                "enable_streaming": post_data.get("enable_streaming", True),
                "selected_provider": post_data.get("selected_provider"),
                "selected_model": post_data.get("selected_model"),
                "_platform_history_id": "webchat_thread",
                "_thread_selected_text": thread.selected_text,
            },
        )

    async def delete_thread(self):
        """Delete a WebChat side thread and its isolated history."""
        post_data = await request.json
        if post_data is None:
            return Response().error("Missing JSON body").__dict__

        thread_id = post_data.get("thread_id")
        if not thread_id:
            return Response().error("Missing key: thread_id").__dict__

        username = g.get("username", "guest")
        thread = await self.db.get_webchat_thread_by_id(thread_id)
        if not thread:
            return Response().error(f"Thread {thread_id} not found").__dict__
        if thread.creator != username:
            return Response().error("Permission denied").__dict__

        await self.db.delete_webchat_thread(thread_id)
        await self._delete_threads_by_ids([thread_id], username)
        return Response().ok(data={"thread_id": thread_id}).__dict__

    async def update_message(self):
        """Update a persisted WebChat message and its linked LLM turn."""
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
        if not isinstance(record.content, dict):
            return Response().error("Invalid message content").__dict__
        if record.content.get("type") != content.get("type"):
            return Response().error("Message type cannot be changed").__dict__
        if content.get("type") != "user":
            return Response().error("Only user messages can be edited").__dict__

        platform_history = await self._get_sorted_platform_history(session)
        latest_user_record = next(
            (
                item
                for item in reversed(platform_history)
                if isinstance(item.content, dict) and item.content.get("type") == "user"
            ),
            None,
        )
        if not latest_user_record or latest_user_record.id != message_id:
            return (
                Response().error("Only the latest user message can be edited").__dict__
            )

        checkpoint_id = record.llm_checkpoint_id
        if not checkpoint_id:
            return (
                Response()
                .error("This message is not linked to LLM history and cannot be edited")
                .__dict__
            )

        conversation_id, history = await self._load_current_conversation_history(
            session,
        )
        turn_range = self._find_turn_range(history, checkpoint_id)
        if not conversation_id or not turn_range:
            return Response().error("Linked checkpoint not found").__dict__
        if not self._is_latest_checkpoint(history, checkpoint_id):
            return Response().error("Only the latest turn can be edited").__dict__

        start, _end = turn_range

        target_index = self._find_turn_user_index(history, start, _end)
        if target_index is None:
            return Response().error("Linked user message not found").__dict__

        new_checkpoint_id = str(uuid.uuid4())
        truncated_history = history[:start]
        await self.platform_history_mgr.update(
            message_id=message_id,
            content=content,
            llm_checkpoint_id=new_checkpoint_id,
        )
        deleted_message_ids = await self._delete_platform_history_after(
            session,
            message_id,
        )
        thread_ids = await self.db.delete_webchat_threads_by_parent_message_ids(
            session_id,
            deleted_message_ids,
        )
        await self._delete_threads_by_ids(thread_ids, username)
        await self.conv_mgr.update_conversation(
            unified_msg_origin=self._build_webchat_unified_msg_origin(session),
            conversation_id=conversation_id,
            history=truncated_history,
        )
        await self.db.update_platform_session(session_id=session_id)
        updated = await self.db.get_platform_message_history_by_id(message_id)
        return (
            Response()
            .ok(
                data={
                    "message": updated.model_dump() if updated else None,
                    "needs_regenerate": True,
                    "truncated_after_message": True,
                },
            )
            .__dict__
        )

    async def regenerate_message(self):
        """Regenerate the latest bot message linked to an LLM checkpoint."""
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

        target_record = await self.db.get_platform_message_history_by_id(message_id)
        if not target_record:
            return Response().error(f"Message {message_id} not found").__dict__
        if (
            target_record.platform_id != session.platform_id
            or target_record.user_id != session_id
        ):
            return Response().error("Message does not belong to the session").__dict__
        if not isinstance(target_record.content, dict):
            return Response().error("Invalid message content").__dict__
        if target_record.content.get("type") != "bot":
            return Response().error("Only bot messages can be regenerated").__dict__

        checkpoint_id = target_record.llm_checkpoint_id
        if not checkpoint_id:
            return Response().error("Message is not linked to LLM history").__dict__

        conversation_id, history = await self._load_current_conversation_history(
            session,
        )
        turn_range = self._find_turn_range(history, checkpoint_id)
        if not conversation_id or not turn_range:
            return Response().error("Linked checkpoint not found").__dict__
        if not self._is_latest_checkpoint(history, checkpoint_id):
            return (
                Response().error("Regenerating older turns requires branching").__dict__
            )

        start, end = turn_range
        user_index = self._find_turn_user_index(history, start, end)
        if user_index is None:
            return Response().error("Linked user message not found").__dict__

        platform_history = await self._get_sorted_platform_history(session)
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
            return Response().error("Linked user display message not found").__dict__

        old_bot_record_ids = [
            item.id
            for item in platform_history
            if item.id is not None
            and item.llm_checkpoint_id == checkpoint_id
            and isinstance(item.content, dict)
            and item.content.get("type") == "bot"
        ]
        if not old_bot_record_ids:
            return Response().error("Linked bot display message not found").__dict__

        new_checkpoint_id = str(uuid.uuid4())
        # The WebChat send path adds the current user message from the prompt.
        # Remove the whole old turn here to avoid duplicating that user message.
        new_history = history[:start] + history[end + 1 :]
        await self.conv_mgr.update_conversation(
            unified_msg_origin=self._build_webchat_unified_msg_origin(session),
            conversation_id=conversation_id,
            history=new_history,
        )
        thread_ids = await self.db.delete_webchat_threads_by_parent_message_ids(
            session_id,
            old_bot_record_ids,
        )
        await self._delete_threads_by_ids(thread_ids, username)
        for old_bot_record_id in old_bot_record_ids:
            await self.platform_history_mgr.delete_by_id(old_bot_record_id)
        await self.platform_history_mgr.update(
            message_id=source_user_record.id,
            llm_checkpoint_id=new_checkpoint_id,
        )

        return await self.chat(
            {
                "session_id": session_id,
                "message": source_user_record.content.get("message", []),
                "enable_streaming": post_data.get("enable_streaming", True),
                "selected_provider": post_data.get("selected_provider"),
                "selected_model": post_data.get("selected_model"),
                "_skip_user_history": True,
                "_llm_checkpoint_id": new_checkpoint_id,
            },
        )

    async def update_session_display_name(self):
        """Update a Platform session's display name."""
        post_data = await request.json
        session_id = post_data.get("session_id")
        display_name = post_data.get("display_name")
        if not session_id:
            return Response().error("Missing key: session_id").to_json()
        if display_name is None:
            return Response().error("Missing key: display_name").to_json()
        username = g.get("username", "guest")
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").to_json()
        if session.creator != username:
            return Response().error("Permission denied").to_json()
        await self.db.update_platform_session(
            session_id=session_id,
            display_name=display_name,
        )
        return Response().ok().to_json()
