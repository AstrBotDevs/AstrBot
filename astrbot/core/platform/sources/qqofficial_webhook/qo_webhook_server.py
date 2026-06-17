import asyncio
import json
import logging
import time
from binascii import Error as BinasciiError
from typing import cast

from botpy import BotAPI, BotHttp, BotWebSocket, Client, ConnectionSession, Token
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from astrbot.api import logger
from astrbot.core.platform.webhook_server import FastAPIWebhookServer

from ..qqofficial.qqofficial_platform_adapter import _ensure_group_message_create_parser

# remove logger handler
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

_SIGNATURE_HEADER = "X-Signature-Ed25519"
_SIGNATURE_TIMESTAMP_HEADER = "X-Signature-Timestamp"
_ED25519_SEED_SIZE = 32
_ED25519_SIGNATURE_SIZE = 64


def _build_ed25519_seed(secret: str) -> bytes:
    if not secret:
        raise ValueError("QQ official bot secret is empty.")

    seed = secret.encode("utf-8")
    while len(seed) < _ED25519_SEED_SIZE:
        seed *= 2
    return seed[:_ED25519_SEED_SIZE]


def _sign_qq_webhook_payload(secret: str, timestamp: str, payload: bytes) -> str:
    seed = _build_ed25519_seed(secret)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
    return private_key.sign(timestamp.encode("utf-8") + payload).hex()


def _verify_qq_webhook_signature(
    secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
) -> bool:
    if not timestamp or not signature:
        return False

    try:
        signature_buffer = bytes.fromhex(signature)
    except (BinasciiError, ValueError):
        return False

    if (
        len(signature_buffer) != _ED25519_SIGNATURE_SIZE
        or signature_buffer[63] & 224 != 0
    ):
        return False

    try:
        seed = _build_ed25519_seed(secret)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        public_key = private_key.public_key()
        public_key.verify(signature_buffer, timestamp.encode("utf-8") + body)
    except (InvalidSignature, ValueError):
        return False
    return True


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

        self.http: BotHttp = BotHttp(
            timeout=300,
            is_sandbox=self.is_sandbox,
            app_id=self.appid,
            secret=self.secret,
        )
        self.api: BotAPI = BotAPI(http=self.http)
        self.token = Token(self.appid, self.secret)

        self.server = FastAPIWebhookServer("qq-official-webhook")
        self.server.add_url_rule(
            "/astrbot-qo-webhook/callback",
            view_func=self.callback,
            methods=["POST"],
        )
        self.client = botpy_client
        self.event_queue = event_queue
        self.shutdown_event = asyncio.Event()
        self._connection: ConnectionSession | None = None

        # Cache for extra fields extracted from raw webhook payloads, keyed by message id
        self._extra_data_cache: dict[str, dict] = {}

        # Deduplication cache for webhook retry callbacks.
        self._seen_event_ids: dict[str, float] = {}
        self._dedup_ttl: int = 60  # seconds

    async def initialize(self) -> None:
        logger.info("正在登录到 QQ 官方机器人...")
        self.user = await self.http.login(self.token)
        logger.info(f"已登录 QQ 官方机器人账号: {self.user}")
        # 直接注入到 botpy 的 Client，移花接木！
        self.client.api = self.api
        self.client.http = self.http
        self._setup_connection()

    def _setup_connection(self) -> None:
        if self._connection is not None:
            return
        _ensure_group_message_create_parser()
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
        # sign
        signature = private_key.sign(msg.encode()).hex()
        response = {
            "plain_token": validation_payload.get("plain_token"),
            "signature": signature,
        }
        return response

    def pop_extra_data(self, message_id: str) -> dict:
        """Pop and return extra fields cached from the raw webhook payload for a given message ID."""
        return self._extra_data_cache.pop(message_id, {})

    async def callback(self, request):
        """内部服务器的回调入口"""
        return await self.handle_callback(request)

    async def handle_callback(self, request) -> dict | tuple[dict[str, str], int]:
        """处理 webhook 回调，可被统一 webhook 入口复用

        Args:
            request: FastAPI webhook request 对象

        Returns:
            响应数据
        """
        body = await request.get_data()
        if not _verify_qq_webhook_signature(
            self.secret,
            request.headers.get(_SIGNATURE_TIMESTAMP_HEADER),
            request.headers.get(_SIGNATURE_HEADER),
            body,
        ):
            logger.warning("qq_official_webhook signature verification failed.")
            return {"error": "Invalid signature"}, 401

        try:
            msg = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning("qq_official_webhook callback body is not valid JSON.")
            return {"error": "Invalid JSON"}, 400
        if not isinstance(msg, dict):
            return {"error": "Invalid JSON"}, 400

        logger.debug(f"收到 qq_official_webhook 回调: {msg}")

        event = msg.get("t")
        opcode = msg.get("op")
        data = msg.get("d")

        if opcode == 13:
            # validation
            signed = await self.webhook_validation(cast(dict, data))
            logger.debug(f"webhook validation response: {signed}")
            return signed

        event_id = msg.get("id")
        if event_id:
            now = time.monotonic()
            # Lazily evict expired entries to prevent unbounded growth.
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
            event = msg["t"].lower()
            if self._connection is None:
                logger.warning(
                    "qq_official_webhook botpy connection is not initialized; "
                    "creating parser connection lazily.",
                )
                self._setup_connection()
            connection = cast(ConnectionSession, self._connection)

            # Extract extra fields from raw payload before botpy parses and discards them
            if data:
                msg_id = data.get("id")
                if msg_id:
                    author = data.get("author") or {}
                    extra: dict = {}
                    if union_openid := author.get("union_openid"):
                        extra["union_openid"] = union_openid
                    if message_scene := data.get("message_scene"):
                        extra["message_scene"] = message_scene
                    if extra:
                        self._extra_data_cache[msg_id] = extra
            try:
                func = connection.parser[event]
            except KeyError:
                logger.error("_parser unknown event %s.", event)
                if data:
                    self._extra_data_cache.pop(data.get("id", ""), None)
            else:
                func(msg)

        return {"opcode": 12}

    async def start_polling(self) -> None:
        logger.info(
            f"将在 {self.callback_server_host}:{self.port} 端口启动 QQ 官方机器人 webhook 适配器。",
        )
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self) -> None:
        await self.shutdown_event.wait()
