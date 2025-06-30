import json
import hmac
import hashlib
import asyncio
import logging
from typing import Callable, Optional
from quart import Quart, request, Response
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from astrbot.api import logger


class SlackWebhookClient:
    """Slack Webhook 模式客户端，使用 Quart 作为 Web 服务器"""

    def __init__(
        self,
        web_client: AsyncWebClient,
        signing_secret: str,
        host: str = "0.0.0.0",
        port: int = 3000,
        path: str = "/slack/events",
        event_handler: Optional[Callable] = None,
    ):
        self.web_client = web_client
        self.signing_secret = signing_secret
        self.host = host
        self.port = port
        self.path = path
        self.event_handler = event_handler

        self.app = Quart(__name__)
        self._setup_routes()

        # 禁用 Quart 的默认日志输出
        logging.getLogger("quart.app").setLevel(logging.WARNING)
        logging.getLogger("quart.serving").setLevel(logging.WARNING)

        self.shutdown_event = asyncio.Event()

    def _setup_routes(self):
        """设置路由"""

        @self.app.route(self.path, methods=["POST"])
        async def slack_events():
            """处理 Slack 事件"""
            try:
                # 获取请求体和头部
                body = await request.get_data()
                event_data = json.loads(body.decode("utf-8"))

                # Verify Slack request signature
                timestamp = request.headers.get("X-Slack-Request-Timestamp")
                signature = request.headers.get("X-Slack-Signature")
                if not timestamp or not signature:
                    return Response("Missing headers", status=400)
                # Calculate the HMAC signature
                sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
                my_signature = (
                    "v0="
                    + hmac.new(
                        self.signing_secret.encode("utf-8"),
                        sig_basestring.encode("utf-8"),
                        hashlib.sha256,
                    ).hexdigest()
                )
                # Verify the signature
                if not hmac.compare_digest(my_signature, signature):
                    logger.warning("Slack request signature verification failed")
                    return Response("Invalid signature", status=400)
                logger.info(f"Received Slack event: {event_data}")

                # 处理 URL 验证事件
                if event_data.get("type") == "url_verification":
                    return {"challenge": event_data.get("challenge")}
                # 处理事件
                if self.event_handler and event_data.get("type") == "event_callback":
                    await self.event_handler(event_data)

                return Response("", status=200)

            except Exception as e:
                logger.error(f"处理 Slack 事件时出错: {e}")
                return Response("Internal Server Error", status=500)

        @self.app.route("/health", methods=["GET"])
        async def health_check():
            """健康检查端点"""
            return {"status": "ok", "service": "slack-webhook"}

    async def start(self):
        """启动 Webhook 服务器"""
        logger.info(
            f"Slack Webhook 服务器启动中，监听 {self.host}:{self.port}{self.path}..."
        )

        await self.app.run_task(
            host=self.host,
            port=self.port,
            debug=False,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()

    async def stop(self):
        """停止 Webhook 服务器"""
        self.shutdown_event.set()
        logger.info("Slack Webhook 服务器已停止")


class SlackSocketClient:
    """Slack Socket 模式客户端"""

    def __init__(
        self,
        web_client: AsyncWebClient,
        app_token: str,
        event_handler: Optional[Callable] = None,
    ):
        self.web_client = web_client
        self.app_token = app_token
        self.event_handler = event_handler
        self.socket_client = None

    async def _handle_events(self, _: SocketModeClient, req: SocketModeRequest):
        """处理 Socket Mode 事件"""
        try:
            # 确认收到事件
            response = SocketModeResponse(envelope_id=req.envelope_id)
            await self.socket_client.send_socket_mode_response(response)

            # 处理事件
            if self.event_handler:
                await self.event_handler(req)

        except Exception as e:
            logger.error(f"处理 Socket Mode 事件时出错: {e}")

    async def start(self):
        """启动 Socket Mode 连接"""
        self.socket_client = SocketModeClient(
            app_token=self.app_token,
            logger=logger,
            web_client=self.web_client,
        )

        # 注册事件处理器
        self.socket_client.socket_mode_request_listeners.append(self._handle_events)

        logger.info("Slack Socket Mode 客户端启动中...")
        await self.socket_client.connect()

    async def stop(self):
        """停止 Socket Mode 连接"""
        if self.socket_client:
            await self.socket_client.disconnect()
            await self.socket_client.close()
        logger.info("Slack Socket Mode 客户端已停止")
