import asyncio
import json
from typing import Dict, Any, Optional, Awaitable

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import (
    AstrBotMessage,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSession
import astrbot.api.message_components as Comp

from .misskey_api import MisskeyAPI
from .misskey_event import MisskeyPlatformEvent
from .misskey_utils import (
    serialize_message_chain,
    resolve_message_visibility,
    is_valid_user_session_id,
    is_valid_room_session_id,
    add_at_mention_if_needed,
    process_files,
    extract_sender_info,
    create_base_message,
    process_at_mention,
    cache_user_info,
    cache_room_info,
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

        self.unique_session = platform_settings["unique_session"]

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
        connection_attempts = 0

        while self._running:
            try:
                connection_attempts += 1
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
                    logger.info(
                        f"[Misskey] WebSocket 已连接 (尝试 #{connection_attempts})"
                    )
                    connection_attempts = 0  # 重置计数器
                    await streaming.subscribe_channel("main")
                    if self.enable_chat:
                        await streaming.subscribe_channel("messaging")
                        await streaming.subscribe_channel("messagingIndex")
                        logger.info("[Misskey] 聊天频道已订阅")

                    backoff_delay = 1.0  # 重置延迟
                    await streaming.listen()
                else:
                    logger.error(
                        f"[Misskey] WebSocket 连接失败 (尝试 #{connection_attempts})"
                    )

            except Exception as e:
                logger.error(
                    f"[Misskey] WebSocket 异常 (尝试 #{connection_attempts}): {e}"
                )

            if self._running:
                logger.info(
                    f"[Misskey] {backoff_delay:.1f}秒后重连 (下次尝试 #{connection_attempts + 1})"
                )
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

            sender_id = str(
                data.get("fromUserId", "") or data.get("fromUser", {}).get("id", "")
            )
            if sender_id == self.client_self_id:
                return

            room_id = data.get("toRoomId")
            if room_id:
                raw_text = data.get("text", "")
                logger.debug(
                    f"[Misskey] 检查群聊消息: '{raw_text}', 机器人用户名: '{self._bot_username}'"
                )

                message = await self.convert_room_message(data)
                logger.info(f"[Misskey] 处理群聊消息: {message.message_str[:50]}...")
            else:
                message = await self.convert_chat_message(data)
                logger.info(f"[Misskey] 处理私聊消息: {message.message_str[:50]}...")

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
        self, session: MessageSession, message_chain: MessageChain
    ) -> Awaitable[Any]:
        if not self.api:
            logger.error("[Misskey] API 客户端未初始化")
            return await super().send_by_session(session, message_chain)

        try:
            session_id = session.session_id
            text, has_at_user = serialize_message_chain(message_chain.chain)

            if not has_at_user and session_id:
                user_info = self._user_cache.get(session_id)
                text = add_at_mention_if_needed(text, user_info, has_at_user)

            if not text or not text.strip():
                logger.warning("[Misskey] 消息内容为空，跳过发送")
                return await super().send_by_session(session, message_chain)

            if len(text) > self.max_message_length:
                text = text[: self.max_message_length] + "..."

            if session_id and is_valid_user_session_id(session_id):
                from .misskey_utils import extract_user_id_from_session_id

                user_id = extract_user_id_from_session_id(session_id)
                await self.api.send_message(user_id, text)
            elif session_id and is_valid_room_session_id(session_id):
                from .misskey_utils import extract_room_id_from_session_id

                room_id = extract_room_id_from_session_id(session_id)
                await self.api.send_room_message(room_id, text)
            else:
                visibility, visible_user_ids = resolve_message_visibility(
                    user_id=session_id,
                    user_cache=self._user_cache,
                    self_id=self.client_self_id,
                    default_visibility=self.default_visibility,
                )

                await self.api.create_note(
                    text,
                    visibility=visibility,
                    visible_user_ids=visible_user_ids,
                    local_only=self.local_only,
                )

        except Exception as e:
            logger.error(f"[Misskey] 发送消息失败: {e}")

        return await super().send_by_session(session, message_chain)

    async def convert_message(self, raw_data: Dict[str, Any]) -> AstrBotMessage:
        """将 Misskey 贴文数据转换为 AstrBotMessage 对象"""
        sender_info = extract_sender_info(raw_data, is_chat=False)
        message = create_base_message(
            raw_data,
            sender_info,
            self.client_self_id,
            is_chat=False,
            unique_session=self.unique_session,
        )
        cache_user_info(
            self._user_cache, sender_info, raw_data, self.client_self_id, is_chat=False
        )

        message_parts = []
        raw_text = raw_data.get("text", "")

        if raw_text:
            text_parts, processed_text = process_at_mention(
                message, raw_text, self._bot_username, self.client_self_id
            )
            message_parts.extend(text_parts)

        files = raw_data.get("files", [])
        file_parts = process_files(message, files)
        message_parts.extend(file_parts)

        message.message_str = (
            " ".join(part for part in message_parts if part.strip())
            if message_parts
            else ""
        )
        return message

    async def convert_chat_message(self, raw_data: Dict[str, Any]) -> AstrBotMessage:
        """将 Misskey 聊天消息数据转换为 AstrBotMessage 对象"""
        sender_info = extract_sender_info(raw_data, is_chat=True)
        message = create_base_message(
            raw_data,
            sender_info,
            self.client_self_id,
            is_chat=True,
            unique_session=self.unique_session,
        )
        cache_user_info(
            self._user_cache, sender_info, raw_data, self.client_self_id, is_chat=True
        )

        raw_text = raw_data.get("text", "")
        if raw_text:
            message.message.append(Comp.Plain(raw_text))

        files = raw_data.get("files", [])
        process_files(message, files, include_text_parts=False)

        message.message_str = raw_text if raw_text else ""
        return message

    async def convert_room_message(self, raw_data: Dict[str, Any]) -> AstrBotMessage:
        """将 Misskey 群聊消息数据转换为 AstrBotMessage 对象"""
        sender_info = extract_sender_info(raw_data, is_chat=True)
        room_id = raw_data.get("toRoomId", "")
        message = create_base_message(
            raw_data,
            sender_info,
            self.client_self_id,
            is_chat=False,
            room_id=room_id,
            unique_session=self.unique_session,
        )

        cache_user_info(
            self._user_cache, sender_info, raw_data, self.client_self_id, is_chat=False
        )
        cache_room_info(self._user_cache, raw_data, self.client_self_id)

        raw_text = raw_data.get("text", "")
        message_parts = []

        if raw_text:
            if self._bot_username and f"@{self._bot_username}" in raw_text:
                text_parts, processed_text = process_at_mention(
                    message, raw_text, self._bot_username, self.client_self_id
                )
                message_parts.extend(text_parts)
            else:
                message.message.append(Comp.Plain(raw_text))
                message_parts.append(raw_text)

        files = raw_data.get("files", [])
        file_parts = process_files(message, files)
        message_parts.extend(file_parts)

        message.message_str = (
            " ".join(part for part in message_parts if part.strip())
            if message_parts
            else ""
        )
        return message

    async def terminate(self):
        self._running = False
        if self.api:
            await self.api.close()

    def get_client(self) -> Any:
        return self.api
