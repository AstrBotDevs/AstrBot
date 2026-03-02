import asyncio
import json
import re

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSesion

from .kook_client import KookClient
from .kook_config import KookConfig
from .kook_event import KookEvent


@register_platform_adapter(
    "kook",
    "KOOK 适配器",
)
class KookPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.kook_config = KookConfig.from_dict(platform_config)
        logger.debug(f"[KOOK] 配置: {self.kook_config.pretty_jsons()}")
        self.settings = platform_settings
        self.client = KookClient(self.kook_config, self._on_received)
        self._reconnect_task = None
        self.running = False
        self._main_task = None

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        inner_message = AstrBotMessage()
        inner_message.session_id = session.session_id
        inner_message.type = session.message_type
        message_event = KookEvent(
            message_str=message_chain.get_plain_text(),
            message_obj=inner_message,
            platform_meta=self.meta(),
            session_id=session.session_id,
            client=self.client,
        )
        await message_event.send(message_chain)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="kook", description="KOOK 适配器", id=self.kook_config.id
        )

    async def _on_received(self, data: dict):
        logger.debug(f"KOOK 收到数据: {data}")
        if "d" in data and data["s"] == 0:
            event_type = data["d"].get("type")
            # 支持type=9（文本）和type=10（卡片）
            if event_type in (9, 10):
                try:
                    abm = await self.convert_message(data["d"])
                    await self.handle_msg(abm)
                except Exception as e:
                    logger.error(f"[KOOK] 消息处理异常: {e}")

    async def run(self):
        """主运行循环"""
        self.running = True
        logger.info("[KOOK] 启动KOOK适配器")

        # 启动主循环
        self._main_task = asyncio.create_task(self._main_loop())

        try:
            await self._main_task
        except asyncio.CancelledError:
            logger.info("[KOOK] 适配器被取消")
        except Exception as e:
            logger.error(f"[KOOK] 适配器运行异常: {e}")
        finally:
            self.running = False
            await self._cleanup()

    async def _main_loop(self):
        """主循环，处理连接和重连"""
        consecutive_failures = 0
        max_consecutive_failures = self.kook_config.max_consecutive_failures
        max_retry_delay = self.kook_config.max_retry_delay

        while self.running:
            try:
                logger.info("[KOOK] 尝试连接KOOK服务器...")

                # 尝试连接
                success = await self.client.connect()

                if success:
                    logger.info("[KOOK] 连接成功，开始监听消息")
                    consecutive_failures = 0  # 重置失败计数

                    # 等待连接结束（可能是正常关闭或异常）
                    while self.client.running and self.running:
                        try:
                            # 等待 client 内部触发 _stop_event，或者超时 1 秒后重试
                            # 使用 wait_for 配合 timeout 是为了防止极端情况下 self.running 变化没被察觉
                            await asyncio.wait_for(
                                self.client.wait_until_closed(), timeout=1.0
                            )
                        except asyncio.TimeoutError:
                            # 正常超时，继续下一轮 while 检查
                            continue

                    if self.running:
                        logger.warning("[KOOK] 连接断开，准备重连")

                else:
                    consecutive_failures += 1
                    logger.error(
                        f"[KOOK] 连接失败，连续失败次数: {consecutive_failures}"
                    )

                    if consecutive_failures >= max_consecutive_failures:
                        logger.error("[KOOK] 连续失败次数过多，停止重连")
                        break

                    # 等待一段时间后重试
                    wait_time = min(
                        2**consecutive_failures, max_retry_delay
                    )  # 指数退避
                    logger.info(f"[KOOK] 等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)

            except Exception as e:
                consecutive_failures += 1
                logger.error(f"[KOOK] 主循环异常: {e}")

                if consecutive_failures >= max_consecutive_failures:
                    logger.error("[KOOK] 连续异常次数过多，停止重连")
                    break

                await asyncio.sleep(5)

    async def _cleanup(self):
        """清理资源"""
        logger.info("[KOOK] 开始清理资源")

        if self.client:
            try:
                await self.client.close()
            except Exception as e:
                logger.error(f"[KOOK] 关闭客户端异常: {e}")

        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass

        logger.info("[KOOK] 资源清理完成")

    async def convert_message(self, data: dict) -> AstrBotMessage:
        abm = AstrBotMessage()
        abm.raw_message = data
        abm.self_id = self.client.bot_id

        channel_type = data.get("channel_type")
        # channel_type定义: https://developer.kookapp.cn/doc/event/event-introduction
        match channel_type:
            case "GROUP":
                abm.type = MessageType.GROUP_MESSAGE
                abm.group_id = data.get("target_id")
                abm.session_id = data.get("target_id")
            case "PERSON":
                abm.type = MessageType.FRIEND_MESSAGE
                abm.group_id = ""
                abm.session_id = data.get("author_id")
            case "BROADCAST":
                abm.type = MessageType.OTHER_MESSAGE
                abm.group_id = data.get("target_id")
                abm.session_id = data.get("target_id")
            case _:
                raise ValueError(f"不支持的频道类型: {channel_type}")

        abm.sender = MessageMember(
            user_id=data.get("author_id"),
            nickname=data.get("extra", {}).get("author", {}).get("username", ""),
        )

        abm.message_id = data.get("msg_id")

        # 普通文本消息
        if data.get("type") == 9:
            raw_content = (
                data.get("extra", {})
                .get("kmarkdown", {})
                .get("raw_content", data.get("content"))
            )

            raw_content = re.sub(
                r"^@[^\s]+(\s*-\s*[^\s]+)?\s*", "", raw_content
            )  # 删除@前缀
            abm.message_str = raw_content
            abm.message = [Plain(text=raw_content)]
        # 卡片消息
        elif data.get("type") == 10:
            content = data.get("content")
            try:
                card_list = json.loads(content)
                text = ""
                images = []
                for card in card_list:
                    for module in card.get("modules", []):
                        if module.get("type") == "section":
                            text += module.get("text", {}).get("content", "")
                        elif module.get("type") == "container":
                            for element in module.get("elements", []):
                                if element.get("type") == "image":
                                    image_src = element.get("src")
                                    if not isinstance(image_src, str):
                                        logger.warning(
                                            f'[KOOK] 处理卡片中的图片时发生错误,图片url "{image_src}" 应该为str类型, 而不是 "{type(image_src)}" '
                                        )
                                        continue
                                    if not image_src.startswith(
                                        ("http://", "https://")
                                    ):
                                        logger.warning(
                                            f"[KOOK] 屏蔽非http图片url: {image_src}"
                                        )
                                        continue
                                    images.append(image_src)

                abm.message_str = text
                abm.message = []
                if text:
                    abm.message.append(Plain(text=text))
                for img_url in images:
                    abm.message.append(Image(file=img_url))
            except Exception as exp:
                logger.error(f"[KOOK] 卡片消息解析失败: {exp}")
                abm.message_str = "[卡片消息解析失败]"
                abm.message = [Plain(text="[卡片消息解析失败]")]
        else:
            logger.warning(f'[KOOK] 不支持的kook消息类型: "{data.get("type")}"')
            abm.message_str = "[不支持的消息类型]"
            abm.message = [Plain(text="[不支持的消息类型]")]

        return abm

    async def handle_msg(self, message: AstrBotMessage):
        message_event = KookEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )
        raw = message.raw_message
        is_at = False
        # 检查kmarkdown.mention_role_part
        kmarkdown = raw.get("extra", {}).get("kmarkdown", {})
        mention_role_part = kmarkdown.get("mention_role_part", [])
        raw_content = kmarkdown.get("raw_content", "")
        bot_nickname = self.client.bot_name
        if mention_role_part:
            is_at = True
        elif f"@{bot_nickname}" in raw_content:
            is_at = True
        if is_at:
            message_event.is_wake = True
            message_event.is_at_or_wake_command = True
        self.commit_event(message_event)
