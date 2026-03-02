"""企业微信智能机器人 HTTP 服务器
处理企业微信智能机器人的 HTTP 回调请求
"""
from astrbot.core.lang import t

import asyncio
from collections.abc import Callable
from typing import Any

import quart

from astrbot.api import logger

from .wecomai_api import WecomAIBotAPIClient
from .wecomai_utils import WecomAIBotConstants


class WecomAIBotServer:
    """企业微信智能机器人 HTTP 服务器"""

    def __init__(
        self,
        host: str,
        port: int,
        api_client: WecomAIBotAPIClient,
        message_handler: Callable[[dict[str, Any], dict[str, str]], Any] | None = None,
    ) -> None:
        """初始化服务器

        Args:
            host: 监听地址
            port: 监听端口
            api_client: API客户端实例
            message_handler: 消息处理回调函数

        """
        self.host = host
        self.port = port
        self.api_client = api_client
        self.message_handler = message_handler

        self.app = quart.Quart(__name__)
        self._setup_routes()

        self.shutdown_event = asyncio.Event()

    def _setup_routes(self) -> None:
        """设置 Quart 路由"""
        # 使用 Quart 的 add_url_rule 方法添加路由
        self.app.add_url_rule(
            "/webhook/wecom-ai-bot",
            view_func=self.verify_url,
            methods=["GET"],
        )

        self.app.add_url_rule(
            "/webhook/wecom-ai-bot",
            view_func=self.handle_message,
            methods=["POST"],
        )

    async def verify_url(self):
        """内部服务器的 GET 验证入口"""
        return await self.handle_verify(quart.request)

    async def handle_verify(self, request):
        """处理 URL 验证请求，可被统一 webhook 入口复用

        Args:
            request: Quart 请求对象

        Returns:
            验证响应元组 (content, status_code, headers)
        """
        args = request.args
        msg_signature = args.get("msg_signature")
        timestamp = args.get("timestamp")
        nonce = args.get("nonce")
        echostr = args.get("echostr")

        if not all([msg_signature, timestamp, nonce, echostr]):
            logger.error(t("msg-adaee66c"))
            return "verify fail", 400

        # 类型检查确保不为 None
        assert msg_signature is not None
        assert timestamp is not None
        assert nonce is not None
        assert echostr is not None

        logger.info(t("msg-742e0b43"))
        result = self.api_client.verify_url(msg_signature, timestamp, nonce, echostr)
        return result, 200, {"Content-Type": "text/plain"}

    async def handle_message(self):
        """内部服务器的 POST 消息回调入口"""
        return await self.handle_callback(quart.request)

    async def handle_callback(self, request):
        """处理消息回调，可被统一 webhook 入口复用

        Args:
            request: Quart 请求对象

        Returns:
            响应元组 (content, status_code, headers)
        """
        args = request.args
        msg_signature = args.get("msg_signature")
        timestamp = args.get("timestamp")
        nonce = args.get("nonce")

        if not all([msg_signature, timestamp, nonce]):
            logger.error(t("msg-f86c030c"))
            return "缺少必要参数", 400

        # 类型检查确保不为 None
        assert msg_signature is not None
        assert timestamp is not None
        assert nonce is not None

        logger.debug(
            t("msg-cce4e44c", msg_signature=msg_signature, timestamp=timestamp, nonce=nonce),
        )

        try:
            # 获取请求体
            post_data = await request.get_data()

            # 确保 post_data 是 bytes 类型
            if isinstance(post_data, str):
                post_data = post_data.encode("utf-8")

            # 解密消息
            ret_code, message_data = await self.api_client.decrypt_message(
                post_data,
                msg_signature,
                timestamp,
                nonce,
            )

            if ret_code != WecomAIBotConstants.SUCCESS or not message_data:
                logger.error(t("msg-16a7bfed", ret_code=ret_code))
                return "消息解密失败", 400

            # 调用消息处理器
            response = None
            if self.message_handler:
                try:
                    response = await self.message_handler(
                        message_data,
                        {"nonce": nonce, "timestamp": timestamp},
                    )
                except Exception as e:
                    logger.error(t("msg-a567f8e3", e=e))
                    return "消息处理异常", 500

            if response:
                return response, 200, {"Content-Type": "text/plain"}
            return "success", 200, {"Content-Type": "text/plain"}

        except Exception as e:
            logger.error(t("msg-88aba3b0", e=e))
            return "内部服务器错误", 500

    async def start_server(self) -> None:
        """启动服务器"""
        logger.info(t("msg-1cccaaf4", res=self.host, res_2=self.port))

        try:
            await self.app.run_task(
                host=self.host,
                port=self.port,
                shutdown_trigger=self.shutdown_trigger,
            )
        except Exception as e:
            logger.error(t("msg-866d0b8b", e=e))
            raise

    async def shutdown_trigger(self) -> None:
        """关闭触发器"""
        await self.shutdown_event.wait()

    async def shutdown(self) -> None:
        """关闭服务器"""
        logger.info(t("msg-3269840c"))
        self.shutdown_event.set()

    def get_app(self):
        """获取 Quart 应用实例"""
        return self.app
