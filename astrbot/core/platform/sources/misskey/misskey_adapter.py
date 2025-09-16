import asyncio
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


def _serialize_message_chain(chain):
    """将消息链序列化为文本字符串"""
    text_parts = []
    has_at = False

    for component in chain:
        if isinstance(component, Comp.Plain):
            text_parts.append(component.text)
        elif isinstance(component, Comp.Image):
            text_parts.append("[图片]")
        elif isinstance(component, Comp.Node):
            if component.content:
                for node_comp in component.content:
                    if isinstance(node_comp, Comp.Plain):
                        text_parts.append(node_comp.text)
                    elif isinstance(node_comp, Comp.Image):
                        text_parts.append("[图片]")
                    else:
                        text_parts.append(str(node_comp))
        elif isinstance(component, Comp.At):
            has_at = True
            text_parts.append(f"@{component.qq}")
        else:
            text_parts.append(str(component))

    return "".join(text_parts), has_at


def _resolve_visibility(user_id, user_cache, self_id):
    """解析 Misskey 消息的可见性设置"""
    visibility = "public"
    visible_user_ids = None

    if user_id:
        user_info = user_cache.get(user_id)
        if user_info:
            original_visibility = user_info.get("visibility", "public")
            if original_visibility == "specified":
                visibility = "specified"
                original_visible_users = user_info.get("visible_user_ids", [])
                users_to_include = [user_id]
                if self_id:
                    users_to_include.append(self_id)
                visible_user_ids = list(set(original_visible_users + users_to_include))
                visible_user_ids = [uid for uid in visible_user_ids if uid]
            else:
                visibility = original_visibility

    return visibility, visible_user_ids


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
        self.poll_interval = self.config.get("poll_interval", 5.0)
        self.max_message_length = self.config.get("max_message_length", 3000)

        self.api: Optional[MisskeyAPI] = None
        self._running = False
        self.last_notification_id = None
        self.client_self_id = ""
        self._bot_username = ""
        self._user_cache = {}

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="misskey",
            description="Misskey 平台适配器",
            id=self.config.get("id"),
            default_config_tmpl=self.config,
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
                f"[Misskey] 用户: {user_info.get('username', '')} (ID: {self.client_self_id})"
            )
        except Exception as e:
            logger.error(f"[Misskey] 获取用户信息失败: {e}")
            return

        await self._start_polling()

    async def _start_polling(self):
        if not self.api:
            logger.error("[Misskey] API 客户端未初始化，无法开始轮询")
            return

        # 指数退避参数
        initial_backoff = 1  # 秒
        max_backoff = 60  # 秒
        backoff_multiplier = 2
        current_backoff = initial_backoff

        is_first_poll = True

        try:
            latest_notifications = await self.api.get_mentions(limit=1)
            if latest_notifications:
                self.last_notification_id = latest_notifications[0].get("id")
                logger.debug(f"[Misskey] 起始通知 ID: {self.last_notification_id}")
        except Exception as e:
            logger.warning(f"[Misskey] 获取起始通知失败: {e}")

        while self._running:
            if not self.api:
                logger.error("[Misskey] API 客户端在轮询过程中变为 None")
                break

            try:
                notifications = await self.api.get_mentions(
                    limit=20, since_id=self.last_notification_id
                )

                # 重置退避时间
                current_backoff = initial_backoff

                if notifications:
                    if is_first_poll:
                        logger.debug(f"[Misskey] 跳过 {len(notifications)} 条历史通知")
                        is_first_poll = False
                        self.last_notification_id = notifications[0].get("id")
                    else:
                        notifications.reverse()
                        for notification in notifications:
                            await self._process_notification(notification)
                        self.last_notification_id = notifications[0].get("id")
                elif is_first_poll:
                    is_first_poll = False
                    logger.info("[Misskey] 开始监听新消息")

                await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.warning(f"[Misskey] 获取通知失败: {e}")
                logger.info(
                    f"[Misskey] 轮询将在 {current_backoff} 秒后重试（指数退避）"
                )
                await asyncio.sleep(current_backoff)
                current_backoff = min(current_backoff * backoff_multiplier, max_backoff)

    async def _process_notification(self, notification: Dict[str, Any]):
        notification_type = notification.get("type")

        if notification_type not in ["mention", "reply", "quote"]:
            return

        note = notification.get("note")
        if not note or not self._is_bot_mentioned(note):
            return

        message = await self.convert_message(note)
        event = MisskeyPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.api,
        )
        self.commit_event(event)

    def _is_bot_mentioned(self, note: Dict[str, Any]) -> bool:
        text = note.get("text", "")
        if not text:
            return False

        bot_user_id = self.client_self_id

        if self._bot_username and f"@{self._bot_username}" in text:
            return True

        reply_id = note.get("replyId")
        mentions = note.get("mentions", [])

        if not reply_id:
            return bot_user_id in [str(uid) for uid in mentions]

        reply = note.get("reply")
        if reply and isinstance(reply, dict):
            reply_user_id = str(reply.get("user", {}).get("id", ""))
            if reply_user_id == str(bot_user_id):
                return bool(self._bot_username and f"@{self._bot_username}" in text)
            else:
                return bot_user_id in [str(uid) for uid in mentions]

        return False

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ) -> Awaitable[Any]:
        if not self.api:
            logger.error("[Misskey] API 客户端未初始化")
            return super().send_by_session(session, message_chain)

        try:
            # 解析session信息 - 现在session_id就是用户ID
            session_id = session.session_id
            user_id = session_id  # 直接使用session_id作为用户ID

            text, has_at_user = _serialize_message_chain(message_chain.chain)

            # 如果没有@用户，添加@用户
            if not has_at_user and user_id:
                user_info = self._user_cache.get(user_id)
                if user_info:
                    username = user_info.get("username")
                    nickname = user_info.get("nickname")
                    if username:
                        text = f"@{username} {text}".strip()
                    elif nickname:
                        text = f"@{nickname} {text}".strip()

            if not text or not text.strip():
                logger.warning("[Misskey] 消息内容为空，跳过发送")
                return await super().send_by_session(session, message_chain)

            if len(text) > self.max_message_length:
                text = text[: self.max_message_length] + "..."

            visibility, visible_user_ids = _resolve_visibility(
                user_id=user_id,
                user_cache=self._user_cache,
                self_id=self.client_self_id,
            )

            # 发送消息
            if user_id and self._is_user_session(user_id):
                await self.api.send_message(user_id, text)
            else:
                await self.api.create_note(
                    text, visibility=visibility, visible_user_ids=visible_user_ids
                )

        except Exception as e:
            logger.error(f"[Misskey] 发送消息失败: {e}")

        return await super().send_by_session(session, message_chain)

    def _is_user_session(self, session_id: str) -> bool:
        return 5 <= len(session_id) <= 64 and " " not in session_id

    async def convert_message(self, raw_data: Dict[str, Any]) -> AstrBotMessage:
        message = AstrBotMessage()
        message.raw_message = raw_data
        message.message_str = raw_data.get("text", "")
        message.message = []

        sender = raw_data.get("user", {})
        sender_username = sender.get("username", "")
        message.sender = MessageMember(
            user_id=str(sender.get("id", "")),
            nickname=sender.get("name", sender.get("username", "")),
        )

        user_id = message.sender.user_id
        message_id = str(raw_data.get("id", ""))
        # 使用 AstrBot 标准的会话ID格式: platform_name:message_type:session_id
        message.session_id = user_id  # 使用用户ID作为基础session_id
        message.message_id = message_id
        message.self_id = self.client_self_id
        message.type = MessageType.FRIEND_MESSAGE

        self._user_cache[user_id] = {
            "username": sender_username,
            "nickname": message.sender.nickname,
            "visibility": raw_data.get("visibility", "public"),
            "visible_user_ids": raw_data.get("visibleUserIds", []),
        }

        raw_text = message.message_str
        if raw_text:
            if self._bot_username:
                at_mention = f"@{self._bot_username}"
                if raw_text.startswith(at_mention):
                    message.message.append(Comp.At(qq=self.client_self_id))
                    remaining_text = raw_text[len(at_mention) :].strip()
                    message.message_str = remaining_text
                    if remaining_text:
                        message.message.append(Comp.Plain(remaining_text))
                    return message

            message.message.append(Comp.Plain(raw_text))

        # 处理文件附件
        files = raw_data.get("files", [])
        if files:
            for file_info in files:
                file_type = file_info.get("type", "").lower()
                file_url = file_info.get("url", "")
                file_name = file_info.get("name", "未知文件")

                if file_type.startswith("image/"):
                    # 图片文件
                    message.message.append(Comp.Image(file_url))
                else:
                    # 其他文件类型，作为纯文本描述
                    message.message.append(Comp.Plain(f"[文件: {file_name}]"))

        return message

    async def terminate(self):
        logger.info("[Misskey] 终止适配器")
        self._running = False
        if self.api:
            await self.api.close()

    def get_client(self) -> Any:
        return self.api
