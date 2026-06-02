import time
from astrbot.api import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.api.message_components import Plain


class EventFactory:
    """事件工厂类，用于创建不同平台类型的事件对象"""

    def __init__(self, context):
        self.context = context

    def _get_platform_instance(self, platform_id: str):
        """获取平台实例，通过平台ID（用户自定义名称）获取"""
        try:
            # 使用框架提供的方法通过平台ID获取平台实例
            platform_inst = self.context.get_platform_inst(platform_id)
            if platform_inst:
                logger.debug(f"成功通过平台ID获取平台实例: {platform_id}")
                return platform_inst
        except Exception as e:
            logger.warning(f"通过context.get_platform_inst获取平台实例失败: {e}")

        logger.error(f"无法获取平台实例: {platform_id}")
        return None

    def create_event(self, unified_msg_origin: str, command: str, creator_id: str, creator_name: str = None) -> AstrMessageEvent:
        """创建事件对象，根据平台类型自动选择正确的事件类"""

        # 解析平台信息
        platform_id = "unknown"
        session_id = "unknown"
        message_type = MessageType.FRIEND_MESSAGE

        if ":" in unified_msg_origin:
            parts = unified_msg_origin.split(":")
            if len(parts) >= 3:
                # 直接使用第一部分作为平台ID（用户自定义的平台名称）
                platform_id = parts[0]
                msg_type_str = parts[1]
                session_id = ":".join(parts[2:])  # 可能包含多个冒号

                if "GroupMessage" in msg_type_str:
                    message_type = MessageType.GROUP_MESSAGE
                elif "FriendMessage" in msg_type_str:
                    message_type = MessageType.FRIEND_MESSAGE

        # 添加调试日志
        logger.debug(f"create_event: platform_id={platform_id}, unified_msg_origin={unified_msg_origin}")

        # 获取平台实例 - 使用原始的platform_id（如"本地"）
        platform_instance = self._get_platform_instance(platform_id)

        # 获取真实的平台类型
        platform_type = self._get_platform_type_from_instance(platform_instance, unified_msg_origin)
        logger.debug(f"create_event: 获取到的平台类型={platform_type}")

        # 创建基础消息对象
        msg = self._create_message_object(command, session_id, message_type, creator_id, creator_name, platform_instance)

        # 创建平台元数据，使用真实的平台类型，但ID保持原始值
        meta = PlatformMetadata(platform_type, "command_trigger", platform_id)

        # 根据平台类型创建正确的事件对象
        event = self._create_platform_specific_event(platform_type, command, msg, meta, session_id, platform_instance)
        event.is_admin = lambda: True
        event.get_sender_id = lambda: creator_id
        event.get_sender_name = lambda: creator_name or "用户"
        
        return event

    def _get_platform_type_from_instance(self, platform_instance, unified_msg_origin: str) -> str:
        """优先从平台实例获取类型，否则从origin解析"""
        if platform_instance:
            try:
                # 尝试从平台实例的元数据获取类型
                if hasattr(platform_instance, 'meta'):
                    meta = platform_instance.meta()
                    if hasattr(meta, 'name'):
                        return meta.name
            except Exception as e:
                logger.warning(f"从平台实例获取类型失败: {e}")

        # 回退到基于字符串的判断
        return self._get_platform_type_from_origin(unified_msg_origin)

    def _get_platform_type_from_origin(self, unified_msg_origin: str) -> str:
        """从unified_msg_origin中获取平台类型"""
        if ":" in unified_msg_origin:
            platform_part = unified_msg_origin.split(":")[0]
            # 根据平台名称映射到实际平台类型
            platform_mapping = {
                "aiocqhttp": "aiocqhttp",
                "qq_official": "qq_official",
                "telegram": "telegram",
                "discord": "discord",
                "slack": "slack",
                "lark": "lark",
                "wechatpadpro": "wechatpadpro",
                "webchat": "webchat",
                "dingtalk": "dingtalk",
            }
            return platform_mapping.get(platform_part, platform_part)
        return "unknown"

    def _get_real_self_id_sync(self, platform_instance) -> str:
        """
        同步方式获取真实的机器人ID
        """
        if not platform_instance:
            return "123456789"

        try:
            # 仅使用 client_self_id
            if hasattr(platform_instance, 'client_self_id'):
                val = getattr(platform_instance, 'client_self_id')
                if val and isinstance(val, (str, int)):
                    return str(val)
        except Exception as e:
            logger.debug(f"获取机器人ID时发生异常: {e}")

        return "123456789"

    def _create_message_object(self, command: str, session_id: str, message_type: MessageType,
                              creator_id: str, creator_name: str = None, platform_instance=None) -> AstrBotMessage:
        """创建消息对象"""
        msg = AstrBotMessage()
        msg.message_str = command
        msg.session_id = session_id
        msg.type = message_type

        # 使用同步方法获取真实的机器人ID
        real_self_id = self._get_real_self_id_sync(platform_instance)
        msg.self_id = real_self_id
        logger.debug(f"使用机器人ID: {msg.self_id}")

        msg.message_id = "command_trigger_" + str(int(time.time()))

        # 设置发送者信息
        from astrbot.api.platform import MessageMember
        msg.sender = MessageMember(user_id=creator_id, nickname=creator_name or "用户")

        # 设置群组ID（如果是群聊）
        if message_type == MessageType.GROUP_MESSAGE:
            # 从session_id中提取群组ID
            if "_" in session_id:
                # 处理会话隔离格式
                group_id = session_id.split("_")[0]
            else:
                group_id = session_id
            msg.group_id = group_id

        # 设置消息链
        msg.message = [Plain(command)]

        # 设置raw_message属性（模拟原始消息对象）
        msg.raw_message = {
            "message": command,
            "message_type": "group" if message_type == MessageType.GROUP_MESSAGE else "private",
            "sender": {"user_id": creator_id, "nickname": creator_name or "用户"},
            "self_id": msg.self_id
        }
        
        # 如果是群聊，在 raw_message 中添加 group_id
        if message_type == MessageType.GROUP_MESSAGE:
            msg.raw_message["group_id"] = msg.group_id

        return msg

    def _create_platform_specific_event(self, platform_name: str, command: str, msg: AstrBotMessage,
                                       meta: PlatformMetadata, session_id: str, platform_instance=None) -> AstrMessageEvent:
        """根据平台类型创建特定的事件对象"""

        if platform_name == "aiocqhttp":
            return self._create_aiocqhttp_event(command, msg, meta, session_id)
        elif platform_name == "qq_official":
            return self._create_qq_official_event(command, msg, meta, session_id)
        elif platform_name == "telegram":
            return self._create_telegram_event(command, msg, meta, session_id)
        elif platform_name == "discord":
            return self._create_discord_event(command, msg, meta, session_id)
        elif platform_name == "slack":
            return self._create_slack_event(command, msg, meta, session_id)
        elif platform_name == "lark":
            return self._create_lark_event(command, msg, meta, session_id)
        elif platform_name == "wechatpadpro":
            return self._create_wechatpadpro_event(command, msg, meta, session_id)
        elif platform_name == "webchat":
            return self._create_webchat_event(command, msg, meta, session_id)
        elif platform_name == "dingtalk":
            return self._create_dingtalk_event(command, msg, meta, session_id)
        else:
            # 默认使用基础事件对象
            return self._create_base_event(command, msg, meta, session_id)

    def _create_aiocqhttp_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 aiocqhttp 平台事件"""
        try:
            platform = self._get_platform_instance(meta.id)  # 使用平台ID而不是平台类型
            logger.debug(f"_create_aiocqhttp_event: 尝试获取平台实例，platform_id={meta.id}")
            if platform and hasattr(platform, 'bot'):
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                event = AiocqhttpMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    bot=platform.bot
                )
                # 确保事件对象有正确的平台实例引用
                event.platform_instance = platform
                logger.debug(f"成功创建 AiocqhttpMessageEvent，平台ID: {meta.name}")
                return event
        except Exception as e:
            logger.warning(f"创建 AiocqhttpMessageEvent 失败: {e}")

        # 回退到基础事件
        return self._create_base_event(command, msg, meta, session_id)

    def _create_qq_official_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 QQ 官方平台事件"""
        try:
            platform = self._get_platform_instance("qq_official")
            if platform and hasattr(platform, 'client'):
                from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import QQOfficialMessageEvent
                event = QQOfficialMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    bot=platform.client
                )
                logger.info("成功创建 QQOfficialMessageEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 QQOfficialMessageEvent 失败: {e}")

        return self._create_base_event(command, msg, meta, session_id)

    def _create_telegram_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 Telegram 平台事件"""
        try:
            platform = self._get_platform_instance("telegram")
            if platform and hasattr(platform, 'client'):
                from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                event = TelegramPlatformEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    client=platform.client
                )
                logger.info("成功创建 TelegramPlatformEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 TelegramPlatformEvent 失败: {e}")

        return self._create_base_event(command, msg, meta, session_id)

    def _create_discord_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 Discord 平台事件"""
        try:
            platform = self._get_platform_instance("discord")
            if platform and hasattr(platform, 'client'):
                from astrbot.core.platform.sources.discord.discord_platform_event import DiscordPlatformEvent
                event = DiscordPlatformEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    client=platform.client
                )
                logger.info("成功创建 DiscordPlatformEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 DiscordPlatformEvent 失败: {e}")

        return self._create_base_event(command, msg, meta, session_id)

    def _create_slack_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 Slack 平台事件"""
        try:
            platform = self._get_platform_instance("slack")
            if platform and hasattr(platform, 'web_client'):
                from astrbot.core.platform.sources.slack.slack_event import SlackMessageEvent
                event = SlackMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    web_client=platform.web_client
                )
                logger.info("成功创建 SlackMessageEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 SlackMessageEvent 失败: {e}")

        return self._create_base_event(command, msg, meta, session_id)

    def _create_lark_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 Lark 平台事件"""
        try:
            platform = self._get_platform_instance("lark")
            if platform and hasattr(platform, 'bot'):
                from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
                event = LarkMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    bot=platform.bot
                )
                logger.info("成功创建 LarkMessageEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 LarkMessageEvent 失败: {e}")

        return self._create_base_event(command, msg, meta, session_id)

    def _create_wechatpadpro_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 WeChatPadPro 平台事件"""
        try:
            platform = self._get_platform_instance("wechatpadpro")
            if platform:
                from astrbot.core.platform.sources.wechatpadpro.wechatpadpro_message_event import WeChatPadProMessageEvent
                event = WeChatPadProMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    adapter=platform
                )
                logger.info("成功创建 WeChatPadProMessageEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 WeChatPadProMessageEvent 失败: {e}")

        return self._create_base_event(command, msg, meta, session_id)

    def _create_webchat_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 WebChat 平台事件"""
        try:
            from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent
            event = WebChatMessageEvent(
                message_str=command,
                message_obj=msg,
                platform_meta=meta,
                session_id=session_id
            )
            logger.info("成功创建 WebChatMessageEvent")
            return event
        except Exception as e:
            logger.warning(f"创建 WebChatMessageEvent 失败: {e}")

        return self._create_base_event(command, msg, meta, session_id)

    def _create_dingtalk_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建钉钉平台事件"""
        try:
            platform = self._get_platform_instance("dingtalk")
            if platform and hasattr(platform, 'client'):
                from astrbot.core.platform.sources.dingtalk.dingtalk_event import DingtalkMessageEvent
                event = DingtalkMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    client=platform.client
                )
                logger.info("成功创建 DingtalkMessageEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 DingtalkMessageEvent 失败: {e}")

        return self._create_base_event(command, msg, meta, session_id)

    def _create_base_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建基础事件对象（作为回退方案）"""
        from astrbot.core.platform.astr_message_event import AstrMessageEvent as CoreAstrMessageEvent

        event = CoreAstrMessageEvent(
            message_str=command,
            message_obj=msg,
            platform_meta=meta,
            session_id=session_id
        )

        # 设置必要属性
        event.unified_msg_origin = f"{meta.name}:{msg.type.value}:{session_id}"
        event.is_wake = True  # 标记为唤醒状态
        event.is_at_or_wake_command = True  # 标记为指令

        # 尝试设置平台实例和相关属性
        try:
            platform_instance = self._get_platform_instance(meta.id)  # 使用平台ID而不是平台类型
            logger.info(f"_create_base_event: 尝试获取平台实例，platform_id={meta.id}")
            if platform_instance:
                event.platform_instance = platform_instance

                # 复制平台实例的所有相关属性到事件对象
                copied_attrs = []
                for attr_name in dir(platform_instance):
                    # 跳过私有属性和方法
                    if not attr_name.startswith('_'):
                        try:
                            attr_value = getattr(platform_instance, attr_name)
                            # 跳过方法，只复制属性
                            if not callable(attr_value):
                                setattr(event, attr_name, attr_value)
                                copied_attrs.append(attr_name)
                        except Exception as attr_e:
                            logger.debug(f"跳过属性 {attr_name}: {attr_e}")
                            continue

                logger.info(f"为基础事件复制平台属性: {copied_attrs}, 平台ID: {meta.id}")
                logger.info(f"为基础事件设置平台实例: {meta.id}")
            else:
                logger.warning(f"无法为基础事件获取平台实例: {meta.id}")
        except Exception as e:
            logger.warning(f"设置基础事件平台实例失败: {e}")

        logger.info("使用基础 AstrMessageEvent")
        return event