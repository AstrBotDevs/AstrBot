import asyncio
import logging
import time

import quart
from botpy import BotAPI, BotHttp, BotWebSocket, Client, ConnectionSession, Token
from cryptography.hazmat.primitives.asymmetric import ed25519

from astrbot.api import logger
from astrbot.core.platform.platform import Platform

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


class QQOfficialWebhook:
    def __init__(
        self,
        config: dict,
        event_queue: asyncio.Queue,
        botpy_client: Client,
        platform: Platform,
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
        self.platform = platform
        self.shutdown_event = asyncio.Event()
        self._seen_event_ids: dict[str, float] = {}
        self._dedup_ttl: int = 60

    async def initialize(self) -> None:
        logger.info("正在登录到 QQ 官方机器人...")
        self.user = await self.http.login(self.token)
        logger.info(f"已登录 QQ 官方机器人账号: {self.user}")
        self.client.api = self.api
        self.client.http = self.http

        async def bot_connect() -> None:
            pass

        self._connection = ConnectionSession(
            max_async=1,
            connect=bot_connect,
            dispatch=self.client.ws_dispatch,
            loop=asyncio.get_running_loop(),
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
        signature = private_key.sign(msg.encode()).hex()
        response = {
            "plain_token": validation_payload.get("plain_token"),
            "signature": signature,
        }
        return response

    def pop_extra_data(self, message_id: str) -> dict:
        """Pop and return extra fields cached from the raw webhook payload for a given message ID."""
        return self._extra_data_cache.pop(message_id, {})

    async def callback(self):
        """内部服务器的回调入口"""
        return await self.handle_callback(quart.request)

    async def handle_callback(self, request) -> dict:
        """处理 webhook 回调,可被统一 webhook 入口复用

        Args:
            request: Quart 请求对象

        Returns:
            响应数据

        """
        msg: dict = await request.json
        logger.debug(f"收到 qq_official_webhook 回调: {msg}")
        event = msg.get("t")
        opcode = msg.get("op")
        data = msg.get("d")

        context = {
            "opcode": opcode,
            "event_type": event,
            "is_validation": opcode == 13,
            "request_path": getattr(request, "path", ""),
            "request_method": getattr(request, "method", ""),
        }
        stopped = await self.platform.emit_raw_platform_event(msg, meta=context)

        if opcode == 13:
            # validation
            signed = await self.webhook_validation(cast(dict, data))
            return signed
        event_id = msg.get("id")
        if event_id:
            now = time.monotonic()
            expired = [
                k
                for k, ts in self._seen_event_ids.items()
                if now - ts > self._dedup_ttl
            ]
            for k in expired:
                del self._seen_event_ids[k]
            if event_id in self._seen_event_ids:
                logger.debug(f"Duplicate webhook event {event_id!r}, skipping.")
                return {"opcode": 12}
            self._seen_event_ids[event_id] = now

        if event and opcode == BotWebSocket.WS_DISPATCH_EVENT:
            event_lower = msg["t"].lower()
            try:
                func = self._connection.parser[event_lower]
            except KeyError:
                logger.error("_parser unknown event %s.", event_lower)
                return {"opcode": 12}
            func(msg)

            # interaction_create 在 webhook 模式下 ack code 必须放进 HTTP
            # 响应体（PUT /interactions/{id} 在 webhook 模式下会被 QQ 忽略）。
            if event_lower == "interaction_create":
                return await self._wait_interaction_ack(cast(dict, data))

        return {"opcode": 12}

    async def _wait_interaction_ack(self, data: dict) -> dict:
        """等待插件调用 event.ack_interaction(code)，把 code 放进响应体。

        botClient.on_interaction_create 在创建事件后会立刻把它注册到
        ``botClient.pending_interactions``。这里先轮询拿到事件对象，再
        等待 ``_interaction_ack_done``，最后把 code 顶层返回。
        """
        from .qo_webhook_adapter import botClient as _botClient

        interaction_id = data.get("id") or ""
        if not interaction_id:
            return {"code": 0}

        # 等事件对象创建（on_interaction_create 是异步任务，可能尚未运行）
        event_obj = None
        for _ in range(50):
            event_obj = _botClient.pending_interactions.get(interaction_id)
            if event_obj is not None:
                break
            await asyncio.sleep(0.01)
        if event_obj is None:
            logger.warning(
                f"[QQOfficial-Webhook] 未找到 interaction 事件对象 id={interaction_id}"
            )
            return {"code": 0}

        #   等到下面任一条件即响应：
        #   - 插件主动 ack（用插件指定的 code 响应）
        #   - pipeline 处理完毕但插件未 ack（用 code=0 响应，与改动前行为对齐）
        #   - 0.5s 超时兜底（超过会显示『三方未响应』）
        ack_task = asyncio.create_task(event_obj._interaction_ack_done.wait())
        pipeline_task = asyncio.create_task(event_obj._pipeline_finished.wait())
        try:
            done, pending = await asyncio.wait(
                {ack_task, pipeline_task},
                return_when=asyncio.FIRST_COMPLETED,
                timeout=0.5,
            )
            for task in pending:
                task.cancel()
            if not done:
                logger.info(
                    f"[QQOfficial-Webhook] 等待 ack/pipeline 超时，使用 code=0 兜底 id={interaction_id}"
                )
        except Exception as e:
            logger.warning(f"[QQOfficial-Webhook] 等待 interaction ack 异常: {e}")

        code = event_obj._interaction_ack_code if event_obj._interaction_acked else 0
        _botClient.pending_interactions.pop(interaction_id, None)
        return {"code": code}

    async def start_polling(self) -> None:
        logger.info(
            f"将在 {self.callback_server_host}:{self.port} 端口启动 QQ 官方机器人 webhook 适配器｡",
        )
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self) -> None:
        await self.shutdown_event.wait()
