import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager

from quart import Response as QuartResponse
from quart import g, make_response, request

from astrbot.core import logger
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
            "/chat/post_image": ("POST", self.post_image),
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

            with open(real_file_path, "rb") as f:
                filename_ext = os.path.splitext(filename)[1].lower()

                if filename_ext == ".wav":
                    return QuartResponse(f.read(), mimetype="audio/wav")
                if filename_ext[1:] in self.supported_imgs:
                    return QuartResponse(f.read(), mimetype="image/jpeg")
                return QuartResponse(f.read())

        except (FileNotFoundError, OSError):
            return Response().error("File access error").__dict__

    async def post_image(self):
        post_data = await request.files
        if "file" not in post_data:
            return Response().error("Missing key: file").__dict__

        file = post_data["file"]
        filename = str(uuid.uuid4()) + ".jpg"
        path = os.path.join(self.imgs_dir, filename)
        await file.save(path)

        return Response().ok(data={"filename": filename}).__dict__

    async def post_file(self):
        post_data = await request.files
        if "file" not in post_data:
            return Response().error("Missing key: file").__dict__

        file = post_data["file"]
        filename = f"{uuid.uuid4()!s}"
        # 通过文件格式判断文件类型
        if file.content_type.startswith("audio"):
            filename += ".wav"

        path = os.path.join(self.imgs_dir, filename)
        await file.save(path)

        return Response().ok(data={"filename": filename}).__dict__

    async def chat(self):
        username = g.get("username", "guest")

        post_data = await request.json
        if "message" not in post_data and "image_url" not in post_data:
            return Response().error("Missing key: message or image_url").__dict__

        if "session_id" not in post_data and "conversation_id" not in post_data:
            return (
                Response().error("Missing key: session_id or conversation_id").__dict__
            )

        message = post_data["message"]
        # conversation_id = post_data["conversation_id"]
        session_id = post_data.get("session_id", post_data.get("conversation_id"))
        image_url = post_data.get("image_url")
        audio_url = post_data.get("audio_url")
        selected_provider = post_data.get("selected_provider")
        selected_model = post_data.get("selected_model")
        enable_streaming = post_data.get("enable_streaming", True)  # 默认为 True

        if not message and not image_url and not audio_url:
            return (
                Response()
                .error("Message and image_url and audio_url are empty")
                .__dict__
            )
        if not session_id:
            return Response().error("session_id is empty").__dict__

        # 追加用户消息
        webchat_conv_id = session_id

        # 获取会话特定的队列
        back_queue = webchat_queue_mgr.get_or_create_back_queue(webchat_conv_id)

        new_his = {"type": "user", "message": message}
        if image_url:
            new_his["image_url"] = image_url
        if audio_url:
            new_his["audio_url"] = audio_url
        await self.platform_history_mgr.insert(
            platform_id="webchat",
            user_id=webchat_conv_id,
            content=new_his,
            sender_id=username,
            sender_name=username,
        )

        async def stream():
            client_disconnected = False

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

                        result_text = result["data"]
                        type = result.get("type")
                        streaming = result.get("streaming", False)

                        try:
                            if not client_disconnected:
                                yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
                        except Exception as e:
                            if not client_disconnected:
                                logger.debug(
                                    f"[WebChat] 用户 {username} 断开聊天长连接。 {e}",
                                )
                            client_disconnected = True

                        try:
                            if not client_disconnected:
                                await asyncio.sleep(0.05)
                        except asyncio.CancelledError:
                            logger.debug(f"[WebChat] 用户 {username} 断开聊天长连接。")
                            client_disconnected = True

                        if type == "end":
                            break
                        elif (
                            (streaming and type == "complete")
                            or not streaming
                            or type == "break"
                        ):
                            # 追加机器人消息
                            new_his = {"type": "bot", "message": result_text}
                            if "reasoning" in result:
                                new_his["reasoning"] = result["reasoning"]
                            await self.platform_history_mgr.insert(
                                platform_id="webchat",
                                user_id=webchat_conv_id,
                                content=new_his,
                                sender_id="bot",
                                sender_name="bot",
                            )
            except BaseException as e:
                logger.exception(f"WebChat stream unexpected error: {e}", exc_info=True)

        # 将消息放入会话特定的队列
        chat_queue = webchat_queue_mgr.get_or_create_queue(webchat_conv_id)
        await chat_queue.put(
            (
                username,
                webchat_conv_id,
                {
                    "message": message,
                    "image_url": image_url,  # list
                    "audio_url": audio_url,
                    "selected_provider": selected_provider,
                    "selected_model": selected_model,
                    "enable_streaming": enable_streaming,
                },
            ),
        )

        response = await make_response(
            stream(),
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Transfer-Encoding": "chunked",
                "Connection": "keep-alive",
            },
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
        unified_msg_origin = f"{session.platform_id}:FriendMessage:{session.platform_id}!{username}!{session_id}"
        await self.conv_mgr.delete_conversations_by_user_id(unified_msg_origin)

        # 删除消息历史
        await self.platform_history_mgr.delete(
            platform_id=session.platform_id,
            user_id=session_id,
            offset_sec=99999999,
        )

        # 清理队列（仅对 webchat）
        if session.platform_id == "webchat":
            webchat_queue_mgr.remove_queues(session_id)

        # 删除会话
        await self.db.delete_platform_session(session_id)

        return Response().ok().__dict__

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

        # 转换为字典格式，并添加额外信息
        sessions_data = []
        for session in sessions:
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

        # Get platform message history using session_id
        history_ls = await self.platform_history_mgr.get(
            platform_id=platform_id,
            user_id=session_id,
            page=1,
            page_size=1000,
        )

        history_res = [history.model_dump() for history in history_ls]

        return (
            Response()
            .ok(
                data={
                    "history": history_res,
                    "is_running": self.running_convs.get(session_id, False),
                },
            )
            .__dict__
        )

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
