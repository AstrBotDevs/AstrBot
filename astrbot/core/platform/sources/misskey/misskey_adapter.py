import asyncio
import json
import sys
import uuid
from typing import Any, Awaitable, Dict, Optional

import aiohttp
import websockets

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Reply
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core import logger
from astrbot.core.platform.astr_message_event import MessageSesion

from .misskey_event import MisskeyPlatformEvent

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


# Misskey 平台适配器的默认配置模板
DEFAULT_CONFIG_TEMPLATE = {
    "type": "misskey",
    "enable": False,
    "id": "misskey",
    "misskey_instance_url": "https://misskey.io",
    "misskey_access_token": "",
    "misskey_bot_account_name": "",
    "misskey_listen_channels": ["main", "home"],
    "misskey_listen_mentions": True,
    "misskey_listen_replies": True,
}


@register_platform_adapter(
    "misskey",
    "Misskey 平台适配器",
    default_config_tmpl=DEFAULT_CONFIG_TEMPLATE,
    adapter_display_name="Misskey",
)
class MisskeyPlatformAdapter(Platform):
    """Misskey 平台适配器

    支持连接到 Misskey 实例，监听提及和时间线事件，并发送回复。
    """

    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)
        self.config = platform_config
        self.settings = platform_settings
        self.unique_session = platform_settings.get("unique_session", False)

        # 配置信息
        self.instance_url = self.config.get(
            "misskey_instance_url", "https://misskey.io"
        )
        self.access_token = self.config.get("misskey_access_token", "")
        self.bot_account_name = self.config.get("misskey_bot_account_name", "")
        self.listen_channels = self.config.get(
            "misskey_listen_channels", ["main", "home"]
        )
        self.listen_mentions = self.config.get("misskey_listen_mentions", True)
        self.listen_replies = self.config.get("misskey_listen_replies", True)

        # 清理 URL，确保没有尾随斜杠
        if self.instance_url.endswith("/"):
            self.instance_url = self.instance_url[:-1]

        # WebSocket 连接相关
        self.websocket = None
        self.websocket_task = None
        self.running = False

        # 用户信息缓存
        self.bot_user_info = None

        self.metadata = PlatformMetadata(
            name="misskey",
            description="Misskey 平台适配器",
            id=self.config.get("id", "misskey"),
        )

    @override
    def meta(self) -> PlatformMetadata:
        return self.metadata

    @override
    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        """通过会话发送消息"""
        sending_event = MisskeyPlatformEvent(
            message_str="",
            message_obj=None,
            platform_meta=self.meta(),
            session_id=session.session_id,
            adapter=self,
        )
        await sending_event.send(message_chain)
        await super().send_by_session(session, message_chain)

    async def send_note(
        self, text: str, reply_id: Optional[str] = None, visibility: str = "public"
    ) -> Optional[Dict]:
        """发送 Misskey Note（帖子）

        Args:
            text: 消息文本
            reply_id: 回复的 Note ID（可选）
            visibility: 可见性（public, home, followers, specified）

        Returns:
            创建的 Note 信息，失败时返回 None
        """
        url = f"{self.instance_url}/api/notes/create"
        payload = {
            "i": self.access_token,
            "text": text,
            "visibility": visibility,
        }

        if reply_id:
            payload["replyId"] = reply_id

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.debug(
                            f"Note sent successfully: {result.get('createdNote', {}).get('id', 'unknown')}"
                        )
                        return result.get("createdNote")
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Failed to send note: {response.status} - {error_text}"
                        )
                        return None
        except Exception as e:
            logger.error(f"Error sending note: {e}")
            return None

    async def get_bot_user_info(self) -> Optional[Dict]:
        """获取机器人用户信息"""
        if self.bot_user_info:
            return self.bot_user_info

        url = f"{self.instance_url}/api/i"
        payload = {"i": self.access_token}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        self.bot_user_info = await response.json()
                        logger.info(
                            f"Bot user info retrieved: @{self.bot_user_info.get('username', 'unknown')}"
                        )
                        return self.bot_user_info
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Failed to get user info: {response.status} - {error_text}"
                        )
                        return None
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None

    async def connect_websocket(self):
        """连接到 Misskey WebSocket 流 API"""
        if not self.access_token:
            logger.error("Misskey access token is required")
            return

        # 首先获取用户信息
        await self.get_bot_user_info()
        if not self.bot_user_info:
            logger.error("Failed to get bot user information")
            return

        # 构建 WebSocket URL
        ws_url = self.instance_url.replace("https://", "wss://").replace(
            "http://", "ws://"
        )
        ws_url = f"{ws_url}/streaming"

        try:
            logger.info(f"Connecting to Misskey WebSocket: {ws_url}")
            self.websocket = await websockets.connect(ws_url)
            logger.info("Connected to Misskey WebSocket")

            # 连接到不同的频道
            for channel in self.listen_channels:
                await self.subscribe_to_channel(channel)

            # 监听 mentions 和 replies
            if self.listen_mentions:
                await self.subscribe_to_channel(
                    "main"
                )  # mentions usually come through main timeline

            # 开始监听消息
            await self.listen_messages()

        except websockets.exceptions.ConnectionClosed:
            logger.warning("Misskey WebSocket connection closed")
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
        finally:
            if self.websocket:
                await self.websocket.close()
                self.websocket = None

    async def subscribe_to_channel(self, channel_name: str):
        """订阅 Misskey 流频道"""
        if not self.websocket:
            return

        subscribe_message = {
            "type": "connect",
            "body": {
                "channel": channel_name,
                "id": str(uuid.uuid4()),
            },
        }

        if channel_name in ["main", "home"] and self.access_token:
            subscribe_message["body"]["params"] = {"i": self.access_token}

        try:
            await self.websocket.send(json.dumps(subscribe_message))
            logger.debug(f"Subscribed to channel: {channel_name}")
        except Exception as e:
            logger.error(f"Failed to subscribe to channel {channel_name}: {e}")

    async def listen_messages(self):
        """监听 WebSocket 消息"""
        if not self.websocket:
            return

        try:
            async for message in self.websocket:
                if not self.running:
                    break

                try:
                    data = json.loads(message)
                    await self.handle_websocket_message(data)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to decode WebSocket message: {message}")
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {e}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error in message listener: {e}")

    async def handle_websocket_message(self, data: Dict):
        """处理 WebSocket 消息"""
        message_type = data.get("type")
        body = data.get("body", {})

        if message_type == "channel":
            channel_type = body.get("type")
            channel_body = body.get("body", {})

            if channel_type == "note":
                await self.handle_note_event(channel_body)
            elif channel_type == "mention":
                await self.handle_mention_event(channel_body)

    async def handle_note_event(self, note_data: Dict):
        """处理 Note 事件"""
        # 检查是否是对机器人的提及或回复
        if not self.should_process_note(note_data):
            return

        try:
            abm = await self.convert_note_to_astrbot_message(note_data)
            if abm:
                await self.handle_message(abm, note_data)
        except Exception as e:
            logger.error(f"Error processing note event: {e}")

    async def handle_mention_event(self, mention_data: Dict):
        """处理提及事件"""
        try:
            abm = await self.convert_note_to_astrbot_message(mention_data)
            if abm:
                await self.handle_message(abm, mention_data)
        except Exception as e:
            logger.error(f"Error processing mention event: {e}")

    def should_process_note(self, note_data: Dict) -> bool:
        """判断是否应该处理这条 Note"""
        if not self.bot_user_info:
            return False

        bot_username = self.bot_user_info.get("username", "")
        bot_id = self.bot_user_info.get("id", "")

        # 忽略机器人自己发送的消息
        author = note_data.get("user", {})
        if author.get("id") == bot_id:
            return False

        # 检查是否是回复
        if self.listen_replies and note_data.get("replyId"):
            return True

        # 检查是否提及了机器人
        if self.listen_mentions:
            text = note_data.get("text", "")
            if f"@{bot_username}" in text:
                return True

        return False

    async def convert_note_to_astrbot_message(
        self, note_data: Dict
    ) -> Optional[AstrBotMessage]:
        """将 Misskey Note 转换为 AstrBot 消息"""
        try:
            user = note_data.get("user", {})
            text = note_data.get("text", "")
            note_id = note_data.get("id", "")

            if not text.strip():
                return None

            # 创建发送者信息
            sender = MessageMember(
                user_id=user.get("id", ""),
                nickname=user.get("name", user.get("username", "Unknown")),
                avatar_url=user.get("avatarUrl", ""),
            )

            # 创建消息
            abm = AstrBotMessage(
                type=MessageType.GROUP_MESSAGE,  # 将 Misskey 视为群聊
                message_str=text,
                sender=sender,
                message_id=note_id,
                group_id="misskey_timeline",  # 使用固定的群组ID
            )

            # 添加文本内容
            abm.message.append(Plain(text))

            # 处理回复
            reply_id = note_data.get("replyId")
            if reply_id:
                abm.message.insert(0, Reply(reply_id))

            # 设置会话ID
            if self.unique_session:
                abm.session_id = sender.user_id
            else:
                abm.session_id = "misskey_timeline"

            return abm

        except Exception as e:
            logger.error(f"Error converting note to AstrBot message: {e}")
            return None

    async def handle_message(self, abm: AstrBotMessage, original_note: Dict):
        """处理消息事件"""
        event = MisskeyPlatformEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            adapter=self,
        )

        # 设置原始 Note 数据，用于回复
        event.set_extra("original_note", original_note)

        self.commit_event(event)

    @override
    async def run(self) -> Awaitable[Any]:
        """运行 Misskey 适配器"""
        if not self.access_token:
            logger.error("Misskey access token is not configured")
            return

        logger.info("Starting Misskey Platform Adapter")
        self.running = True

        # 启动 WebSocket 连接
        self.websocket_task = asyncio.create_task(self.connect_websocket())

        try:
            await self.websocket_task
        except asyncio.CancelledError:
            logger.info("Misskey adapter task cancelled")
        except Exception as e:
            logger.error(f"Misskey adapter error: {e}")
        finally:
            self.running = False

    @override
    async def terminate(self):
        """终止适配器"""
        logger.info("Terminating Misskey Platform Adapter")
        self.running = False

        if self.websocket_task:
            self.websocket_task.cancel()
            try:
                await self.websocket_task
            except asyncio.CancelledError:
                pass

        if self.websocket:
            await self.websocket.close()
            self.websocket = None

    def get_client(self):
        """获取客户端对象"""
        return self
