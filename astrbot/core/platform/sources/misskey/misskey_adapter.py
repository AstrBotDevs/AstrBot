import asyncio
import json
from typing import Dict, Any, Optional, Awaitable

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSesion
import astrbot.api.message_components as Comp

from .misskey_api import MisskeyAPI
from .misskey_event import MisskeyPlatformEvent
from .misskey_utils import (
    serialize_message_chain,
    resolve_message_visibility,
    is_valid_user_session_id,
    add_at_mention_if_needed,
)


@register_platform_adapter("misskey", "Misskey 平台适配器")
class MisskeyPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)
        self.config = platform_config or {}
        self.settings = platform_settings or {}
        self.instance_url = self.config.get("misskey_instance_url", "")
        self.access_token = self.config.get("misskey_token", "")
        self.max_message_length = self.config.get("max_message_length", 3000)
        self.default_visibility = self.config.get(
            "misskey_default_visibility", "public"
        )
        self.local_only = self.config.get("misskey_local_only", False)
        self.enable_chat = self.config.get("misskey_enable_chat", True)

        self.api: Optional[MisskeyAPI] = None
        self._running = False
        self.client_self_id = ""
        self._bot_username = ""
        self._user_cache = {}

    def meta(self) -> PlatformMetadata:
        default_config = {
            "misskey_instance_url": "",
            "misskey_token": "",
            "max_message_length": 3000,
            "misskey_default_visibility": "public",
            "misskey_local_only": False,
            "misskey_enable_chat": True,
        }
        default_config.update(self.config)

        return PlatformMetadata(
            name="misskey",
            description="Misskey 平台适配器",
            id=self.config.get("id", "misskey"),
            default_config_tmpl=default_config,
        )

    async def run(self):
        if not self.instance_url or not self.access_token:
            logger.error("[Misskey] 配置不完整，无法启动")
            return

        self.api = MisskeyAPI(self.instance_url, self.access_token)
        self._running = True

        try:
            user_info = await self.api.get_current_user()
            self.client_self_id = str(user_info.get("id", ""))
            self._bot_username = user_info.get("username", "")
            logger.info(
                f"[Misskey] 已连接用户: {self._bot_username} (ID: {self.client_self_id})"
            )
        except Exception as e:
            logger.error(f"[Misskey] 获取用户信息失败: {e}")
            self._running = False
            return

        await self._start_websocket_connection()

    async def _start_websocket_connection(self):
        backoff_delay = 1.0
        max_backoff = 300.0
        backoff_multiplier = 1.5

        while self._running:
            try:
                if not self.api:
                    logger.error("[Misskey] API 客户端未初始化")
                    break

                streaming = self.api.get_streaming_client()
                streaming.add_message_handler("notification", self._handle_notification)
                if self.enable_chat:
                    streaming.add_message_handler(
                        "newChatMessage", self._handle_chat_message
                    )
                    streaming.add_message_handler("_debug", self._debug_handler)

                if await streaming.connect():
                    logger.info("[Misskey] WebSocket 已连接")
                    await streaming.subscribe_channel("main")
                    if self.enable_chat:
                        await streaming.subscribe_channel("messaging")
                        await streaming.subscribe_channel("messagingIndex")
                        logger.info("[Misskey] 聊天频道已订阅")

                    backoff_delay = 1.0
                    await streaming.listen()
                else:
                    logger.error("[Misskey] WebSocket 连接失败")

            except Exception as e:
                logger.error(f"[Misskey] WebSocket 异常: {e}")

            if self._running:
                logger.info(f"[Misskey] {backoff_delay:.1f}秒后重连")
                await asyncio.sleep(backoff_delay)
                backoff_delay = min(backoff_delay * backoff_multiplier, max_backoff)

    async def _handle_notification(self, data: Dict[str, Any]):
        try:
            logger.debug(
                f"[Misskey] 收到通知事件:\n{json.dumps(data, indent=2, ensure_ascii=False)}"
            )
            notification_type = data.get("type")
            if notification_type in ["mention", "reply", "quote"]:
                note = data.get("note")
                if note and self._is_bot_mentioned(note):
                    logger.info(
                        f"[Misskey] 处理贴文提及: {note.get('text', '')[:50]}..."
                    )
                    message = await self.convert_message(note)
                    event = MisskeyPlatformEvent(
                        message_str=message.message_str,
                        message_obj=message,
                        platform_meta=self.meta(),
                        session_id=message.session_id,
                        client=self.api,
                    )
                    self.commit_event(event)
        except Exception as e:
            logger.error(f"[Misskey] 处理通知失败: {e}")

    async def _handle_chat_message(self, data: Dict[str, Any]):
        try:
            logger.debug(
                f"[Misskey] 收到聊天事件数据:\n{json.dumps(data, indent=2, ensure_ascii=False)}"
            )
            sender_id = str(data.get("user", {}).get("id", ""))
            if sender_id == self.client_self_id:
                return

            message = await self.convert_chat_message(data)
            logger.info(f"[Misskey] 处理聊天消息: {message.message_str[:50]}...")
            event = MisskeyPlatformEvent(
                message_str=message.message_str,
                message_obj=message,
                platform_meta=self.meta(),
                session_id=message.session_id,
                client=self.api,
            )
            self.commit_event(event)
        except Exception as e:
            logger.error(f"[Misskey] 处理聊天消息失败: {e}")

    async def _debug_handler(self, data: Dict[str, Any]):
        logger.debug(
            f"[Misskey] 收到未处理事件:\n{json.dumps(data, indent=2, ensure_ascii=False)}"
        )

    def _is_bot_mentioned(self, note: Dict[str, Any]) -> bool:
        text = note.get("text", "")
        if not text:
            return False

        mentions = note.get("mentions", [])
        if self._bot_username and f"@{self._bot_username}" in text:
            return True
        if self.client_self_id in [str(uid) for uid in mentions]:
            return True

        reply = note.get("reply")
        if reply and isinstance(reply, dict):
            reply_user_id = str(reply.get("user", {}).get("id", ""))
            if reply_user_id == self.client_self_id:
                return bool(self._bot_username and f"@{self._bot_username}" in text)

        return False

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ) -> Awaitable[Any]:
        if not self.api:
            logger.error("[Misskey] API 客户端未初始化")
            return await super().send_by_session(session, message_chain)

        try:
            user_id = session.session_id
            text, has_at_user = serialize_message_chain(message_chain.chain)

            if not has_at_user and user_id:
                user_info = self._user_cache.get(user_id)
                text = add_at_mention_if_needed(text, user_info, has_at_user)

            if not text or not text.strip():
                logger.warning("[Misskey] 消息内容为空，跳过发送")
                return await super().send_by_session(session, message_chain)

            if len(text) > self.max_message_length:
                text = text[: self.max_message_length] + "..."

            visibility, visible_user_ids = resolve_message_visibility(
                user_id=user_id,
                user_cache=self._user_cache,
                self_id=self.client_self_id,
                default_visibility=self.default_visibility,
            )

            if user_id and is_valid_user_session_id(user_id):
                await self.api.send_message(user_id, text)
            else:
                await self.api.create_note(
                    text,
                    visibility=visibility,
                    visible_user_ids=visible_user_ids,
                    local_only=self.local_only,
                )

        except Exception as e:
            logger.error(f"[Misskey] 发送消息失败: {e}")

        return await super().send_by_session(session, message_chain)

    def _create_file_component(self, file_info: Dict[str, Any]):
        """创建文件组件和描述文本"""
        file_url = file_info.get("url", "")
        file_name = file_info.get("name", "未知文件")
        file_type = file_info.get("type", "")

        if file_type.startswith("image/"):
            return Comp.Image(url=file_url, file=file_name), f"图片[{file_name}]"
        elif file_type.startswith("audio/"):
            return Comp.Record(url=file_url, file=file_name), f"音频[{file_name}]"
        elif file_type.startswith("video/"):
            return Comp.Video(url=file_url, file=file_name), f"视频[{file_name}]"
        else:
            return Comp.File(name=file_name, url=file_url), f"文件[{file_name}]"

    def _extract_sender_info(self, raw_data: Dict[str, Any], is_chat: bool = False):
        """提取发送者信息"""
        if is_chat:
            sender = raw_data.get("fromUser", {})
            sender_id = str(sender.get("id", "") or raw_data.get("fromUserId", ""))
        else:
            sender = raw_data.get("user", {})
            sender_id = str(sender.get("id", ""))

        return {
            "sender": sender,
            "sender_id": sender_id,
            "nickname": sender.get("name", sender.get("username", "")),
            "username": sender.get("username", ""),
        }

    def _create_base_message(
        self,
        raw_data: Dict[str, Any],
        sender_info: Dict[str, Any],
        is_chat: bool = False,
    ) -> AstrBotMessage:
        """创建基础消息对象"""
        message = AstrBotMessage()
        message.raw_message = raw_data
        message.message = []

        message.sender = MessageMember(
            user_id=sender_info["sender_id"],
            nickname=sender_info["nickname"],
        )

        session_prefix = "chat" if is_chat else "note"
        message.session_id = (
            f"{session_prefix}:{sender_info['sender_id']}"
            if sender_info["sender_id"]
            else f"{session_prefix}:unknown"
        )

        message.message_id = str(raw_data.get("id", ""))
        message.self_id = self.client_self_id
        message.type = MessageType.FRIEND_MESSAGE

        return message

    def _cache_user_info(
        self,
        sender_info: Dict[str, Any],
        raw_data: Dict[str, Any],
        is_chat: bool = False,
    ):
        """缓存用户信息"""
        if is_chat:
            user_cache_data = {
                "username": sender_info["username"],
                "nickname": sender_info["nickname"],
                "visibility": "specified",
                "visible_user_ids": [self.client_self_id, sender_info["sender_id"]],
            }
        else:
            user_cache_data = {
                "username": sender_info["username"],
                "nickname": sender_info["nickname"],
                "visibility": raw_data.get("visibility", "public"),
                "visible_user_ids": raw_data.get("visibleUserIds", []),
            }

        self._user_cache[sender_info["sender_id"]] = user_cache_data

    async def convert_message(self, raw_data: Dict[str, Any]) -> AstrBotMessage:
        """转换贴文消息"""
        sender_info = self._extract_sender_info(raw_data, is_chat=False)
        message = self._create_base_message(raw_data, sender_info, is_chat=False)
        self._cache_user_info(sender_info, raw_data, is_chat=False)

        message_parts = []
        raw_text = raw_data.get("text", "")

        if raw_text:
            if self._bot_username and raw_text.startswith(f"@{self._bot_username}"):
                at_mention = f"@{self._bot_username}"
                message.message.append(Comp.At(qq=self.client_self_id))
                remaining_text = raw_text[len(at_mention) :].strip()
                if remaining_text:
                    message.message.append(Comp.Plain(remaining_text))
                    message_parts.append(remaining_text)
            else:
                message.message.append(Comp.Plain(raw_text))
                message_parts.append(raw_text)

        files = raw_data.get("files", [])
        if files:
            for file_info in files:
                component, part_text = self._create_file_component(file_info)
                message.message.append(component)
                message_parts.append(part_text)

        message.message_str = (
            " ".join(part for part in message_parts if part.strip())
            if message_parts
            else ""
        )
        return message

    async def convert_chat_message(self, raw_data: Dict[str, Any]) -> AstrBotMessage:
        """转换聊天消息"""
        sender_info = self._extract_sender_info(raw_data, is_chat=True)
        message = self._create_base_message(raw_data, sender_info, is_chat=True)
        self._cache_user_info(sender_info, raw_data, is_chat=True)

        raw_text = raw_data.get("text", "")
        if raw_text:
            message.message.append(Comp.Plain(raw_text))

        files = raw_data.get("files", [])
        if files:
            for file_info in files:
                component, _ = self._create_file_component(file_info)
                message.message.append(component)

        message.message_str = raw_text if raw_text else ""
        return message

    async def terminate(self):
        self._running = False
        if self.api:
            await self.api.close()

    def get_client(self) -> Any:
        return self.api
