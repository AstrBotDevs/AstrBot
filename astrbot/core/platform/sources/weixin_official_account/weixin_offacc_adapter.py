import asyncio
import os
import sys
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, cast

import quart
from requests import Response
from wechatpy import WeChatClient, create_reply, parse_message
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
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import convert_audio_to_wav
from astrbot.core.utils.webhook_utils import log_webhook_info

from .weixin_offacc_event import WeixinOfficialAccountPlatformEvent

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class WeixinOfficialAccountServer:
    def __init__(
        self,
        event_queue: asyncio.Queue,
        config: dict,
        user_buffer: dict[Any, dict[str, Any]],
    ) -> None:
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

        self.callback: (
            Callable[[BaseMessage], Coroutine[Any, Any, str | None]] | None
        ) = None
        self.shutdown_event = asyncio.Event()

        self._wx_msg_time_out = 4.0  # 微信服务器要求 5 秒内回复
        self.user_buffer: dict[str, dict[str, Any]] = user_buffer  # from_user -> state
        self.active_send_mode = False  # 是否启用主动发送模式，启用后 callback 将直接返回回复内容，无需等待微信回调

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

    def _maybe_encrypt(self, xml: str, nonce: str | None, timestamp: str | None) -> str:
        if xml and "<Encrypt>" not in xml and nonce and timestamp:
            return self.crypto.encrypt_message(xml, nonce, timestamp)
        return xml or "success"

    def _preview(self, msg: BaseMessage, limit: int = 24) -> str:
        """生成消息预览文本，供占位符使用"""
        if isinstance(msg, TextMessage):
            t = cast(str, msg.content).strip()
            return (t[:limit] + "...") if len(t) > limit else (t or "空消息")
        if isinstance(msg, ImageMessage):
            return "图片"
        if isinstance(msg, VoiceMessage):
            return "语音"
        return getattr(msg, "type", "未知消息")

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

            if not self.callback:
                return "success"

            # by pass passive reply logic and return active reply directly.
            if self.active_send_mode:
                result_xml = await self.callback(msg)
                if not result_xml:
                    return "success"
                if isinstance(result_xml, str):
                    return result_xml

            # passive reply
            from_user = str(getattr(msg, "source", ""))
            msg_id = str(cast(str | int, getattr(msg, "id", "")))
            state = self.user_buffer.get(from_user)

            def _reply_text(text: str) -> str:
                reply_obj = create_reply(text, msg)
                reply_xml = reply_obj if isinstance(reply_obj, str) else str(reply_obj)
                return self._maybe_encrypt(reply_xml, nonce, timestamp)

            # if in cached state, return cached result or placeholder
            if state:
                logger.debug(f"用户消息缓冲状态: user={from_user} state={state}")
                cached = state.get("cached_xml")
                # send one cached each time, if cached is empty after pop, remove the buffer
                if cached and len(cached) > 0:
                    logger.info(f"wx buffer hit on trigger: user={from_user}")
                    cached_xml = cached.pop(0)
                    if len(cached) == 0:
                        self.user_buffer.pop(from_user, None)
                        return _reply_text(cached_xml)
                    else:
                        return _reply_text(
                            cached_xml
                            + "\n【后续消息还在缓冲中，回复任意文字继续获取】"
                        )

                task: asyncio.Task | None = cast(asyncio.Task | None, state.get("task"))
                placeholder = (
                    f"【正在思考'{state.get('preview', '...')}'中，已思考"
                    f"{int(time.monotonic() - state.get('started_at', time.monotonic()))}s，回复任意文字尝试获取回复】"
                )

                # same msgid => WeChat retry: wait a little; new msgid => user trigger: just placeholder
                if task and state.get("msg_id") == msg_id:
                    done, _ = await asyncio.wait(
                        {task},
                        timeout=self._wx_msg_time_out,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if done:
                        try:
                            cached = state.get("cached_xml")
                            # send one cached each time, if cached is empty after pop, remove the buffer
                            if cached and len(cached) > 0:
                                logger.info(
                                    f"wx buffer hit on retry window: user={from_user}"
                                )
                                cached_xml = cached.pop(0)
                                if len(cached) == 0:
                                    self.user_buffer.pop(from_user, None)
                                    logger.debug(
                                        f"wx finished message sending in passive window: user={from_user} msg_id={msg_id} "
                                    )
                                    return _reply_text(cached_xml)
                                else:
                                    logger.debug(
                                        f"wx finished message sending in passive window but not final: user={from_user} msg_id={msg_id} "
                                    )
                                    return _reply_text(
                                        cached_xml
                                        + "\n【后续消息还在缓冲中，回复任意文字继续获取】"
                                    )
                            logger.info(
                                f"wx finished in window but not final; return placeholder: user={from_user} msg_id={msg_id} "
                            )
                            return _reply_text(placeholder)
                        except Exception:
                            logger.critical(
                                "wx task failed in passive window", exc_info=True
                            )
                            self.user_buffer.pop(from_user, None)
                            return _reply_text("处理消息失败，请稍后再试。")

                    logger.info(
                        f"wx passive window timeout: user={from_user} msg_id={msg_id}"
                    )
                    return _reply_text(placeholder)

                logger.debug(f"wx trigger while thinking: user={from_user}")
                return _reply_text(placeholder)

            # create new trigger when state is empty, and store state in buffer
            logger.debug(f"wx new trigger: user={from_user} msg_id={msg_id}")
            preview = self._preview(msg)
            placeholder = (
                f"【正在思考'{preview}'中，已思考0s，回复任意文字尝试获取回复】"
            )
            logger.info(
                f"wx start task: user={from_user} msg_id={msg_id} preview={preview}"
            )

            self.user_buffer[from_user] = state = {
                "msg_id": msg_id,
                "preview": preview,
                "task": None,  # set later after task created
                "cached_xml": [],  # for passive reply
                "started_at": time.monotonic(),
            }
            self.user_buffer[from_user]["task"] = task = asyncio.create_task(
                self.callback(msg)
            )

            # immediate return if done
            done, _ = await asyncio.wait(
                {task},
                timeout=self._wx_msg_time_out,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if done:
                try:
                    cached = state.get("cached_xml", None)
                    # send one cached each time, if cached is empty after pop, remove the buffer
                    if cached and len(cached) > 0:
                        logger.info(f"wx buffer hit immediately: user={from_user}")
                        cached_xml = cached.pop(0)
                        if len(cached) == 0:
                            self.user_buffer.pop(from_user, None)
                            return _reply_text(cached_xml)
                        else:
                            return _reply_text(
                                cached_xml
                                + "\n【后续消息还在缓冲中，回复任意文字继续获取】"
                            )
                    logger.info(
                        f"wx not finished in first window; return placeholder: user={from_user} msg_id={msg_id} "
                    )
                    return _reply_text(placeholder)
                except Exception:
                    logger.critical("wx task failed in first window", exc_info=True)
                    self.user_buffer.pop(from_user, None)
                    return _reply_text("处理消息失败，请稍后再试。")

            logger.info(f"wx first window timeout: user={from_user} msg_id={msg_id}")
            return _reply_text(placeholder)

    async def start_polling(self) -> None:
        logger.info(
            f"将在 {self.callback_server_host}:{self.port} 端口启动 微信公众平台 适配器。",
        )
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self) -> None:
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

        self.user_buffer: dict[str, dict[str, Any]] = {}  # from_user -> state
        self.server = WeixinOfficialAccountServer(
            self._event_queue, self.config, self.user_buffer
        )

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
                    return None

                msg_id = str(cast(str | int, msg.id))
                future = self.wexin_event_workers.get(msg_id)
                if future:
                    logger.debug(f"duplicate message id checked: {msg.id}")
                else:
                    future = asyncio.get_event_loop().create_future()
                    self.wexin_event_workers[msg_id] = future
                    await self.convert_message(msg, future)
                    # I love shield so much!
                    result = await asyncio.wait_for(
                        asyncio.shield(future),
                        180,
                    )  # wait for 180s
                logger.debug(f"Got future result: {result}")
                return result
            except asyncio.TimeoutError:
                logger.info(f"callback 处理消息超时: message_id={msg.id}")
                return create_reply("处理消息超时，请稍后再试。", msg)
            except Exception as e:
                logger.error(f"转换消息时出现异常: {e}")
            finally:
                self.wexin_event_workers.pop(str(cast(str | int, msg.id)), None)

        self.server.callback = callback
        self.server.active_send_mode = self.active_send_mode

    @override
    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        await super().send_by_session(session, message_chain)

    @override
    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            "weixin_official_account",
            "微信公众平台 适配器",
            id=self.config.get("id", "weixin_official_account"),
            support_streaming_message=False,
            support_proactive_message=False,
        )

    @override
    async def run(self) -> None:
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
            temp_dir = get_astrbot_temp_path()
            path = os.path.join(temp_dir, f"weixin_offacc_{msg.media_id}.amr")
            with open(path, "wb") as f:
                f.write(resp.content)

            try:
                path_wav = os.path.join(
                    temp_dir,
                    f"weixin_offacc_{msg.media_id}.wav",
                )
                path_wav = await convert_audio_to_wav(path, path_wav)
            except Exception as e:
                logger.error(
                    f"转换音频失败: {e}。如果没有安装 ffmpeg 请先安装。",
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

    async def handle_msg(self, message: AstrBotMessage) -> None:
        buffer = self.user_buffer.get(message.sender.user_id, None)
        if buffer is None:
            logger.critical(
                f"用户消息未找到缓冲状态，无法处理消息: user={message.sender.user_id} message_id={message.message_id}"
            )
            return
        message_event = WeixinOfficialAccountPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
            message_out=buffer,
        )
        self.commit_event(message_event)

    def get_client(self) -> WeChatClient:
        return self.client

    async def terminate(self) -> None:
        self.server.shutdown_event.set()
        try:
            await self.server.server.shutdown()
        except Exception as _:
            pass
        logger.info("微信公众平台 适配器已被关闭")
