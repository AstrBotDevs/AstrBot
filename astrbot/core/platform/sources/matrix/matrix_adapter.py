import asyncio
import sys
import re
from typing import Awaitable, Any
from nio import (
    AsyncClient,
    MatrixRoom,
    RoomMessageText,
    RoomMessageImage,
    RoomMessageFile,
)
from astrbot.api.platform import (
    Platform,
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Image, File
from astrbot.api import logger
from astrbot.core.platform.astr_message_event import MessageSesion
from .matrix_event import MatrixMessageEvent

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


@register_platform_adapter(
    "matrix",
    "Matrix 协议适配器 (支持 Element、VoceChat 等 Matrix 客户端)",
    {
        "homeserver": "https://matrix.org",
        "user_id": "",
        "access_token": "",
        "device_id": "",
        "store_path": "./data/matrix_store",
        "enable": False,
    },
)
class MatrixPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)
        self.config = platform_config
        self.settings = platform_settings
        self.unique_session = platform_settings.get("unique_session", False)

        # Matrix 配置
        self.homeserver = platform_config.get("homeserver", "https://matrix.org")
        self.user_id = platform_config.get("user_id", "")
        self.access_token = platform_config.get("access_token", "")
        self.device_id = platform_config.get("device_id", "ASTRBOT")
        self.store_path = platform_config.get("store_path", "./data/matrix_store")

        if not self.user_id or not self.access_token:
            raise ValueError("Matrix user_id 和 access_token 是必需的")

        # 初始化 Matrix 客户端
        self.client = AsyncClient(
            homeserver=self.homeserver,
            user=self.user_id,
            device_id=self.device_id,
            store_path=self.store_path,
        )
        self.client.access_token = self.access_token

        # 设置事件回调
        self.client.add_event_callback(self._handle_message, RoomMessageText)
        self.client.add_event_callback(self._handle_image, RoomMessageImage)
        self.client.add_event_callback(self._handle_file, RoomMessageFile)

        self.client_self_id = self.user_id
        logger.info(f"Matrix 适配器初始化完成: {self.user_id} @ {self.homeserver}")

    @override
    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="matrix",
            description="Matrix 协议适配器 (支持 Element、VoceChat 等 Matrix 客户端)",
            id=self.config.get("id", "matrix"),
        )

    @override
    async def run(self) -> Awaitable[Any]:
        """启动 Matrix 客户端"""
        try:
            logger.info("正在启动 Matrix 客户端...")

            # 同步消息历史
            await self.client.sync()
            logger.info("Matrix 客户端同步完成")

            # 开始监听事件
            await self.client.sync_forever(timeout=30000)

        except Exception as e:
            logger.error(f"Matrix 客户端运行出错: {e}")
            raise

    async def terminate(self):
        """关闭 Matrix 客户端"""
        try:
            await self.client.close()
            logger.info("Matrix 客户端已关闭")
        except Exception as e:
            logger.error(f"Matrix 客户端关闭出错: {e}")

    @override
    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        """通过会话发送消息"""
        room_id = session.session_id

        if not room_id:
            logger.error("Matrix 会话缺少房间 ID")
            return

        for message_component in message_chain:
            try:
                if isinstance(message_component, Plain):
                    await self.client.room_send(
                        room_id=room_id,
                        message_type="m.room.message",
                        content={
                            "msgtype": "m.text",
                            "body": message_component.text,
                        },
                    )

                elif isinstance(message_component, Image):
                    # 处理图片发送
                    await self._send_image(room_id, message_component)

                elif isinstance(message_component, File):
                    # 处理文件发送
                    await self._send_file(room_id, message_component)

            except Exception as e:
                logger.error(f"Matrix 消息发送失败: {e}")

    async def _send_image(self, room_id: str, image_component: Image):
        """发送图片消息"""
        try:
            image_path = image_component.file or image_component.url
            if not image_path:
                logger.error("Matrix 图片消息缺少文件路径或URL")
                return

            # 这里简化处理，实际应该上传图片并获取 MXC URI
            await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": f"[图片] {image_component.filename or 'image'}",
                },
            )
        except Exception as e:
            logger.error(f"Matrix 图片发送失败: {e}")

    async def _send_file(self, room_id: str, file_component: File):
        """发送文件消息"""
        try:
            # 这里简化处理，实际应该上传文件并获取 MXC URI
            await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": f"[文件] {file_component.name}",
                },
            )
        except Exception as e:
            logger.error(f"Matrix 文件发送失败: {e}")

    def get_client(self):
        """获取 Matrix 客户端"""
        return self.client

    async def _handle_message(self, room: MatrixRoom, event: RoomMessageText):
        """处理文本消息"""
        if event.sender == self.user_id:
            return  # 忽略自己发送的消息

        try:
            message_content = event.body

            # 处理 @机器人
            if self.user_id in message_content:
                # 移除 @机器人 部分
                message_content = re.sub(
                    r"@[\w\-\.]+:[\w\-\.]+", "", message_content
                ).strip()

            abm = AstrBotMessage()
            abm.type = (
                MessageType.GROUP_MESSAGE
                if room.member_count > 2
                else MessageType.PRIVATE_MESSAGE
            )
            abm.group_id = (
                room.room_id if abm.type == MessageType.GROUP_MESSAGE else None
            )
            abm.message_str = message_content
            abm.sender = MessageMember(
                user_id=event.sender, nickname=room.user_name(event.sender)
            )
            abm.message = [Plain(text=message_content)]
            abm.raw_message = event
            abm.self_id = self.client_self_id
            abm.session_id = room.room_id
            abm.message_id = event.event_id

            # 创建事件并提交
            matrix_event = MatrixMessageEvent(
                message_str=message_content,
                message_obj=abm,
                platform_meta=self.meta(),
                session_id=room.room_id,
                client=self.client,
                room_id=room.room_id,
                event_id=event.event_id,
            )

            self.commit_event(matrix_event)
            logger.debug(f"Matrix 消息处理完成: {message_content[:100]}...")

        except Exception as e:
            logger.error(f"Matrix 消息处理失败: {e}")

    async def _handle_image(self, room: MatrixRoom, event: RoomMessageImage):
        """处理图片消息"""
        if event.sender == self.user_id:
            return

        try:
            abm = AstrBotMessage()
            abm.type = (
                MessageType.GROUP_MESSAGE
                if room.member_count > 2
                else MessageType.PRIVATE_MESSAGE
            )
            abm.group_id = (
                room.room_id if abm.type == MessageType.GROUP_MESSAGE else None
            )
            abm.message_str = f"[图片] {event.body}"
            abm.sender = MessageMember(
                user_id=event.sender, nickname=room.user_name(event.sender)
            )

            # 构建消息组件
            message_chain = [Plain(text=f"[图片] {event.body}")]
            if hasattr(event, "url") and event.url:
                message_chain.append(Image(url=event.url, filename=event.body))

            abm.message = message_chain
            abm.raw_message = event
            abm.self_id = self.client_self_id
            abm.session_id = room.room_id
            abm.message_id = event.event_id

            # 创建事件并提交
            matrix_event = MatrixMessageEvent(
                message_str=abm.message_str,
                message_obj=abm,
                platform_meta=self.meta(),
                session_id=room.room_id,
                client=self.client,
                room_id=room.room_id,
                event_id=event.event_id,
            )

            self.commit_event(matrix_event)
            logger.debug(f"Matrix 图片消息处理完成: {event.body}")

        except Exception as e:
            logger.error(f"Matrix 图片消息处理失败: {e}")

    async def _handle_file(self, room: MatrixRoom, event: RoomMessageFile):
        """处理文件消息"""
        if event.sender == self.user_id:
            return

        try:
            abm = AstrBotMessage()
            abm.type = (
                MessageType.GROUP_MESSAGE
                if room.member_count > 2
                else MessageType.PRIVATE_MESSAGE
            )
            abm.group_id = (
                room.room_id if abm.type == MessageType.GROUP_MESSAGE else None
            )
            abm.message_str = f"[文件] {event.body}"
            abm.sender = MessageMember(
                user_id=event.sender, nickname=room.user_name(event.sender)
            )

            # 构建消息组件
            message_chain = [Plain(text=f"[文件] {event.body}")]
            if hasattr(event, "url") and event.url:
                message_chain.append(File(name=event.body, url=event.url))

            abm.message = message_chain
            abm.raw_message = event
            abm.self_id = self.client_self_id
            abm.session_id = room.room_id
            abm.message_id = event.event_id

            # 创建事件并提交
            matrix_event = MatrixMessageEvent(
                message_str=abm.message_str,
                message_obj=abm,
                platform_meta=self.meta(),
                session_id=room.room_id,
                client=self.client,
                room_id=room.room_id,
                event_id=event.event_id,
            )

            self.commit_event(matrix_event)
            logger.debug(f"Matrix 文件消息处理完成: {event.body}")

        except Exception as e:
            logger.error(f"Matrix 文件消息处理失败: {e}")
