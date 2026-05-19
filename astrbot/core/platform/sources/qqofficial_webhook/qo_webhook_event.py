import botpy.interaction
from botpy import Client

from astrbot.api import logger
from astrbot.api.platform import AstrBotMessage, PlatformMetadata

from ..qqofficial.qqofficial_message_event import QQOfficialMessageEvent


class QQOfficialWebhookMessageEvent(QQOfficialMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        bot: Client,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id, bot)

    async def ack_interaction(self, code: int = 0) -> None:
        """Webhook 模式下,interaction ack 必须通过 HTTP 响应体返回,
        而不是 ``PUT /interactions/{id}`` 接口(QQ webhook 模式会忽略它)。

        本方法只记录 code 并触发 done 事件，由 webhook 服务在收到响应前
        从事件上读取该 code 并写入 HTTP 响应体。
        """
        if self._interaction_acked:
            logger.debug(
                f"[QQOfficial-Webhook] ack_interaction 跳过(已 ack)，请求 code={code}"
            )
            return
        if not isinstance(self.message_obj.raw_message, botpy.interaction.Interaction):
            return
        self._interaction_acked = True
        self._interaction_ack_code = code
        logger.debug(f"[QQOfficial-Webhook] 记录 interaction code={code}")
        self._interaction_ack_done.set()
