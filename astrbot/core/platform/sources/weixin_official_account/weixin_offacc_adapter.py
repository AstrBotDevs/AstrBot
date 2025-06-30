import sys
import uuid
import asyncio
import quart

from astrbot.api.platform import (
    Platform,
    AstrBotMessage,
    MessageMember,
    PlatformMetadata,
    MessageType,
)
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Image, Record
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.api.platform import register_platform_adapter
from astrbot.core import logger
from requests import Response

from wechatpy.utils import check_signature
from wechatpy.crypto import WeChatCrypto
from wechatpy import WeChatClient
from wechatpy.messages import TextMessage, ImageMessage, VoiceMessage, BaseMessage
from wechatpy.exceptions import InvalidSignatureException
from wechatpy import parse_message
from .weixin_offacc_event import WeixinOfficialAccountPlatformEvent

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class WecomServer:
    def __init__(self, event_queue: asyncio.Queue, config: dict):
        self.server = quart.Quart(__name__)
        self.port = int(config.get("port"))
        self.callback_server_host = config.get("callback_server_host", "0.0.0.0")
        self.token = config.get("token")
        self.encoding_aes_key = config.get("encoding_aes_key")
        self.appid = config.get("appid")
        self.server.add_url_rule(
            "/callback/command", view_func=self.verify, methods=["GET"]
        )
        self.server.add_url_rule(
            "/callback/command", view_func=self.callback_command, methods=["POST"]
        )
        self.crypto = WeChatCrypto(self.token, self.encoding_aes_key, self.appid)

        self.event_queue = event_queue

        self.callback = None
        self.shutdown_event = asyncio.Event()

    async def verify(self):
        logger.info(f"验证请求有效性: {quart.request.args}")

        args = quart.request.args
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
        data = await quart.request.get_data()
        msg_signature = quart.request.args.get("msg_signature")
        timestamp = quart.request.args.get("timestamp")
        nonce = quart.request.args.get("nonce")
        try:
            xml = self.crypto.decrypt_message(data, msg_signature, timestamp, nonce)
        except InvalidSignatureException:
            logger.error("解密失败，签名异常，请检查配置。")
            raise
        else:
            msg = parse_message(xml)
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
            f"将在 {self.callback_server_host}:{self.port} 端口启动 微信公众平台 适配器。"
        )
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()


@register_platform_adapter("weixin_official_account", "微信公众平台 适配器")
class WeixinOfficialAccountPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)
        self.config = platform_config
        self.settingss = platform_settings
        self.client_self_id = uuid.uuid4().hex[:8]
        self.api_base_url = platform_config.get(
            "api_base_url", "https://api.weixin.qq.com/cgi-bin/"
        )
        self.active_send_mode = self.config.get("active_send_mode", False)

        if not self.api_base_url:
            self.api_base_url = "https://api.weixin.qq.com/cgi-bin/"

        if self.api_base_url.endswith("/"):
            self.api_base_url = self.api_base_url[:-1]
        if not self.api_base_url.endswith("/cgi-bin"):
            self.api_base_url += "/cgi-bin"

        if not self.api_base_url.endswith("/"):
            self.api_base_url += "/"

        self.server = WecomServer(self._event_queue, self.config)

        self.client = WeChatClient(
            self.config["appid"].strip(),
            self.config["secret"].strip(),
        )

        self.client.API_BASE_URL = self.api_base_url

        # 微信公众号必须 5 秒内进行回复，否则会重试 3 次，我们需要对其进行消息排重
        # msgid -> Future
        self.wexin_event_workers: dict[str, asyncio.Future] = {}

        async def callback(msg: BaseMessage):
            try:
                if self.active_send_mode:
                    await self.convert_message(msg, None)
                else:
                    if msg.id in self.wexin_event_workers:
                        future = self.wexin_event_workers[msg.id]
                        logger.debug(f"duplicate message id checked: {msg.id}")
                    else:
                        future = asyncio.get_event_loop().create_future()
                        self.wexin_event_workers[msg.id] = future
                        await self.convert_message(msg, future)
                    # I love shield so much!
                    result = await asyncio.wait_for(asyncio.shield(future), 60)  # wait for 60s
                    logger.debug(f"Got future result: {result}")
                    self.wexin_event_workers.pop(msg.id, None)
                    return result  # xml. see weixin_offacc_event.py
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"转换消息时出现异常: {e}")

        self.server.callback = callback

    @override
    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        await super().send_by_session(session, message_chain)

    @override
    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            "weixin_official_account",
            "微信公众平台 适配器",
        )

    @override
    async def run(self):
        await self.server.start_polling()

    async def convert_message(
        self, msg, future: asyncio.Future = None
    ) -> AstrBotMessage | None:
        abm = AstrBotMessage()
        if isinstance(msg, TextMessage):
            abm.message_str = msg.content
            abm.self_id = str(msg.target)
            abm.message = [Plain(msg.content)]
            abm.type = MessageType.FRIEND_MESSAGE
            abm.sender = MessageMember(
                msg.source,
                msg.source,
            )
            abm.message_id = msg.id
            abm.timestamp = msg.time
            abm.session_id = abm.sender.user_id
        elif msg.type == "image":
            assert isinstance(msg, ImageMessage)
            abm.message_str = "[图片]"
            abm.self_id = str(msg.target)
            abm.message = [Image(file=msg.image, url=msg.image)]
            abm.type = MessageType.FRIEND_MESSAGE
            abm.sender = MessageMember(
                msg.source,
                msg.source,
            )
            abm.message_id = msg.id
            abm.timestamp = msg.time
            abm.session_id = abm.sender.user_id
        elif msg.type == "voice":
            assert isinstance(msg, VoiceMessage)

            resp: Response = await asyncio.get_event_loop().run_in_executor(
                None, self.client.media.download, msg.media_id
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
                    f"转换音频失败: {e}。如果没有安装 pydub 和 ffmpeg 请先安装。"
                )
                path_wav = path
                return

            abm.message_str = ""
            abm.self_id = str(msg.target)
            abm.message = [Record(file=path_wav, url=path_wav)]
            abm.type = MessageType.FRIEND_MESSAGE
            abm.sender = MessageMember(
                msg.source,
                msg.source,
            )
            abm.message_id = msg.id
            abm.timestamp = msg.time
            abm.session_id = abm.sender.user_id
        else:
            logger.warning(f"暂未实现的事件: {msg.type}")
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
        logger.info("微信公众平台 适配器已被优雅地关闭")
