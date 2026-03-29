"""企业微信智能机器人平台适配器
基于企业微信智能机器人 API 的消息平台适配器,支持 HTTP 回调与长连接
参考webchat_adapter.py的队列机制,实现异步消息处理和流式响应
"""

import asyncio
import base64
import hashlib
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.utils.webhook_utils import log_webhook_info

from .wecomai_api import (
    WecomAIBotAPIClient,
    WecomAIBotMessageParser,
    WecomAIBotStreamMessageBuilder,
)
from .wecomai_event import WecomAIBotMessageEvent
from .wecomai_long_connection import WecomAIBotLongConnectionClient
from .wecomai_queue_mgr import WecomAIQueueMgr
from .wecomai_server import WecomAIBotServer
from .wecomai_utils import (
    WecomAIBotConstants,
    format_session_id,
    generate_random_string,
    process_encrypted_image,
)
from .wecomai_webhook import WecomAIBotWebhookClient, WecomAIBotWebhookError


class WecomAIQueueListener:
    """企业微信智能机器人队列监听器,参考webchat的QueueListener设计"""

    def __init__(
        self,
        queue_mgr: WecomAIQueueMgr,
        callback: Callable[[dict], Awaitable[None]],
    ) -> None:
        self.queue_mgr = queue_mgr
        self.callback = callback

    async def run(self) -> None:
        """注册监听回调并定期清理过期响应｡"""
        self.queue_mgr.set_listener(self.callback)
        while True:
            self.queue_mgr.cleanup_expired_responses()
            await asyncio.sleep(1)


