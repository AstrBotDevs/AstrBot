"""
企业微信智能机器人 HTTP 服务器
处理企业微信智能机器人的 HTTP 回调请求
"""

import asyncio
from typing import Dict, Any, Optional, Callable

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
        message_handler: Optional[
            Callable[[Dict[str, Any], Dict[str, str]], Any]
        ] = None,
    ):
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

    def _setup_routes(self):
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
        """验证回调 URL"""
        args = quart.request.args
        msg_signature = args.get("msg_signature")
        timestamp = args.get("timestamp")
        nonce = args.get("nonce")
        echostr = args.get("echostr")

        if not all([msg_signature, timestamp, nonce, echostr]):
            logger.error("URL 验证参数缺失")
            return "verify fail", 400

        # 类型检查确保不为 None
        assert msg_signature is not None
        assert timestamp is not None
        assert nonce is not None
        assert echostr is not None

        logger.info("收到企业微信智能机器人 WebHook URL 验证请求。")
        result = self.api_client.verify_url(msg_signature, timestamp, nonce, echostr)
        return result, 200, {"Content-Type": "text/plain"}

    async def handle_message(self):
        """处理消息回调"""
        args = quart.request.args
        msg_signature = args.get("msg_signature")
        timestamp = args.get("timestamp")
        nonce = args.get("nonce")

        if not all([msg_signature, timestamp, nonce]):
            logger.error("消息回调参数缺失")
            return "缺少必要参数", 400

        # 类型检查确保不为 None
        assert msg_signature is not None
        assert timestamp is not None
        assert nonce is not None

        logger.debug(
            f"收到消息回调，msg_signature={msg_signature}, timestamp={timestamp}, nonce={nonce}"
        )

        try:
            # 获取请求体
            post_data = await quart.request.get_data()

            # 确保 post_data 是 bytes 类型
            if isinstance(post_data, str):
                post_data = post_data.encode("utf-8")

            # 解密消息
            ret_code, message_data = await self.api_client.decrypt_message(
                post_data, msg_signature, timestamp, nonce
            )

            if ret_code != WecomAIBotConstants.SUCCESS or not message_data:
                logger.error("消息解密失败，错误码: %d", ret_code)
                return "消息解密失败", 400

            # 调用消息处理器
            response = None
            if self.message_handler:
                try:
                    response = await self.message_handler(
                        message_data, {"nonce": nonce, "timestamp": timestamp}
                    )
                except Exception as e:
                    logger.error("消息处理器执行异常: %s", e)
                    return "消息处理异常", 500

            if response:
                return response, 200, {"Content-Type": "text/plain"}
            else:
                return "success", 200, {"Content-Type": "text/plain"}

        except Exception as e:
            logger.error("处理消息时发生异常: %s", e)
            return "内部服务器错误", 500

    async def start_server(self):
        """启动服务器"""
        logger.info("启动企业微信智能机器人服务器，监听 %s:%d", self.host, self.port)

        try:
            await self.app.run_task(
                host=self.host,
                port=self.port,
                shutdown_trigger=self.shutdown_trigger,
            )
        except Exception as e:
            logger.error("服务器运行异常: %s", e)
            raise

    async def shutdown_trigger(self):
        """关闭触发器"""
        await self.shutdown_event.wait()

    async def shutdown(self):
        """关闭服务器"""
        logger.info("企业微信智能机器人服务器正在关闭...")
        self.shutdown_event.set()

    def get_app(self):
        """获取 Quart 应用实例"""
        return self.app
