import sys
import asyncio
import os

from astrbot.api.platform import Platform, AstrBotMessage, MessageType, PlatformMetadata
from astrbot.api.event import MessageChain
from astrbot.core.platform.astr_message_event import MessageSesion
from ...register import register_platform_adapter
from .gewechat_event import GewechatPlatformEvent
from .client import SimpleGewechatClient
from astrbot import logger

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


@register_platform_adapter("gewechat", "基于 gewechat 的 Wechat 适配器")
class GewechatPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)
        self.config = platform_config
        self.settingss = platform_settings
        self.test_mode = os.environ.get("TEST_MODE", "off") == "on"
        self.client = None

        self.client = SimpleGewechatClient(
            self.config["base_url"],
            self.config["nickname"],
            self.config["host"],
            self.config["port"],
            self._event_queue,
        )

        async def on_event_received(abm: AstrBotMessage):
            await self.handle_msg(abm)

        self.client.on_event_received = on_event_received

    @override
    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        session_id = session.session_id
        if "#" in session_id:
            # unique session
            to_wxid = session_id.split("#")[1]
        else:
            to_wxid = session_id

        await GewechatPlatformEvent.send_with_client(
            message_chain, to_wxid, self.client
        )

        await super().send_by_session(session, message_chain)

    @override
    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="gewechat",
            description="基于 gewechat 的 Wechat 适配器",
            id=self.config.get("id"),
        )

    async def terminate(self):
        self.client.shutdown_event.set()
        try:
            await self.client.server.shutdown()
        except Exception as _:
            pass
        logger.info("Gewechat 适配器已被优雅地关闭。")

    async def logout(self):
        await self.client.logout()

    @override
    def run(self):
        return self._run()

    async def _run(self):
        await self.client.login()
        await self.client.start_polling()

    async def handle_msg(self, message: AstrBotMessage):
        if message.type == MessageType.GROUP_MESSAGE:
            if self.settingss["unique_session"]:
                message.session_id = message.sender.user_id + "#" + message.group_id

        message_event = GewechatPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )

        self.commit_event(message_event)

    def get_client(self) -> SimpleGewechatClient:
        return self.client