@register_platform_adapter(
    "wecom_ai_bot",
    "企业微信智能机器人适配器,支持 HTTP 回调接收消息",
)
class WecomAIBotAdapter(Platform):
    """企业微信智能机器人适配器"""

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings

        # 初始化配置参数
        self.connection_mode = self.config.get(
            "wecom_ai_bot_connection_mode", "webhook"
        )
        self.token = self.config.get("token", self.config.get("wecomaibot_token", ""))
        self.encoding_aes_key = self.config.get(
            "encoding_aes_key", self.config.get("wecomaibot_encoding_aes_key", "")
        )
        self.port = int(self.config["port"])
        self.host = self.config.get("callback_server_host", "0.0.0.0")
        self.bot_name = self.config.get("wecom_ai_bot_name", "")
        self.initial_respond_text = self.config.get(
            "wecomaibot_init_respond_text",
            "",
        )
        self.friend_message_welcome_text = self.config.get(
            "wecomaibot_friend_message_welcome_text",
            "",
        )
        self.unified_webhook_mode = self.config.get("unified_webhook_mode", False)
        self.msg_push_webhook_url = self.config.get("msg_push_webhook_url", "").strip()
        self.only_use_webhook_url_to_send = bool(
            self.config.get("only_use_webhook_url_to_send", False),
        )
        self.long_connection_bot_id = self.config.get(
            "wecomaibot_ws_bot_id", self.config.get("long_connection_bot_id", "")
        )
        self.long_connection_secret = self.config.get(
            "wecomaibot_ws_secret", self.config.get("long_connection_secret", "")
        )
        self.long_connection_ws_url = self.config.get(
            "wecomaibot_ws_url",
            "wss://openws.work.weixin.qq.com",
        )
        self.long_connection_heartbeat_interval = int(
            self.config.get("wecomaibot_heartbeat_interval", 30),
        )

        # 平台元数据
        self.metadata = PlatformMetadata(
            name="wecom_ai_bot",
            description="企业微信智能机器人适配器,支持 HTTP 回调和长连接模式",
            id=self.config.get("id", "wecom_ai_bot"),
            support_proactive_message=bool(self.msg_push_webhook_url),
        )

        self.api_client: WecomAIBotAPIClient | None = None
        self.server: WecomAIBotServer | None = None
        self.long_connection_client: WecomAIBotLongConnectionClient | None = None

        if self.connection_mode == "long_connection":
            if not self.long_connection_bot_id or not self.long_connection_secret:
                logger.warning(
                    "企业微信智能机器人长连接模式缺少 BotID 或 Secret,连接可能失败"
                )
            self.long_connection_client = WecomAIBotLongConnectionClient(
                bot_id=self.long_connection_bot_id,
                secret=self.long_connection_secret,
                ws_url=self.long_connection_ws_url,
                heartbeat_interval=self.long_connection_heartbeat_interval,
                message_handler=self._process_long_connection_payload,
            )
        else:
            self.api_client = WecomAIBotAPIClient(self.token, self.encoding_aes_key)
            self.server = WecomAIBotServer(
                host=self.host,
                port=self.port,
                api_client=self.api_client,
                message_handler=self._process_message,
            )

        # 事件循环和关闭信号
        self.shutdown_event = asyncio.Event()

        # 队列管理器
        self.queue_mgr = WecomAIQueueMgr()

        # 队列监听器
        self.queue_listener = WecomAIQueueListener(
            self.queue_mgr,
            self._handle_queued_message,
        )
        self._stream_plain_cache: dict[str, str] = {}

        self.webhook_client: WecomAIBotWebhookClient | None = None
        if self.msg_push_webhook_url:
            try:
                self.webhook_client = WecomAIBotWebhookClient(
                    self.msg_push_webhook_url,
                )
            except WecomAIBotWebhookError as e:
                logger.error("企业微信消息推送 webhook 配置无效: %s", e)

    async def _handle_queued_message(self, data: dict) -> None:
        """处理队列中的消息,类似webchat的callback"""
        try:
            abm = await self.convert_message(data)
            await self.handle_msg(abm)
        except Exception as e:
            logger.error(f"处理队列消息时发生异常: {e}")

    async def _process_message(
        self,
        message_data: dict[str, Any],
        callback_params: dict[str, str],
    ) -> str | None:
        """处理接收到的消息

        Args:
            message_data: 解密后的消息数据
            callback_params: 回调参数 (nonce, timestamp)

        Returns:
            加密后的响应消息,无需响应时返回 None

        """
        if not self.api_client:
            logger.error("Webhook 消息处理失败: API 客户端未初始化")
            return None
        msgtype = message_data.get("msgtype")
        if not msgtype:
            logger.warning(f"消息类型未知,忽略: {message_data}")
            return None
        session_id = self._extract_session_id(message_data)
        if msgtype in ("text", "image", "mixed"):
            # user sent a text / image / mixed message
            try:
                # create a brand-new unique stream_id for this message session
                stream_id = f"{session_id}_{generate_random_string(10)}"
                await self._enqueue_message(
                    message_data,
                    callback_params,
                    stream_id,
                    session_id,
                )
                self.queue_mgr.set_pending_response(stream_id, callback_params)

                if self.only_use_webhook_url_to_send and self.webhook_client:
                    return None
                if self.initial_respond_text:
                    resp = WecomAIBotStreamMessageBuilder.make_text_stream(
                        stream_id,
                        self.initial_respond_text,
                        False,
                    )
                    return await self.api_client.encrypt_message(
                        resp,
                        callback_params["nonce"],
                        callback_params["timestamp"],
                    )
            except Exception as e:
                logger.error("处理消息时发生异常: %s", e)
                return None
        elif msgtype == "stream":
            # wechat server is requesting for updates of a stream
            stream_id = message_data["stream"]["id"]
            if not self.queue_mgr.has_back_queue(stream_id):
                self._stream_plain_cache.pop(stream_id, None)
                if self.queue_mgr.is_stream_finished(stream_id):
                    logger.debug(
                        f"Stream already finished, returning end message: {stream_id}"
                    )
                else:
                    logger.warning(f"Cannot find back queue for stream_id: {stream_id}")

                # 返回结束标志,告诉微信服务器流已结束
                end_message = WecomAIBotStreamMessageBuilder.make_text_stream(
                    stream_id,
                    "",
                    True,
                )
                resp = await self.api_client.encrypt_message(
                    end_message,
                    callback_params["nonce"],
                    callback_params["timestamp"],
                )
                return resp
            queue = self.queue_mgr.get_or_create_back_queue(stream_id)
            if queue.empty():
                logger.debug(
                    f"No new messages in back queue for stream_id: {stream_id}",
                )
                return None

            # aggregate all delta chains in the back queue
            cached_plain_content = self._stream_plain_cache.get(stream_id, "")
            latest_plain_content = cached_plain_content
            image_base64 = []
            finish = False
            while not queue.empty():
                msg = await queue.get()
                if msg["type"] == "plain":
                    plain_data = msg.get("data") or ""
                    if msg.get("streaming", False):
                        # streaming plain payload is already cumulative
                        cached_plain_content = plain_data
                    else:
                        # segmented non-stream send() pushes plain chunks, needs append
                        cached_plain_content += plain_data
                    latest_plain_content = cached_plain_content
                elif msg["type"] == "image":
                    image_base64.append(msg["image_data"])
                elif msg["type"] == "break":
                    continue
                elif msg["type"] in {"end", "complete"}:
                    # stream end
                    finish = True
                    self.queue_mgr.remove_queues(stream_id, mark_finished=True)
                    self._stream_plain_cache.pop(stream_id, None)
                    break

            logger.debug(
                f"Aggregated content: {latest_plain_content}, image: {len(image_base64)}, finish: {finish}",
            )
            if not finish:
                self._stream_plain_cache[stream_id] = cached_plain_content
            if finish and not latest_plain_content and not image_base64:
                end_message = WecomAIBotStreamMessageBuilder.make_text_stream(
                    stream_id,
                    "",
                    True,
                )
                return await self.api_client.encrypt_message(
                    end_message,
                    callback_params["nonce"],
                    callback_params["timestamp"],
                )
            if latest_plain_content or image_base64:
                msg_items = []
                if finish and image_base64:
                    for img_b64 in image_base64:
                        # get md5 of image
                        img_data = base64.b64decode(img_b64)
                        img_md5 = hashlib.md5(img_data).hexdigest()
                        msg_items.append(
                            {
                                "msgtype": WecomAIBotConstants.MSG_TYPE_IMAGE,
                                "image": {"base64": img_b64, "md5": img_md5},
                            },
                        )
                    image_base64 = []

                plain_message = WecomAIBotStreamMessageBuilder.make_mixed_stream(
                    stream_id,
                    latest_plain_content,
                    msg_items,
                    finish,
                )
                encrypted_message = await self.api_client.encrypt_message(
                    plain_message,
                    callback_params["nonce"],
                    callback_params["timestamp"],
                )
                if encrypted_message:
                    logger.debug(
                        f"Stream message sent successfully, stream_id: {stream_id}",
                    )
                else:
                    logger.error("消息加密失败")
                return encrypted_message
            return None
        elif msgtype == "event":
            event = message_data.get("event")
            if event == "enter_chat" and self.friend_message_welcome_text:
                # 用户进入会话,发送欢迎消息
                try:
                    resp = WecomAIBotStreamMessageBuilder.make_text(
                        self.friend_message_welcome_text,
                    )
                    return await self.api_client.encrypt_message(
                        resp,
                        callback_params["nonce"],
                        callback_params["timestamp"],
                    )
                except Exception as e:
                    logger.error("处理欢迎消息时发生异常: %s", e)
                    return None

    async def _process_long_connection_payload(
        self,
        payload: dict[str, Any],
    ) -> None:
        """处理长连接回调消息｡"""
        cmd = payload.get("cmd")
        headers = payload.get("headers") or {}
        body = payload.get("body") or {}
        req_id = headers.get("req_id")
        if not isinstance(body, dict):
            return

        if cmd == "aibot_msg_callback":
            session_id = self._extract_session_id(body)
            stream_id = f"{session_id}_{generate_random_string(10)}"
            await self._enqueue_message(
                body, {"req_id": req_id or ""}, stream_id, session_id
            )
            self.queue_mgr.set_pending_response(
                stream_id,
                {
                    "req_id": req_id or "",
                    "connection_mode": "long_connection",
                },
            )

            if self.initial_respond_text and req_id:
                await self._send_long_connection_respond_msg(
                    req_id=req_id,
                    body={
                        "msgtype": "stream",
                        "stream": {
                            "id": stream_id,
                            "finish": False,
                            "content": self.initial_respond_text,
                        },
                    },
                )
            return

        if cmd == "aibot_event_callback":
            event = body.get("event") or {}
            event_type = event.get("eventtype")
            if (
                event_type == "enter_chat"
                and self.friend_message_welcome_text
                and req_id
            ):
                await self._send_long_connection_respond_welcome(req_id)
            elif event_type == "disconnected_event":
                logger.warning(
                    "[WecomAI][LongConn] 收到 disconnected_event,旧连接将被关闭"
                )

    async def _send_long_connection_respond_welcome(self, req_id: str) -> bool:
        client = self.long_connection_client
        if not client:
            return False
        return await client.send_command(
            cmd="aibot_respond_welcome_msg",
            req_id=req_id,
            body={
                "msgtype": "text",
                "text": {
                    "content": self.friend_message_welcome_text,
                },
            },
        )

    async def _send_long_connection_respond_msg(
        self,
        req_id: str,
        body: dict[str, Any],
    ) -> bool:
        client = self.long_connection_client
        if not client:
            return False
        return await client.send_command(
            cmd="aibot_respond_msg",
            req_id=req_id,
            body=body,
        )

    def _extract_session_id(self, message_data: dict[str, Any]) -> str:
        """从消息数据中提取会话ID
        群聊使用 chatid,单聊使用 userid
        """
        chattype = message_data.get("chattype", "single")
        if chattype == "group":
            chat_id = message_data.get("chatid", "default_group")
            return format_session_id("wecomai", chat_id)
        else:
            user_id = message_data.get("from", {}).get("userid", "default_user")
            return format_session_id("wecomai", user_id)

    async def _enqueue_message(
        self,
        message_data: dict[str, Any],
        callback_params: dict[str, str],
        stream_id: str,
        session_id: str,
    ) -> None:
        """将消息放入队列进行异步处理"""
        input_queue = self.queue_mgr.get_or_create_queue(stream_id)
        _ = self.queue_mgr.get_or_create_back_queue(stream_id)
        message_payload = {
            "message_data": message_data,
            "callback_params": callback_params,
            "session_id": session_id,
            "stream_id": stream_id,
        }
        await input_queue.put(message_payload)
        logger.debug(f"[WecomAI] 消息已入队: {stream_id}")

    async def convert_message(self, payload: dict) -> AstrBotMessage:
        """转换队列中的消息数据为AstrBotMessage,类似webchat的convert_message"""
        message_data = payload["message_data"]
        session_id = payload["session_id"]
        # callback_params = payload["callback_params"]  # 保留但暂时不使用

        # 解析消息内容
        msgtype = message_data.get("msgtype")
        content = ""
        image_base64 = []

        _img_url_to_process: list[tuple[str, str | None]] = []
        msg_items = []

        if msgtype == WecomAIBotConstants.MSG_TYPE_TEXT:
            content = WecomAIBotMessageParser.parse_text_message(message_data)
        elif msgtype == WecomAIBotConstants.MSG_TYPE_IMAGE:
            image_payload = message_data.get("image", {})
            image_url = image_payload.get("url", "")
            if image_url:
                _img_url_to_process.append((image_url, image_payload.get("aeskey")))
        elif msgtype == WecomAIBotConstants.MSG_TYPE_MIXED:
            # 提取混合消息中的文本内容
            msg_items = WecomAIBotMessageParser.parse_mixed_message(message_data)
            text_parts = []
            for item in msg_items or []:
                if item.get("msgtype") == WecomAIBotConstants.MSG_TYPE_TEXT:
                    text_content = item.get("text", {}).get("content", "")
                    if text_content:
                        text_parts.append(text_content)
                elif item.get("msgtype") == WecomAIBotConstants.MSG_TYPE_IMAGE:
                    image_payload = item.get("image", {})
                    image_url = image_payload.get("url", "")
                    if image_url:
                        _img_url_to_process.append(
                            (image_url, image_payload.get("aeskey"))
                        )
            content = " ".join(text_parts) if text_parts else ""
        else:
            content = f"[{msgtype}消息]"

        # 并行处理图片下载和解密
        if _img_url_to_process:
            tasks = [
                process_encrypted_image(url, aes_key or self.encoding_aes_key)
                for url, aes_key in _img_url_to_process
            ]
            results = await asyncio.gather(*tasks)
            for success, result in results:
                if success:
                    image_base64.append(result)
                else:
                    logger.error(f"处理加密图片失败: {result}")

        # 构建 AstrBotMessage
        abm = AstrBotMessage()
        abm.self_id = self.bot_name
        abm.message_str = content or "[未知消息]"
        abm.message_id = str(uuid.uuid4())
        abm.timestamp = int(time.time())
        abm.raw_message = payload

        # 发送者信息
        abm.sender = MessageMember(
            user_id=message_data.get("from", {}).get("userid", "unknown"),
            nickname=message_data.get("from", {}).get("userid", "unknown"),
        )

        # 消息类型
        abm.type = (
            MessageType.GROUP_MESSAGE
            if message_data.get("chattype") == "group"
            else MessageType.FRIEND_MESSAGE
        )
        abm.session_id = session_id

        # 消息内容
        abm.message = []

        # 处理 At
        if self.bot_name and f"@{self.bot_name}" in abm.message_str:
            abm.message_str = abm.message_str.replace(f"@{self.bot_name}", "").strip()
            abm.message.append(At(qq=self.bot_name, name=self.bot_name))
        abm.message.append(Plain(abm.message_str))
        if image_base64:
            for img_b64 in image_base64:
                abm.message.append(Image.fromBase64(img_b64))

        logger.debug(f"WecomAIAdapter: {abm.message}")
        return abm

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        """通过消息推送 webhook 发送消息｡"""
        if not self.webhook_client:
            logger.warning(
                "主动消息发送失败: 未配置企业微信消息推送 Webhook URL,请前往配置添加｡session_id=%s",
                session.session_id,
            )
            await super().send_by_session(session, message_chain)
            return

        try:
            await self.webhook_client.send_message_chain(message_chain)
        except Exception as e:
            logger.error(
                "企业微信消息推送失败(session=%s): %s",
                session.session_id,
                e,
            )
        await super().send_by_session(session, message_chain)

    def run(self) -> Awaitable[Any]:
        """运行适配器,同时启动HTTP服务器和队列监听器"""

        async def run_both() -> None:
            if self.connection_mode == "long_connection":
                if not self.long_connection_client:
                    raise RuntimeError("长连接客户端未初始化")
                logger.info(
                    "启动企业微信智能机器人长连接模式: %s", self.long_connection_ws_url
                )
                await asyncio.gather(
                    self.long_connection_client.start(),
                    self.queue_listener.run(),
                )
            else:
                # 如果启用统一 webhook 模式,则不启动独立服务器
                webhook_uuid = self.config.get("webhook_uuid")
                if self.unified_webhook_mode and webhook_uuid:
                    log_webhook_info(
                        f"{self.meta().id}(企业微信智能机器人)", webhook_uuid
                    )
                    # 只运行队列监听器
                    await self.queue_listener.run()
                else:
                    if not self.server:
                        raise RuntimeError("Webhook 服务器未初始化")
                    logger.info(
                        "启动企业微信智能机器人适配器,监听 %s:%d", self.host, self.port
                    )
                    # 同时运行HTTP服务器和队列监听器
                    await asyncio.gather(
                        self.server.start_server(),
                        self.queue_listener.run(),
                    )

        return run_both()

    async def webhook_callback(self, request: Any) -> Any:
        """统一 Webhook 回调入口"""
        if self.connection_mode == "long_connection" or not self.server:
            return "long_connection mode does not accept webhook callbacks", 400
        # 根据请求方法分发到不同的处理函数
        if request.method == "GET":
            return await self.server.handle_verify(request)
        else:
            return await self.server.handle_callback(request)

    async def terminate(self) -> None:
        """终止适配器"""
        logger.info("企业微信智能机器人适配器正在关闭...")
        self.shutdown_event.set()
        if self.long_connection_client:
            await self.long_connection_client.shutdown()
        if self.server:
            await self.server.shutdown()

    def meta(self) -> PlatformMetadata:
        """获取平台元数据"""
        return self.metadata

    async def handle_msg(self, message: AstrBotMessage) -> None:
        """处理消息,创建消息事件并提交到事件队列"""
        try:
            message_event = WecomAIBotMessageEvent(
                message_str=message.message_str,
                message_obj=message,
                platform_meta=self.meta(),
                session_id=message.session_id,
                api_client=self.api_client,
                queue_mgr=self.queue_mgr,
                webhook_client=self.webhook_client,
                only_use_webhook_url_to_send=self.only_use_webhook_url_to_send,
                long_connection_sender=self._send_long_connection_respond_msg,
            )
            message_event.is_at_or_wake_command = (
                True  # 企业微信智能机器人默认消息都是 at 或唤醒命令
            )
            message_event.is_wake = True  # 企业微信智能机器人消息默认当做唤醒命令处理

            self.commit_event(message_event)

        except Exception as e:
            logger.error("处理消息时发生异常: %s", e)

    def get_client(self) -> WecomAIBotAPIClient | None:
        """获取 API 客户端"""
        return self.api_client

    def get_server(self) -> WecomAIBotServer | None:
        """获取 HTTP 服务器实例"""
        return self.server
