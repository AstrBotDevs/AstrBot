import asyncio
import json
import mimetypes
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import cast

from quart import Response as QuartResponse
from quart import g, make_response, request, send_file

from astrbot.core import logger, sp
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.platform.sources.webchat.webchat_queue_mgr import webchat_queue_mgr
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .route import Response, Route, RouteContext


@asynccontextmanager
async def track_conversation(convs: dict, conv_id: str):
    convs[conv_id] = True
    try:
        yield
    finally:
        convs.pop(conv_id, None)


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
            "/chat/delete_session": ("GET", self.delete_webchat_session),
            "/chat/update_session_display_name": (
                "POST",
                self.update_session_display_name,
            ),
            "/chat/get_file": ("GET", self.get_file),
            "/chat/get_attachment": ("GET", self.get_attachment),
            "/chat/post_file": ("POST", self.post_file),
        }
        self.core_lifecycle = core_lifecycle
        self.register_routes()
        self.imgs_dir = os.path.join(get_astrbot_data_path(), "webchat", "imgs")
        os.makedirs(self.imgs_dir, exist_ok=True)

        self.supported_imgs = ["jpg", "jpeg", "png", "gif", "webp"]
        self.conv_mgr = core_lifecycle.conversation_manager
        self.platform_history_mgr = core_lifecycle.platform_message_history_manager
        self.db = db
        self.umop_config_router = core_lifecycle.umop_config_router

        self.running_convs: dict[str, bool] = {}

    async def get_file(self):
        filename = request.args.get("filename")
        if not filename:
            return Response().error("Missing key: filename").__dict__

        try:
            file_path = os.path.join(self.imgs_dir, os.path.basename(filename))
            real_file_path = os.path.realpath(file_path)
            real_imgs_dir = os.path.realpath(self.imgs_dir)

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

        path = os.path.join(self.imgs_dir, filename)
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
        """构建用户消息的部分列表

        Args:
            message: 文本消息 (str) 或消息段列表 (list)
        """
        parts = []

        if isinstance(message, list):
            for part in message:
                part_type = part.get("type")
                if part_type == "plain":
                    parts.append({"type": "plain", "text": part.get("text", "")})
                elif part_type == "reply":
                    parts.append(
                        {
                            "type": "reply",
                            "message_id": part.get("message_id"),
                            "selected_text": part.get("selected_text", ""),
                        }
                    )
                elif attachment_id := part.get("attachment_id"):
                    attachment = await self.db.get_attachment_by_id(attachment_id)
                    if attachment:
                        parts.append(
                            {
                                "type": attachment.type,
                                "attachment_id": attachment.attachment_id,
                                "filename": os.path.basename(attachment.path),
                                "path": attachment.path,  # will be deleted
                            }
                        )
            return parts

        if message:
            parts.append({"type": "plain", "text": message})

        return parts

    async def _create_attachment_from_file(
        self, filename: str, attach_type: str
    ) -> dict | None:
        """从本地文件创建 attachment 并返回消息部分

        用于处理 bot 回复中的媒体文件

        Args:
            filename: 存储的文件名
            attach_type: 附件类型 (image, record, file, video)
        """
        file_path = os.path.join(self.imgs_dir, os.path.basename(filename))
        if not os.path.exists(file_path):
            return None

        # guess mime type
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "application/octet-stream"

        # insert attachment
        attachment = await self.db.insert_attachment(
            path=file_path,
            type=attach_type,
            mime_type=mime_type,
        )
        if not attachment:
            return None

        return {
            "type": attach_type,
            "attachment_id": attachment.attachment_id,
            "filename": os.path.basename(file_path),
        }

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
        # 从 accumulated_parts 中找到所有 web_search_tavily 的工具调用结果
        web_search_results = {}
        tool_call_parts = [
            p
            for p in accumulated_parts
            if p.get("type") == "tool_call" and p.get("tool_calls")
        ]

        for part in tool_call_parts:
            for tool_call in part["tool_calls"]:
                if tool_call.get("name") != "web_search_tavily" or not tool_call.get(
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
            if favicon := sp.temorary_cache.get("_ws_favicon", {}).get(payload["url"]):
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

    async def chat(self):
        username = g.get("username", "guest")

        post_data = await request.json
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

        # 检查消息是否为空
        if isinstance(message, list):
            has_content = any(
                part.get("type") in ("plain", "image", "record", "file", "video")
                for part in message
            )
            if not has_content:
                return (
                    Response()
                    .error("Message content is empty (reply only is not allowed)")
                    .__dict__
                )
        elif not message:
            return Response().error("Message are both empty").__dict__

        if not session_id:
            return Response().error("session_id is empty").__dict__

        webchat_conv_id = session_id
        back_queue = webchat_queue_mgr.get_or_create_back_queue(webchat_conv_id)

        # 构建用户消息段（包含 path 用于传递给 adapter）
        message_parts = await self._build_user_message_parts(message)

        message_id = str(uuid.uuid4())

        async def stream():
            client_disconnected = False
            accumulated_parts = []
            accumulated_text = ""
            accumulated_reasoning = ""
            tool_calls = {}
            agent_stats = {}
            refs = {}
            try:
                async with track_conversation(self.running_convs, webchat_conv_id):
                    while True:
                        try:
                            result = await asyncio.wait_for(back_queue.get(), timeout=1)
                        except asyncio.TimeoutError:
                            continue
                        except asyncio.CancelledError:
                            logger.debug(f"[WebChat] 用户 {username} 断开聊天长连接。")
                            client_disconnected = True
                        except Exception as e:
                            logger.error(f"WebChat stream error: {e}")

                        if not result:
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
                                saved_info = {
                                    "type": "message_saved",
                                    "data": {
                                        "id": saved_record.id,
                                        "created_at": saved_record.created_at.astimezone().isoformat(),
                                    },
                                }
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

        message_parts_for_storage = []
        for part in message_parts:
            part_copy = {k: v for k, v in part.items() if k != "path"}
            message_parts_for_storage.append(part_copy)

        await self.platform_history_mgr.insert(
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

    async def delete_webchat_session(self):
        """Delete a Platform session and all its related data."""
        session_id = request.args.get("session_id")
        if not session_id:
            return Response().error("Missing key: session_id").__dict__
        username = g.get("username", "guest")

        # 验证会话是否存在且属于当前用户
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").__dict__
        if session.creator != username:
            return Response().error("Permission denied").__dict__

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

        # 删除会话
        await self.db.delete_platform_session(session_id)

        return Response().ok().__dict__

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

    async def _delete_attachments(self, attachment_ids: list[str]):
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

        sessions = await self.db.get_platform_sessions_by_creator(
            creator=username,
            platform_id=platform_id,
            page=1,
            page_size=100,  # 暂时返回前100个
        )

        # 转换为字典格式，并添加项目信息
        # get_platform_sessions_by_creator 现在返回 list[dict] 包含 session 和项目字段
        sessions_data = []
        for item in sessions:
            session = item["session"]
            project_id = item["project_id"]

            # 跳过属于项目的会话（在侧边栏对话列表中不显示）
            if project_id is not None:
                continue

            sessions_data.append(
                {
                    "session_id": session.session_id,
                    "platform_id": session.platform_id,
                    "creator": session.creator,
                    "display_name": session.display_name,
                    "is_group": session.is_group,
                    "created_at": session.created_at.astimezone().isoformat(),
                    "updated_at": session.updated_at.astimezone().isoformat(),
                }
            )

        return Response().ok(data=sessions_data).__dict__

    async def get_session(self):
        """Get session information and message history by session_id."""
        session_id = request.args.get("session_id")
        if not session_id:
            return Response().error("Missing key: session_id").__dict__

        # 获取会话信息以确定 platform_id
        session = await self.db.get_platform_session_by_id(session_id)
        platform_id = session.platform_id if session else "webchat"

        # 获取项目信息（如果会话属于某个项目）
        username = g.get("username", "guest")
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
