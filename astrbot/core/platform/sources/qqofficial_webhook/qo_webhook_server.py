from astrbot.core.lang import t
import asyncio
import logging
from typing import cast

import quart
from botpy import BotAPI, BotHttp, BotWebSocket, Client, ConnectionSession, Token
from cryptography.hazmat.primitives.asymmetric import ed25519

from astrbot.api import logger

# remove logger handler
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


class QQOfficialWebhook:
    def __init__(
        self, config: dict, event_queue: asyncio.Queue, botpy_client: Client
    ) -> None:
        self.appid = config["appid"]
        self.secret = config["secret"]
        self.port = config.get("port", 6196)
        self.is_sandbox = config.get("is_sandbox", False)
        self.callback_server_host = config.get("callback_server_host", "0.0.0.0")

        if isinstance(self.port, str):
            self.port = int(self.port)

        self.http: BotHttp = BotHttp(timeout=300, is_sandbox=self.is_sandbox)
        self.api: BotAPI = BotAPI(http=self.http)
        self.token = Token(self.appid, self.secret)

        self.server = quart.Quart(__name__)
        self.server.add_url_rule(
            "/astrbot-qo-webhook/callback",
            view_func=self.callback,
            methods=["POST"],
        )
        self.client = botpy_client
        self.event_queue = event_queue
        self.shutdown_event = asyncio.Event()

    async def initialize(self) -> None:
        logger.info(t("msg-41a3e59d"))
        self.user = await self.http.login(self.token)
        logger.info(t("msg-66040e15", res=self.user))
        # 直接注入到 botpy 的 Client，移花接木！
        self.client.api = self.api
        self.client.http = self.http

        async def bot_connect() -> None:
            pass

        self._connection = ConnectionSession(
            max_async=1,
            connect=bot_connect,
            dispatch=self.client.ws_dispatch,
            loop=asyncio.get_event_loop(),
            api=self.api,
        )

    async def repeat_seed(self, bot_secret: str, target_size: int = 32) -> bytes:
        seed = bot_secret
        while len(seed) < target_size:
            seed *= 2
        return seed[:target_size].encode("utf-8")

    async def webhook_validation(self, validation_payload: dict):
        seed = await self.repeat_seed(self.secret)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        msg = validation_payload.get("event_ts", "") + validation_payload.get(
            "plain_token",
            "",
        )
        # sign
        signature = private_key.sign(msg.encode()).hex()
        response = {
            "plain_token": validation_payload.get("plain_token"),
            "signature": signature,
        }
        return response

    async def callback(self):
        """内部服务器的回调入口"""
        return await self.handle_callback(quart.request)

    async def handle_callback(self, request) -> dict:
        """处理 webhook 回调，可被统一 webhook 入口复用

        Args:
            request: Quart 请求对象

        Returns:
            响应数据
        """
        msg: dict = await request.json
        logger.debug(t("msg-6ed59b60", msg=msg))

        event = msg.get("t")
        opcode = msg.get("op")
        data = msg.get("d")

        if opcode == 13:
            # validation
            signed = await self.webhook_validation(cast(dict, data))
            print(t("msg-ad355b59", signed=signed))
            return signed

        if event and opcode == BotWebSocket.WS_DISPATCH_EVENT:
            event = msg["t"].lower()
            try:
                func = self._connection.parser[event]
            except KeyError:
                logger.error(t("msg-4bf0bff8", event=event))
            else:
                func(msg)

        return {"opcode": 12}

    async def start_polling(self) -> None:
        logger.info(
            t("msg-cef08b17", res=self.callback_server_host, res_2=self.port),
        )
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self) -> None:
        await self.shutdown_event.wait()
