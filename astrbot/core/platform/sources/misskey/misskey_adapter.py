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
            id=self.config.get("id", "misskey"),
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
            self._running = False
            return

        await self._start_polling()

    async def _start_polling(self):
        if not self.api:
            logger.error("[Misskey] API 客户端未初始化，无法开始轮询")
            return

        initial_backoff = 1
        max_backoff = 60
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

                current_backoff = initial_backoff
                await self._process_notifications(notifications, is_first_poll)
                is_first_poll = False

                await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.warning(f"[Misskey] 轮询失败: {e}")
                logger.info(f"[Misskey] 将在 {current_backoff} 秒后重试")
                await asyncio.sleep(current_backoff)
                current_backoff = min(current_backoff * backoff_multiplier, max_backoff)

    async def _process_notifications(self, notifications: list, is_first_poll: bool):
        if not notifications:
            if is_first_poll:
                logger.info("[Misskey] 开始监听新消息")
            return

        if is_first_poll:
            logger.debug(f"[Misskey] 跳过 {len(notifications)} 条历史通知")
            self.last_notification_id = notifications[0].get("id")
        else:
            notifications.reverse()
            for notification in notifications:
                await self._process_notification(notification)
            self.last_notification_id = notifications[0].get("id")

    async def _process_notification(self, notification: Dict[str, Any]):
        try:
            notification_type = notification.get("type")
            if notification_type not in ["mention", "reply", "quote"]:
                return

            note = notification.get("note")
            if not note or not self._is_bot_mentioned(note):
                return

            message = await self.convert_message(note)
            logger.debug(
                f"[Misskey] 收到消息 - {message.sender.nickname}: {message.message_str}"
            )

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

    def _is_bot_mentioned(self, note: Dict[str, Any]) -> bool:
        """检查机器人是否被提及"""
        text = note.get("text", "")
        if not text:
            return False

        bot_user_id = self.client_self_id
        mentions = note.get("mentions", [])

        # 检查文本中是否直接@了机器人
        if self._bot_username and f"@{self._bot_username}" in text:
            return True

        # 检查是否在提及列表中
        if bot_user_id in [str(uid) for uid in mentions]:
            return True

        # 检查回复情况
        reply = note.get("reply")
        if reply and isinstance(reply, dict):
            reply_user_id = str(reply.get("user", {}).get("id", ""))
            # 如果回复的是机器人的消息，需要文本中有@机器人
            if reply_user_id == str(bot_user_id):
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
            )

            if user_id and is_valid_user_session_id(user_id):
                await self.api.send_message(user_id, text)
                logger.debug("[Misskey] 私信发送成功")
            else:
                await self.api.create_note(
                    text, visibility=visibility, visible_user_ids=visible_user_ids
                )
                logger.debug("[Misskey] 帖子发送成功")

        except Exception as e:
            logger.error(f"[Misskey] 发送消息失败: {e}")

        return await super().send_by_session(session, message_chain)

    def _create_file_component(self, file_info: Dict[str, Any]):
        """根据文件类型创建相应的消息组件"""
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

    async def convert_message(self, raw_data: Dict[str, Any]) -> AstrBotMessage:
        logger.debug(
            f"[Misskey] 接收到完整帖子数据:\n{json.dumps(raw_data, ensure_ascii=False, indent=2)}"
        )

        message = AstrBotMessage()
        message.raw_message = raw_data
        message.message = []

        sender = raw_data.get("user", {})
        message.sender = MessageMember(
            user_id=str(sender.get("id", "")),
            nickname=sender.get("name", sender.get("username", "")),
        )

        message.session_id = message.sender.user_id
        message.message_id = str(raw_data.get("id", ""))
        message.self_id = self.client_self_id
        message.type = MessageType.FRIEND_MESSAGE

        self._user_cache[message.sender.user_id] = {
            "username": sender.get("username", ""),
            "nickname": message.sender.nickname,
            "visibility": raw_data.get("visibility", "public"),
            "visible_user_ids": raw_data.get("visibleUserIds", []),
        }

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
            logger.debug(f"[Misskey] 检测到 {len(files)} 个附件")
            for i, file_info in enumerate(files):
                file_type = file_info.get("type", "")
                file_name = file_info.get("name", "未知文件")
                logger.debug(
                    f"[Misskey] 附件 {i + 1}: 名称={file_name}, 类型={file_type}"
                )

                component, part_text = self._create_file_component(file_info)
                message.message.append(component)
                message_parts.append(part_text)

        logger.debug(f"[Misskey] 最终消息组件数量: {len(message.message)}")
        for i, comp in enumerate(message.message):
            logger.debug(f"[Misskey] 组件 {i}: {type(comp).__name__} - {comp}")

        message.message_str = (
            " ".join(part for part in message_parts if part.strip())
            if message_parts
            else ""
        )
        return message

    async def terminate(self):
        logger.info("[Misskey] 终止适配器")
        self._running = False
        if self.api:
            await self.api.close()

    def get_client(self) -> Any:
        return self.api
