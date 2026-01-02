import asyncio
import sys
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, cast

import quart
from requests import Response
from wechatpy import WeChatClient, parse_message
from wechatpy.crypto import WeChatCrypto
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.messages import BaseMessage, ImageMessage, TextMessage, VoiceMessage
from wechatpy.utils import check_signature

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Plain, Record
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core import logger
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.webhook_utils import log_webhook_info

from .weixin_offacc_event import WeixinOfficialAccountPlatformEvent

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class WeixinOfficialAccountServer:
    def __init__(self, event_queue: asyncio.Queue, config: dict):
        self.server = quart.Quart(__name__)
        self.port = int(cast(int | str, config.get("port")))
        self.callback_server_host = config.get("callback_server_host", "0.0.0.0")
        self.token = config.get("token")
        self.encoding_aes_key = config.get("encoding_aes_key")
        self.appid = config.get("appid")
        self.server.add_url_rule(
            "/callback/command",
            view_func=self.verify,
            methods=["GET"],
        )
        self.server.add_url_rule(
            "/callback/command",
            view_func=self.callback_command,
            methods=["POST"],
        )
        self.crypto = WeChatCrypto(self.token, self.encoding_aes_key, self.appid)

        self.event_queue = event_queue

        self.callback: Callable[[BaseMessage], Awaitable[None]] | None = None
        self.shutdown_event = asyncio.Event()

    async def verify(self):
        """内部服务器的 GET 验证入口"""
        return await self.handle_verify(quart.request)

    async def handle_verify(self, request) -> str:
        """处理验证请求，可被统一 webhook 入口复用

        Args:
            request: Quart 请求对象

        Returns:
            验证响应
        """
        logger.info(f"验证请求有效性: {request.args}")

        args = request.args
        if not args.get("signature", None):
            logger.error("未知的响应，请检查回调地址是否填写正确。")
            return "err"
        try:
            check_signature(
                self.token,
                args.get("signature"),
                args.get("timestamp"),
                args.get("nonce"),
            )
            logger.info("验证请求有效性成功。")
            return args.get("echostr", "empty")
        except InvalidSignatureException:
            logger.error("验证请求有效性失败，签名异常，请检查配置。")
            return "err"

    async def callback_command(self):
        """内部服务器的 POST 回调入口"""
        return await self.handle_callback(quart.request)

    async def handle_callback(self, request) -> str:
        """处理回调请求，可被统一 webhook 入口复用

        Args:
            request: Quart 请求对象

        Returns:
            响应内容
        """
        data = await request.get_data()
        msg_signature = request.args.get("msg_signature")
        timestamp = request.args.get("timestamp")
        nonce = request.args.get("nonce")
        try:
            xml = self.crypto.decrypt_message(data, msg_signature, timestamp, nonce)
        except InvalidSignatureException:
            logger.error("解密失败，签名异常，请检查配置。")
            raise
        else:
            msg = parse_message(xml)
            if not msg:
                logger.error("解析失败。msg为None。")
                raise
            logger.info(f"解析成功: {msg}")

            if self.callback:
                result_xml = await self.callback(msg)
                if not result_xml:
                    return "success"
                if isinstance(result_xml, str):
                    return result_xml

        return "success"

    async def start_polling(self):
        logger.info(
            f"将在 {self.callback_server_host}:{self.port} 端口启动 微信公众平台 适配器。",
        )
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()


