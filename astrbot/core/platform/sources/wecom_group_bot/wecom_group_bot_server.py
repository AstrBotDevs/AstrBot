"""企业微信消息推送机器人（原群机器人） HTTP Server"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

import quart
from wechatpy.enterprise.crypto import WeChatCrypto

from astrbot.api import logger

from .wecom_group_bot_parser import WecomGroupBotParser

MessageHandler = Callable[[dict[str, Any], dict[str, str]], Awaitable[None]]


class WecomGroupBotServer:
    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        encoding_aes_key: str,
        receive_id: str,
        parser: WecomGroupBotParser,
        message_handler: MessageHandler | None = None,
        callback_path: str = "/webhook/wecom-group-bot",
    ) -> None:
        self.host = host
        self.port = port
        self.callback_path = callback_path
        self.message_handler = message_handler
        self.parser = parser

        self.app = quart.Quart(__name__)
        self._setup_routes()

        self.crypto = WeChatCrypto(token.strip(), encoding_aes_key.strip(), receive_id.strip())
        self.shutdown_event = asyncio.Event()

    def _setup_routes(self) -> None:
        self.app.add_url_rule(self.callback_path, view_func=self.verify_url, methods=["GET"])
        self.app.add_url_rule(self.callback_path, view_func=self.handle_message, methods=["POST"])

    @staticmethod
    def _make_payload_preview(payload: dict[str, Any], limit: int = 800) -> str:
        try:
            serialized = json.dumps(payload, ensure_ascii=False)
        except Exception:
            serialized = str(payload)
        serialized = serialized.strip()
        if len(serialized) > limit:
            return f"{serialized[:limit]}...<truncated>"
        return serialized

    async def verify_url(self):
        args = quart.request.args
        msg_signature = args.get("msg_signature")
        timestamp = args.get("timestamp")
        nonce = args.get("nonce")
        echostr = args.get("echostr")

        if not all([msg_signature, timestamp, nonce, echostr]):
            logger.error("企业微信消息推送机器人（原群机器人） URL 验证参数缺失")
            return "verify fail", 400

        try:
            echo_result = self.crypto.check_signature(msg_signature, timestamp, nonce, echostr)
            logger.info("企业微信消息推送机器人（原群机器人） URL 验证通过")
            return echo_result, 200
        except Exception as exc:  # pragma: no cover - defensive log
            logger.error("企业微信消息推送机器人（原群机器人） URL 验证失败: %s", exc)
            return "verify fail", 400

    async def handle_message(self):
        args = quart.request.args
        msg_signature = args.get("msg_signature")
        timestamp = args.get("timestamp")
        nonce = args.get("nonce")

        if not all([msg_signature, timestamp, nonce]):
            logger.error("企业微信消息推送机器人（原群机器人）消息参数缺失")
            return "缺少必要参数", 400

        payload_bytes = await quart.request.get_data()
        try:
            decrypted_text = self.crypto.decrypt_message(payload_bytes, msg_signature, timestamp, nonce)
        except Exception as exc:
            logger.error("企业微信消息推送机器人（原群机器人）消息解密失败: %s", exc)
            return "解密失败", 400

        message_data = self.parser.parse(decrypted_text)
        metadata = {"msg_signature": msg_signature, "timestamp": timestamp, "nonce": nonce}

        if message_data:
            logger.info(
                (
                    "企业微信消息推送机器人（原群机器人）收到消息: chat_id=%s, msgtype=%s, sender=%s, payload=%s"
                ),
                message_data.get("chatid") or message_data.get("chat_id"),
                message_data.get("msgtype") or message_data.get("msg_type"),
                (message_data.get("from") or {}).get("userid"),
                self._make_payload_preview(message_data),
            )
        else:
            logger.warning("企业微信消息推送机器人（原群机器人）收到空消息，metadata=%s", metadata)

        if self.message_handler:
            try:
                await self.message_handler(message_data, metadata)
            except Exception as exc:  # pragma: no cover - defensive log
                logger.error("企业微信消息推送机器人（原群机器人）消息处理失败: %s", exc)
                return "处理失败", 500

        return "success", 200

    async def start(self):
        logger.info("启动企业微信消息推送机器人（原群机器人）服务器，监听 %s:%s", self.host, self.port)
        await self.app.run_task(
            host=self.host,
            port=self.port,
            shutdown_trigger=self._shutdown_trigger,
        )

    async def stop(self):
        self.shutdown_event.set()

    async def _shutdown_trigger(self):
        await self.shutdown_event.wait()
