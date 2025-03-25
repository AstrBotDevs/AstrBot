import quart
import logging
import asyncio
from botpy import BotAPI, BotHttp, Client, Token, BotWebSocket, ConnectionSession
from astrbot.api import logger
from cryptography.hazmat.primitives.asymmetric import ed25519

# remove logger handler
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


class QQOfficialWebhook:
    def __init__(self, config: dict, event_queue: asyncio.Queue, botpy_client: Client):
        self.appid = config["appid"]
        self.secret = config["secret"]
        self.port = config.get("port", 6196)
        self.callback_server_host = config.get("callback_server_host", "0.0.0.0")

        if isinstance(self.port, str):
            self.port = int(self.port)

        self.http: BotHttp = BotHttp(timeout=300)
        self.api: BotAPI = BotAPI(http=self.http)
        self.token = Token(self.appid, self.secret)

        self.server = quart.Quart(__name__)
        self.server.add_url_rule(
            "/astrbot-qo-webhook/callback", view_func=self.callback, methods=["POST"]
        )
        self.client = botpy_client
        self.event_queue = event_queue
        self.shutdown_event = asyncio.Event()

    async def initialize(self):
        logger.info("正在登录到 QQ 官方机器人...")
        self.user = await self.http.login(self.token)
        logger.info(f"已登录 QQ 官方机器人账号: {self.user}")
        # 直接注入到 botpy 的 Client，移花接木！
        self.client.api = self.api
        self.client.http = self.http

        async def bot_connect():
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
            "plain_token", ""
        )
        # sign
        signature = private_key.sign(msg.encode()).hex()
        response = {
            "plain_token": validation_payload.get("plain_token"),
            "signature": signature,
        }
        return response

    async def callback(self):
        msg: dict = await quart.request.json
        logger.debug(f"收到 qq_official_webhook 回调: {msg}")

        event = msg.get("t")
        opcode = msg.get("op")
        data = msg.get("d")

        if opcode == 13:
            # validation
            signed = await self.webhook_validation(data)
            print(signed)
            return signed

        if event and opcode == BotWebSocket.WS_DISPATCH_EVENT:
            event = msg["t"].lower()
            try:
                func = self._connection.parser[event]
            except KeyError:
                logger.error("_parser unknown event %s.", event)
            else:
                func(msg)

        return {"opcode": 12}

    async def start_polling(self):
        logger.info(
            f"将在 {self.callback_server_host}:{self.port} 端口启动 QQ 官方机器人 webhook 适配器。"
        )
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()