@register_platform_adapter(
    "weixin_official_account", "微信公众平台 适配器", support_streaming_message=False
)
class WeixinOfficialAccountPlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settingss = platform_settings
        self.client_self_id = uuid.uuid4().hex[:8]
        self.api_base_url = platform_config.get(
            "api_base_url",
            "https://api.weixin.qq.com/cgi-bin/",
        )
        self.active_send_mode = self.config.get("active_send_mode", False)
        self.unified_webhook_mode = platform_config.get("unified_webhook_mode", False)

        if not self.api_base_url:
            self.api_base_url = "https://api.weixin.qq.com/cgi-bin/"

        self.api_base_url = self.api_base_url.removesuffix("/")
        if not self.api_base_url.endswith("/cgi-bin"):
            self.api_base_url += "/cgi-bin"

        if not self.api_base_url.endswith("/"):
            self.api_base_url += "/"

        self.server = WeixinOfficialAccountServer(self._event_queue, self.config)

        self.client = WeChatClient(
            self.config["appid"].strip(),
            self.config["secret"].strip(),
        )

        self.client.__setattr__("API_BASE_URL", self.api_base_url)

        # 微信公众号必须 5 秒内进行回复，否则会重试 3 次，我们需要对其进行消息排重
        # msgid -> Future
        self.wexin_event_workers: dict[str, asyncio.Future] = {}

        async def callback(msg: BaseMessage):
            try:
                if self.active_send_mode:
                    await self.convert_message(msg, None)
                else:
                    if str(msg.id) in self.wexin_event_workers:
                        future = self.wexin_event_workers[str(cast(str | int, msg.id))]
                        logger.debug(f"duplicate message id checked: {msg.id}")
                    else:
                        future = asyncio.get_event_loop().create_future()
                        self.wexin_event_workers[str(cast(str | int, msg.id))] = future
                        await self.convert_message(msg, future)
                    # I love shield so much!
                    result = await asyncio.wait_for(
                        asyncio.shield(future),
                        60,
                    )  # wait for 60s
                    logger.debug(f"Got future result: {result}")
                    self.wexin_event_workers.pop(str(cast(str | int, msg.id)), None)
                    return result  # xml. see weixin_offacc_event.py
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"转换消息时出现异常: {e}")

        self.server.callback = callback

    @override
    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ):
        await super().send_by_session(session, message_chain)

    @override
    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            "weixin_official_account",
            "微信公众平台 适配器",
            id=self.config.get("id", "weixin_official_account"),
            support_streaming_message=False,
        )

    @override
    async def run(self):
        # 如果启用统一 webhook 模式，则不启动独立服务器
        webhook_uuid = self.config.get("webhook_uuid")
        if self.unified_webhook_mode and webhook_uuid:
            log_webhook_info(f"{self.meta().id}(微信公众平台)", webhook_uuid)
            # 保持运行状态，等待 shutdown
            await self.server.shutdown_event.wait()
        else:
            await self.server.start_polling()

    async def webhook_callback(self, request: Any) -> Any:
        """统一 Webhook 回调入口"""
        # 根据请求方法分发到不同的处理函数
        if request.method == "GET":
            return await self.server.handle_verify(request)
        else:
            return await self.server.handle_callback(request)

    async def convert_message(
        self,
        msg,
        future: asyncio.Future | None = None,
    ) -> AstrBotMessage | None:
        abm = AstrBotMessage()
        if isinstance(msg, TextMessage):
            abm.message_str = cast(str, msg.content)
            abm.self_id = str(msg.target)
            abm.message = [Plain(cast(str, msg.content))]
            abm.type = MessageType.FRIEND_MESSAGE
            abm.sender = MessageMember(
                cast(str, msg.source),
                cast(str, msg.source),
            )
            abm.message_id = str(cast(str | int, msg.id))
            abm.timestamp = cast(int, msg.time)
            abm.session_id = abm.sender.user_id
        elif msg.type == "image":
            assert isinstance(msg, ImageMessage)
            abm.message_str = "[图片]"
            abm.self_id = str(msg.target)
            abm.message = [Image(file=cast(str, msg.image), url=cast(str, msg.image))]
            abm.type = MessageType.FRIEND_MESSAGE
            abm.sender = MessageMember(
                cast(str, msg.source),
                cast(str, msg.source),
            )
            abm.message_id = str(cast(str | int, msg.id))
            abm.timestamp = cast(int, msg.time)
            abm.session_id = abm.sender.user_id
        elif msg.type == "voice":
            assert isinstance(msg, VoiceMessage)

            resp: Response = await asyncio.get_event_loop().run_in_executor(
                None,
                self.client.media.download,
                msg.media_id,
            )
            path = f"data/temp/wecom_{msg.media_id}.amr"
            with open(path, "wb") as f:
                f.write(resp.content)

            try:
                from pydub import AudioSegment

                path_wav = f"data/temp/wecom_{msg.media_id}.wav"
                audio = AudioSegment.from_file(path)
                audio.export(path_wav, format="wav")
            except Exception as e:
                logger.error(
                    f"转换音频失败: {e}。如果没有安装 pydub 和 ffmpeg 请先安装。",
                )
                path_wav = path
                return

            abm.message_str = ""
            abm.self_id = str(msg.target)
            abm.message = [Record(file=path_wav, url=path_wav)]
            abm.type = MessageType.FRIEND_MESSAGE
            abm.sender = MessageMember(
                cast(str, msg.source),
                cast(str, msg.source),
            )
            abm.message_id = str(cast(str | int, msg.id))
            abm.timestamp = cast(int, msg.time)
            abm.session_id = abm.sender.user_id
        else:
            logger.warning(f"暂未实现的事件: {msg.type}")
            if future:
                future.set_result(None)
            return
        # 很不优雅 :(
        abm.raw_message = {
            "message": msg,
            "future": future,
            "active_send_mode": self.active_send_mode,
        }
        logger.info(f"abm: {abm}")
        await self.handle_msg(abm)

    async def handle_msg(self, message: AstrBotMessage):
        message_event = WeixinOfficialAccountPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )
        self.commit_event(message_event)

    def get_client(self) -> WeChatClient:
        return self.client

    async def terminate(self):
        self.server.shutdown_event.set()
        try:
            await self.server.server.shutdown()
        except Exception as _:
            pass
        logger.info("微信公众平台 适配器已被关闭")
