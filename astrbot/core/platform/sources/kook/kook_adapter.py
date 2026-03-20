import asyncio
import json
import re

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, AtAll, Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.message.components import File, Record, Video
from astrbot.core.platform.astr_message_event import MessageSesion

from .kook_client import KookClient
from .kook_config import KookConfig
from .kook_event import KookEvent
from .kook_types import (
    ContainerModule,
    FileModule,
    HeaderModule,
    ImageGroupModule,
    KmarkdownElement,
    KookCardMessageContainer,
    KookChannelType,
    KookMessageEventData,
    KookMessageType,
    KookModuleType,
    PlainTextElement,
    SectionModule,
)

KOOK_AT_SELECTOR_REGEX = re.compile(r"\(met\)([^()]+)\(met\)")


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

    def _should_ignore_event_by_bot_nickname(self, author_id: str) -> bool:
        return self.client.bot_id == author_id

    async def _on_received(self, event: KookMessageEventData):
        logger.debug(
            f'[KOOK] 收到来自"{event.channel_type.name}"渠道的消息, 消息类型为: {event.type.name}({event.type.value})'
        )
        event_type = event.type
        if event_type in (KookMessageType.KMARKDOWN, KookMessageType.CARD):
            if self._should_ignore_event_by_bot_nickname(event.author_id):
                logger.debug("[KOOK] 收到来自机器人自身的消息, 忽略此消息")
                return
            try:
                abm = await self.convert_message(event)
                await self.handle_msg(abm)
            except Exception as e:
                logger.error(f"[KOOK] 消息处理异常: {e}")
        elif event_type == KookMessageType.SYSTEM:
            logger.debug(f'[KOOK] 消息为系统通知, 通知类型为: "{event.extra.type}"')
            logger.debug(f"[KOOK] 原始消息数据: {event.to_json()}")

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

    def _parse_kmarkdown_text_message(
        self, data: KookMessageEventData, self_id: str
    ) -> tuple[list, str]:
        kmarkdown = data.extra.kmarkdown
        content = data.content or ""
        if kmarkdown is None:
            logger.error(
                f'[KOOK] 无法转换"{KookMessageType.KMARKDOWN.name}"消息, 消息中找不到kmarkdown字段'
            )
            logger.error(f"[KOOK] 原始消息内容: {data.to_json()}")
            return [], ""

        raw_content = kmarkdown.raw_content or content
        if not isinstance(content, str):
            content = str(content)
        if not isinstance(raw_content, str):
            raw_content = str(raw_content)

        # TODO 后面的pydantic类型替换,以后再来探索吧 :(
        mention_name_map: dict[str, str] = {}
        mention_part = kmarkdown.mention_part
        if isinstance(mention_part, list):
            for item in mention_part:
                if not isinstance(item, dict):
                    continue
                mention_id = item.get("id")
                if mention_id is None:
                    continue
                mention_name_map[str(mention_id)] = str(item.get("username", ""))

        components = []
        cursor = 0
        for match in KOOK_AT_SELECTOR_REGEX.finditer(content):
            if match.start() > cursor:
                plain_text = content[cursor : match.start()]
                if plain_text:
                    components.append(Plain(text=plain_text))

            mention_target = match.group(1).strip()
            if mention_target == "all":
                components.append(AtAll())
            elif mention_target:
                components.append(
                    At(
                        qq=mention_target,
                        name=mention_name_map.get(mention_target, ""),
                    )
                )
            cursor = match.end()

        if cursor < len(content):
            tail_text = content[cursor:]
            if tail_text:
                components.append(Plain(text=tail_text))

        message_str = raw_content
        if components:
            for comp in components:
                if isinstance(comp, Plain):
                    if not comp.text.strip():
                        continue
                    break
                if isinstance(comp, At):
                    if str(comp.qq) == str(self_id):
                        message_str = re.sub(
                            r"^@[^\s]+(\s*-\s*[^\s]+)?\s*",
                            "",
                            message_str,
                            count=1,
                        ).strip()
                    break
        if not components:
            if message_str:
                components = [Plain(text=message_str)]
            else:
                components = []

        return components, message_str

    def _parse_card_message(self, data: KookMessageEventData) -> tuple[list, str]:
        content = data.content
        if not isinstance(content, str):
            content = str(content)

        card_list = KookCardMessageContainer.from_dict(json.loads(content))

        text_parts: list[str] = []
        images: list[str] = []
        files: list[tuple[KookModuleType, str, str]] = []

        for card in card_list:
            for module in card.modules:
                match module:
                    case SectionModule():
                        if content := self._handle_section_text(module):
                            text_parts.append(content)

                    case ContainerModule() | ImageGroupModule():
                        urls = self._handle_image_group(module)
                        images.extend(urls)
                        text_parts.append(" [image]" * len(urls))

                    case HeaderModule():
                        text_parts.append(module.text.content)

                    case FileModule():
                        files.append((module.type, module.title, module.src))
                        text_parts.append(f" [{module.type.value}]")

                    case _:
                        logger.debug(f"[KOOK] 跳过或未处理模块: {module.type}")

        text = "".join(text_parts)
        message = []

        if text:
            for search in KOOK_AT_SELECTOR_REGEX.finditer(text):
                search_text = search.group(1).strip()
                if search_text == "all":
                    message.append(AtAll())
                    continue
                message.append(At(qq=search_text))
                text = text.replace(f"(met){search_text}(met)", "")

            message.append(Plain(text=text))

        for img_url in images:
            message.append(Image(file=img_url))
        for file in files:
            file_type = file[0]
            file_name = file[1]
            file_url = file[2]
            if file_type == KookModuleType.FILE:
                message.append(File(name=file_name, file=file_url))
            elif file_type == KookModuleType.VIDEO:
                message.append(Video(file=file_url))
            elif file_type == KookModuleType.AUDIO:
                message.append(Record(file=file_url))
            else:
                logger.warning(f"[KOOK] 跳过未知文件类型: {file_type.name}")

        return message, text

    def _handle_section_text(self, module: SectionModule) -> str:
        """专门处理 Section 里的文本提取"""
        if isinstance(module.text, (KmarkdownElement, PlainTextElement)):
            return module.text.content or ""
        return ""

    def _handle_image_group(
        self, module: ContainerModule | ImageGroupModule
    ) -> list[str]:
        """专门处理图片组/容器里的合法 URL 提取"""
        valid_urls = []
        for el in module.elements:
            image_src = el.src
            if not el.src.startswith(("http://", "https://")):
                logger.warning(f"[KOOK] 屏蔽非http图片url: {image_src}")
                continue
            valid_urls.append(el.src)
        return valid_urls

    async def convert_message(self, data: KookMessageEventData) -> AstrBotMessage:
        abm = AstrBotMessage()
        abm.raw_message = data.to_dict()
        abm.self_id = self.client.bot_id

        channel_type = data.channel_type
        author_id = data.author_id
        # channel_type定义: https://developer.kookapp.cn/doc/event/event-introduction
        match channel_type:
            case KookChannelType.GROUP:
                session_id = data.target_id or "unknown"
                abm.type = MessageType.GROUP_MESSAGE
                abm.group_id = session_id
                abm.session_id = session_id
            case KookChannelType.PERSON:
                abm.type = MessageType.FRIEND_MESSAGE
                abm.group_id = ""
                abm.session_id = data.author_id or "unknown"
            case KookChannelType.BROADCAST:
                session_id = data.target_id or "unknown"
                abm.type = MessageType.OTHER_MESSAGE
                abm.group_id = session_id
                abm.session_id = session_id
            case _:
                raise ValueError(f"不支持的频道类型: {channel_type}")

        abm.sender = MessageMember(
            user_id=author_id,
            nickname=data.extra.author.username if data.extra.author else "unknown",
        )

        abm.message_id = data.msg_id or "unknown"

        if data.type == KookMessageType.KMARKDOWN:
            message, message_str = self._parse_kmarkdown_text_message(data, abm.self_id)
            abm.message = message
            abm.message_str = message_str
        elif data.type == KookMessageType.CARD:
            try:
                abm.message, abm.message_str = self._parse_card_message(data)
            except Exception as exp:
                logger.error(f"[KOOK] 卡片消息解析失败: {exp}")
                logger.error(f"[KOOK] 原始消息内容: {data.to_json()}")
                abm.message_str = "[卡片消息解析失败]"
                abm.message = [Plain(text="[卡片消息解析失败]")]
        else:
            logger.warning(f'[KOOK] 不支持的kook消息类型: "{data.type.name}"')
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
        self.commit_event(message_event)
