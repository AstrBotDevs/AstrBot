import uuid
import json
import os
from .route import Route, Response, RouteContext
from astrbot.core.platform.sources.webchat.webchat_queue_mgr import webchat_queue_mgr
from quart import request, Response as QuartResponse, g, make_response
from astrbot.core.db import BaseDatabase
import asyncio
from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.platform.astr_message_event import MessageSession


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
            "/chat/new_conversation": ("GET", self.new_conversation),
            "/chat/conversations": ("GET", self.get_conversations),
            "/chat/get_conversation": ("GET", self.get_conversation),
            "/chat/delete_conversation": ("GET", self.delete_conversation),
            "/chat/rename_conversation": ("POST", self.rename_conversation),
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
        selected_provider = post_data.get("selected_provider")
        selected_model = post_data.get("selected_model")
        if not message and not image_url and not audio_url:
            return (
                Response()
                .error("Message and image_url and audio_url are empty")
                .__dict__
            )
        if not conversation_id:
            return Response().error("conversation_id is empty").__dict__

        # append user message
        webchat_conv_id = await self._get_webchat_conv_id_from_conv_id(conversation_id)

        # Get conversation-specific queues
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
            try:
                while True:
                    try:
                        result = await asyncio.wait_for(back_queue.get(), timeout=10)
                    except asyncio.TimeoutError:
                        continue

                    if not result:
                        continue

                    result_text = result["data"]
                    type = result.get("type")
                    streaming = result.get("streaming", False)
                    yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.05)

                    if type == "end":
                        break
                    elif (streaming and type == "complete") or not streaming:
                        # append bot message
                        new_his = {"type": "bot", "message": result_text}
                        await self.platform_history_mgr.insert(
                            platform_id="webchat",
                            user_id=webchat_conv_id,
                            content=new_his,
                            sender_id="bot",
                            sender_name="bot",
                        )

            except BaseException as _:
                logger.debug(f"用户 {username} 断开聊天长连接。")
                return

        # Put message to conversation-specific queue
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
                },
            )
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
        return response

    async def _get_webchat_conv_id_from_conv_id(self, conversation_id: str) -> str:
        """从对话 ID 中提取 WebChat 会话 ID

        NOTE: 关于这里为什么要单独做一个 WebChat 的 Conversation ID 出来，这个是为了向前兼容。
        """
        conversation = await self.conv_mgr.get_conversation(
            unified_msg_origin="webchat", conversation_id=conversation_id
        )
        if not conversation:
            raise ValueError(f"Conversation with ID {conversation_id} not found.")
        conv_user_id = conversation.user_id
        webchat_session_id = MessageSession.from_str(conv_user_id).session_id
        if "!" not in webchat_session_id:
            raise ValueError(f"Invalid conv user ID: {conv_user_id}")
        return webchat_session_id.split("!")[-1]

    async def delete_conversation(self):
        conversation_id = request.args.get("conversation_id")
        if not conversation_id:
            return Response().error("Missing key: conversation_id").__dict__
        username = g.get("username", "guest")

        # Clean up queues when deleting conversation
        webchat_queue_mgr.remove_queues(conversation_id)
        webchat_conv_id = await self._get_webchat_conv_id_from_conv_id(conversation_id)
        await self.conv_mgr.delete_conversation(
            unified_msg_origin=f"webchat:FriendMessage:webchat!{username}!{webchat_conv_id}",
            conversation_id=conversation_id,
        )
        await self.platform_history_mgr.delete(
            platform_id="webchat", user_id=webchat_conv_id, offset_sec=99999999
        )
        return Response().ok().__dict__

    async def new_conversation(self):
        username = g.get("username", "guest")
        webchat_conv_id = str(uuid.uuid4())
        conv_id = await self.conv_mgr.new_conversation(
            unified_msg_origin=f"webchat:FriendMessage:webchat!{username}!{webchat_conv_id}",
            platform_id="webchat",
            content=[],
        )
        return Response().ok(data={"conversation_id": conv_id}).__dict__

    async def rename_conversation(self):
        post_data = await request.json
        if "conversation_id" not in post_data or "title" not in post_data:
            return Response().error("Missing key: conversation_id or title").__dict__

        conversation_id = post_data["conversation_id"]
        title = post_data["title"]

        await self.conv_mgr.update_conversation(
            unified_msg_origin="webchat",  # fake
            conversation_id=conversation_id,
            title=title,
        )
        return Response().ok(message="重命名成功！").__dict__

    async def get_conversations(self):
        conversations = await self.conv_mgr.get_conversations(platform_id="webchat")
        # remove content
        conversations_ = []
        for conv in conversations:
            conv.history = None
            conversations_.append(conv)
        return Response().ok(data=conversations_).__dict__

    async def get_conversation(self):
        conversation_id = request.args.get("conversation_id")
        if not conversation_id:
            return Response().error("Missing key: conversation_id").__dict__

        webchat_conv_id = await self._get_webchat_conv_id_from_conv_id(conversation_id)

        # Get platform message history
        history_ls = await self.platform_history_mgr.get(
            platform_id="webchat", user_id=webchat_conv_id, page=1, page_size=1000
        )

        history_res = [history.model_dump() for history in history_ls]

        return (
            Response()
            .ok(
                data={
                    "history": history_res,
                }
            )
            .__dict__
        )
