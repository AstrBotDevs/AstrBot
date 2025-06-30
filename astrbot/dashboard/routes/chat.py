import uuid
import json
import os
from .route import Route, Response, RouteContext
from astrbot.core import web_chat_queue, web_chat_back_queue
from quart import request, Response as QuartResponse, g, make_response
from astrbot.core.db import BaseDatabase
import asyncio
from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


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
            "/chat/listen": ("GET", self.listener),
            "/chat/new_conversation": ("GET", self.new_conversation),
            "/chat/conversations": ("GET", self.get_conversations),
            "/chat/get_conversation": ("GET", self.get_conversation),
            "/chat/delete_conversation": ("GET", self.delete_conversation),
            "/chat/rename_conversation": ("POST", self.rename_conversation),
            "/chat/get_file": ("GET", self.get_file),
            "/chat/post_image": ("POST", self.post_image),
            "/chat/post_file": ("POST", self.post_file),
            "/chat/status": ("GET", self.status),
        }
        self.db = db
        self.core_lifecycle = core_lifecycle
        self.register_routes()
        self.imgs_dir = os.path.join(get_astrbot_data_path(), "webchat", "imgs")
        os.makedirs(self.imgs_dir, exist_ok=True)

        self.supported_imgs = ["jpg", "jpeg", "png", "gif", "webp"]

        self.curr_user_cid = {}
        self.curr_chat_sse = {}

    async def status(self):
        has_llm_enabled = (
            self.core_lifecycle.provider_manager.curr_provider_inst is not None
        )
        has_stt_enabled = (
            self.core_lifecycle.provider_manager.curr_stt_provider_inst is not None
        )
        return (
            Response()
            .ok(data={"llm_enabled": has_llm_enabled, "stt_enabled": has_stt_enabled})
            .__dict__
        )

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
                elif filename_ext[1:] in self.supported_imgs:
                    return QuartResponse(f.read(), mimetype="image/jpeg")
                else:
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
        filename = f"{str(uuid.uuid4())}"
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

        if "conversation_id" not in post_data:
            return Response().error("Missing key: conversation_id").__dict__

        message = post_data["message"]
        conversation_id = post_data["conversation_id"]
        image_url = post_data.get("image_url")
        audio_url = post_data.get("audio_url")
        if not message and not image_url and not audio_url:
            return (
                Response()
                .error("Message and image_url and audio_url are empty")
                .__dict__
            )
        if not conversation_id:
            return Response().error("conversation_id is empty").__dict__

        self.curr_user_cid[username] = conversation_id

        await web_chat_queue.put(
            (
                username,
                conversation_id,
                {
                    "message": message,
                    "image_url": image_url,  # list
                    "audio_url": audio_url,
                },
            )
        )

        # 持久化
        conversation = self.db.get_conversation_by_user_id(username, conversation_id)
        try:
            history = json.loads(conversation.history)
        except BaseException as e:
            logger.error(f"Failed to parse conversation history: {e}")
            history = []
        new_his = {"type": "user", "message": message}
        if image_url:
            new_his["image_url"] = image_url
        if audio_url:
            new_his["audio_url"] = audio_url
        history.append(new_his)
        self.db.update_conversation(
            username, conversation_id, history=json.dumps(history)
        )

        return Response().ok().__dict__

    async def listener(self):
        """一直保持长连接"""

        username = g.get("username", "guest")

        if username in self.curr_chat_sse:
            return Response().error("Already connected").__dict__

        self.curr_chat_sse[username] = None

        heartbeat = json.dumps({"type": "heartbeat", "data": "ping"})

        async def stream():
            try:
                yield f"data: {heartbeat}\n\n"  # 心跳包
                while True:
                    try:
                        result = await asyncio.wait_for(
                            web_chat_back_queue.get(), timeout=10
                        )  # 设置超时时间为5秒
                    except asyncio.TimeoutError:
                        yield f"data: {heartbeat}\n\n"  # 心跳包
                        continue

                    if not result:
                        continue

                    result_text = result["data"]
                    type = result.get("type")
                    cid = result.get("cid")
                    streaming = result.get("streaming", False)
                    if cid != self.curr_user_cid.get(username):
                        # 丢弃
                        continue
                    yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.05)

                    if streaming and type != "end":
                        continue

                    if type == "update_title":
                        continue

                    if result_text:
                        conversation = self.db.get_conversation_by_user_id(
                            username, cid
                        )
                        try:
                            history = json.loads(conversation.history)
                        except BaseException as e:
                            logger.error(f"Failed to parse conversation history: {e}")
                            history = []
                        history.append({"type": "bot", "message": result_text})
                        self.db.update_conversation(
                            username, cid, history=json.dumps(history)
                        )
            except BaseException as _:
                logger.debug(f"用户 {username} 断开聊天长连接。")
                self.curr_chat_sse.pop(username)
                return

        response = await make_response(
            stream(),
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Transfer-Encoding": "chunked",
                "Connection": "keep-alive",
            },
        )
        response.timeout = None
        return response

    async def delete_conversation(self):
        username = g.get("username", "guest")
        conversation_id = request.args.get("conversation_id")
        if not conversation_id:
            return Response().error("Missing key: conversation_id").__dict__

        self.db.delete_conversation(username, conversation_id)
        return Response().ok().__dict__

    async def new_conversation(self):
        username = g.get("username", "guest")
        conversation_id = str(uuid.uuid4())
        self.db.new_conversation(username, conversation_id)
        return Response().ok(data={"conversation_id": conversation_id}).__dict__

    async def rename_conversation(self):
        username = g.get("username", "guest")
        post_data = await request.json
        if "conversation_id" not in post_data or "title" not in post_data:
            return Response().error("Missing key: conversation_id or title").__dict__

        conversation_id = post_data["conversation_id"]
        title = post_data["title"]

        self.db.update_conversation_title(username, conversation_id, title=title)
        return Response().ok(message="重命名成功！").__dict__

    async def get_conversations(self):
        username = g.get("username", "guest")
        conversations = self.db.get_conversations(username)
        return Response().ok(data=conversations).__dict__

    async def get_conversation(self):
        username = g.get("username", "guest")
        conversation_id = request.args.get("conversation_id")
        if not conversation_id:
            return Response().error("Missing key: conversation_id").__dict__

        conversation = self.db.get_conversation_by_user_id(username, conversation_id)

        self.curr_user_cid[username] = conversation_id

        return Response().ok(data=conversation).__dict__
