"""消息转换器

负责将文本输入转换为AstrBotMessage对象。
"""

import uuid

from astrbot import logger
from astrbot.core.message.components import Plain
from astrbot.core.platform import AstrBotMessage, MessageMember, MessageType


class MessageConverter:
    """消息转换器

    I/O契约:
        Input: text (str), request_id (str | None)
        Output: AstrBotMessage
    """

    def __init__(
        self,
        default_session_id: str = "cli_session",
        user_id: str = "cli_user",
        user_nickname: str = "CLI User",
    ):
        """初始化消息转换器

        Args:
            default_session_id: 默认会话ID
            user_id: 用户ID
            user_nickname: 用户昵称
        """
        self.default_session_id = default_session_id
        self.user_id = user_id
        self.user_nickname = user_nickname

    def convert(
        self,
        text: str,
        request_id: str | None = None,
        use_isolated_session: bool = False,
    ) -> AstrBotMessage:
        """将文本转换为AstrBotMessage

        Args:
            text: 原始文本
            request_id: 请求ID（用于会话隔离）
            use_isolated_session: 是否使用隔离会话

        Returns:
            AstrBotMessage对象
        """
        logger.debug("Converting input: text=%s, request_id=%s", text, request_id)

        message = AstrBotMessage()
        message.self_id = "cli_bot"
        message.message_str = text
        message.message = [Plain(text)]
        message.type = MessageType.FRIEND_MESSAGE
        message.message_id = str(uuid.uuid4())

        # 根据配置决定会话ID
        if use_isolated_session and request_id:
            message.session_id = f"cli_session_{request_id}"
        else:
            message.session_id = self.default_session_id

        message.sender = MessageMember(
            user_id=self.user_id,
            nickname=self.user_nickname,
        )

        return message
