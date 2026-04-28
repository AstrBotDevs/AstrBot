import asyncio
import os
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import aiofiles
import quart
from wechatpy.enterprise import WeChatClient, parse_message
from wechatpy.enterprise.crypto import WeChatCrypto
from wechatpy.enterprise.messages import ImageMessage, TextMessage, VoiceMessage
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.messages import BaseMessage

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

from .wecom_event import WecomPlatformEvent
from .wecom_kf import WeChatKF
from .wecom_kf_message import WeChatKFMessage

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class WecomServer:
    def __init__(self, event_queue: asyncio.Queue, config: dict[str, Any]) -> None:
        self.server = quart.Quart(__name__)
        # Use required access to ensure mypy/ty don't treat as Optional
        # and normalize values with explicit conversions.
        self.port = int(str(config["port"]))
        self.callback_server_host = str(config.get("callback_server_host", "0.0.0.0"))
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
        self.event_queue = event_queue

        # required keys, normalize to str
        token = str(config["token"]).strip()
        encoding_aes_key = str(config["encoding_aes_key"]).strip()
        corpid = str(config["corpid"]).strip()
        self.crypto = WeChatCrypto(token, encoding_aes_key, corpid)

        # callback expects BaseMessage
        self.callback: Callable[[BaseMessage], Awaitable[None]] | None = None
        self.shutdown_event = asyncio.Event()

    async def verify(self):
        """内部服务器的 GET 验证入口"""
        return await self.handle_verify(quart.request)

    async def handle_verify(self, request) -> str:
        """处理验证请求,可被统一 webhook 入口复用"""
        logger.info(f"验证请求有效性: {request.args}")
        args = request.args
        try:
            # wechatpy expects strings; args.get() returns Optional[str]
            echo_str = self.crypto.check_signature(
                args.get("msg_signature"),
                args.get("timestamp"),
                args.get("nonce"),
                args.get("echostr"),
            )
            logger.info("验证请求有效性成功｡")
            # check_signature returns str in wechatpy; ensure return type is str
            return str(echo_str)
        except InvalidSignatureException:
            logger.error("验证请求有效性失败,签名异常,请检查配置｡")
            raise

    async def callback_command(self):
        """内部服务器的 POST 回调入口"""
        return await self.handle_callback(quart.request)

    async def handle_callback(self, request) -> str:
        """处理回调请求,可被统一 webhook 入口复用"""
        data = await request.get_data()
        msg_signature = request.args.get("msg_signature")
        timestamp = request.args.get("timestamp")
        nonce = request.args.get("nonce")
        try:
            # decrypt_message may return bytes/str; pass typed values
            xml = self.crypto.decrypt_message(data, msg_signature, timestamp, nonce)
        except InvalidSignatureException:
            logger.error("解密失败,签名异常,请检查配置｡")
            raise
        else:
            # parse_message returns a BaseMessage (wechatpy). Keep a typed reference.
            msg: BaseMessage = parse_message(xml)  # type: ignore
            logger.info(f"解析成功: {msg}")
            if self.callback:
                await self.callback(msg)
        return "success"

    async def start_polling(self) -> None:
        logger.info(
            f"将在 {self.callback_server_host}:{self.port} 端口启动 企业微信 适配器｡",
        )
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self) -> None:
        await self.shutdown_event.wait()


@register_platform_adapter("wecom", "wecom 适配器", support_streaming_message=False)
class WecomPlatformAdapter(Platform):
    WECHAT_KF_TEXT_CONTENT_DEDUP_TTL_SECONDS = 15

    def __init__(
        self,
        platform_config: dict[str, Any],
        platform_settings: dict[str, Any],
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        # prefer required access for fields we expect to exist
        self.settingss = platform_settings
        api_base_url = platform_config.get(
            "api_base_url",
            "https://qyapi.weixin.qq.com/cgi-bin/",
        )
        self.unified_webhook_mode = bool(
            platform_config.get("unified_webhook_mode", False),
        )
        if not api_base_url:
            api_base_url = "https://qyapi.weixin.qq.com/cgi-bin/"
        # normalize url consistently
        api_base_url = api_base_url.removesuffix("/")
        if not api_base_url.endswith("/cgi-bin"):
            api_base_url += "/cgi-bin"
        if not api_base_url.endswith("/"):
            api_base_url += "/"
        self.api_base_url = api_base_url

        # require config keys to avoid Optional types and normalize them
        corpid = str(self.config["corpid"]).strip()
        secret = str(self.config["secret"]).strip()

        # server expects port and other required keys
        self.server = WecomServer(self._event_queue, self.config)
        self.agent_id: str | None = None
        self._wechat_kf_seen_text_messages: dict[str, float] = {}

        # normalize kf handling: use explicit check and typed assignments
        self.kf_name = self.config.get("kf_name", None)
        if self.kf_name:
            self.wechat_kf_api = WeChatKF(client=self.client)
            self.wechat_kf_message_api = WeChatKFMessage(self.client)
            # attach runtime attributes onto client for use at runtime
            # assign runtime-only attributes directly; signal to type-checkers that these attributes may not be
            # statically declared on WeChatClient with a precise attr-defined ignore instead of blanket ignores.
            self.client.kf = self.wechat_kf_api  # type: ignore
            self.client.kf_message = self.wechat_kf_message_api  # type: ignore
        # ensure API_BASE_URL is set as string (assign directly, it's a runtime extension)
        self.client.API_BASE_URL = self.api_base_url  # type: ignore

        async def callback(msg: BaseMessage) -> None:
            # parse_message may yield messages with .type and ._data; normalize _data to dict
            msg_data = getattr(msg, "_data", {}) or {}
            if not isinstance(msg_data, dict):
                msg_data = {}

            # handle wechat kf special event type
            if (
                getattr(msg, "type", "") == "unknown"
                and msg_data.get("Event") == "kf_msg_or_event"
            ):

                def get_latest_msg_item() -> dict | None:
                    token = str(msg_data.get("Token", "") or "")
                    kfid = str(msg_data.get("OpenKfId", "") or "")
                    has_more = 1
                    ret: dict[str, Any] = {}
                    while has_more:
                        # sync_msg is synchronous in this wrapper; run in executor
                        ret = self.wechat_kf_api.sync_msg(token, kfid)
                        has_more = ret.get("has_more", 0)
                    msg_list = ret.get("msg_list", [])
                    if msg_list:
                        return msg_list[-1]
                    return None

                msg_new = await asyncio.get_running_loop().run_in_executor(
                    None,
                    get_latest_msg_item,
                )
                if msg_new:
                    await self.convert_wechat_kf_message(msg_new)
                return
            await self.convert_message(msg)

        self.server.callback = callback

    def _is_duplicate_wechat_kf_text_message(self, session_id: str, text: str) -> bool:
        normalized_text = text.strip()
        if not normalized_text:
            return False

        now = time.monotonic()
        expired_keys = [
            key
            for key, expires_at in self._wechat_kf_seen_text_messages.items()
            if expires_at <= now
        ]
        for key in expired_keys:
            self._wechat_kf_seen_text_messages.pop(key, None)

        dedup_key = f"{session_id}:{normalized_text}"
        if dedup_key in self._wechat_kf_seen_text_messages:
            return True
        self._wechat_kf_seen_text_messages[dedup_key] = (
            now + self.WECHAT_KF_TEXT_CONTENT_DEDUP_TTL_SECONDS
        )
        return False

    @override
    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        if hasattr(self.client, "kf_message"):
            logger.warning("企业微信客服模式不支持 send_by_session 主动发送｡")
            await super().send_by_session(session, message_chain)
            return
        if not self.agent_id:
            logger.warning(
                f"send_by_session 失败:无法为会话 {session.session_id} 推断 agent_id｡",
            )
            await super().send_by_session(session, message_chain)
            return
        message_obj = AstrBotMessage()
        message_obj.self_id = self.agent_id
        message_obj.session_id = session.session_id
        message_obj.type = session.message_type
        message_obj.sender = MessageMember(session.session_id, session.session_id)
        message_obj.message = []
        message_obj.message_str = ""
        message_obj.message_id = uuid.uuid4().hex
        message_obj.raw_message = {"_proactive_send": True}
        event = WecomPlatformEvent(
            message_str=message_obj.message_str,
            message_obj=message_obj,
            platform_meta=self.meta(),
            session_id=message_obj.session_id,
            client=self.client,
        )
        await event.send(message_chain)
        await super().send_by_session(session, message_chain)

    @override
    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            "wecom",
            "wecom 适配器",
            id=self.config.get("id", "wecom"),
            support_streaming_message=False,
            support_proactive_message=False,
        )

    @override
    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        if getattr(self, "kf_name", None):
            try:
                # run in executor to avoid blocking loop for sync API
                acc_list = (
                    await loop.run_in_executor(
                        None,
                        self.wechat_kf_api.get_account_list,
                    )
                ).get("account_list", [])
                logger.debug(f"获取到微信客服列表: {acc_list!s}")
                for acc in acc_list:
                    name = acc.get("name", None)
                    if name != self.kf_name:
                        continue
                    open_kfid = acc.get("open_kfid", None)
                    if not open_kfid:
                        logger.error("获取微信客服失败,open_kfid 为空｡")
                        continue
                    logger.debug(f"Found open_kfid: {open_kfid!s}")
                    kf_url = (
                        await loop.run_in_executor(
                            None,
                            self.wechat_kf_api.add_contact_way,
                            open_kfid,
                            "astrbot_placeholder",
                        )
                    ).get("url", "")
                    logger.info(
                        f"请打开以下链接,在微信扫码以获取客服微信: https://api.cl2wm.cn/api/qrcode/code?text={kf_url}",
                    )
            except Exception as e:
                logger.error(e)
        webhook_uuid = self.config.get("webhook_uuid")
        if self.unified_webhook_mode and webhook_uuid:
            log_webhook_info(f"{self.meta().id}(企业微信)", webhook_uuid)
            await self.server.shutdown_event.wait()
        else:
            await self.server.start_polling()

    async def webhook_callback(self, request: Any) -> Any:
        """统一 Webhook 回调入口"""
        if request.method == "GET":
            return await self.server.handle_verify(request)
        return await self.server.handle_callback(request)

    async def convert_message(self, msg: BaseMessage) -> AstrBotMessage | None:
        # ensure msg is treated as BaseMessage for typing; normalize fields using str()/int()
        abm = AstrBotMessage()
        if isinstance(msg, TextMessage):
            # TextMessage.content, .agent, .source, .id, .time
            abm.message_str = str(getattr(msg, "content", "") or "")
            abm.self_id = str(getattr(msg, "agent", "") or "")
            abm.message = [Plain(str(getattr(msg, "content", "") or ""))]
            abm.type = MessageType.FRIEND_MESSAGE
            abm.sender = MessageMember(
                str(getattr(msg, "source", "") or ""),
                str(getattr(msg, "source", "") or ""),
            )
            abm.message_id = str(getattr(msg, "id", "") or "")
            # normalize timestamp: allow numeric or string
            abm.timestamp = int(str(getattr(msg, "time", 0) or 0))
            abm.session_id = abm.sender.user_id
            abm.raw_message = msg
        elif isinstance(msg, ImageMessage):
            abm.message_str = "[图片]"
            abm.self_id = str(getattr(msg, "agent", "") or "")
            image_url = str(getattr(msg, "image", "") or "")
            abm.message = [Image(file=image_url, url=image_url)]
            abm.type = MessageType.FRIEND_MESSAGE
            abm.sender = MessageMember(
                str(getattr(msg, "source", "") or ""),
                str(getattr(msg, "source", "") or ""),
            )
            abm.message_id = str(getattr(msg, "id", "") or "")
            abm.timestamp = int(str(getattr(msg, "time", 0) or 0))
            abm.session_id = abm.sender.user_id
            abm.raw_message = msg
        elif isinstance(msg, VoiceMessage):
            resp = await asyncio.get_running_loop().run_in_executor(
                None,
                self.client.media.download,
                str(getattr(msg, "media_id", "") or ""),
            )
            temp_dir = get_astrbot_temp_path()
            media_id = str(getattr(msg, "media_id", "") or "")
            path = os.path.join(temp_dir, f"wecom_{media_id}.amr")
            async with aiofiles.open(path, "wb") as f:
                await f.write(resp.content)
            try:
                path_wav = os.path.join(temp_dir, f"wecom_{media_id}.wav")
                path_wav = await convert_audio_to_wav(path, path_wav)
            except Exception as e:
                logger.error(f"转换音频失败: {e}｡如果没有安装 ffmpeg 请先安装｡")
                # return None to indicate failure to convert/handle voice message
                return None
            abm.message_str = ""
            abm.self_id = str(getattr(msg, "agent", "") or "")
            abm.message = [Record(file=path_wav, url=path_wav)]
            abm.type = MessageType.FRIEND_MESSAGE
            abm.sender = MessageMember(
                str(getattr(msg, "source", "") or ""),
                str(getattr(msg, "source", "") or ""),
            )
            abm.message_id = str(getattr(msg, "id", "") or "")
            abm.timestamp = int(str(getattr(msg, "time", 0) or 0))
            abm.session_id = abm.sender.user_id
            abm.raw_message = msg
        else:
            logger.warning(f"暂未实现的事件: {getattr(msg, 'type', '')!s}")
            return None
        # preserve last-seen agent id
        self.agent_id = abm.self_id
        logger.info(f"abm: {abm}")
        await self.handle_msg(abm)
        return abm

    async def convert_wechat_kf_message(self, msg: dict) -> AstrBotMessage | None:
        msgtype = str(msg.get("msgtype", "") or "")
        external_userid = str(msg.get("external_userid", "") or "")
        abm = AstrBotMessage()
        abm.raw_message = msg
        # normalized flag field to avoid typed union confusion
        abm.raw_message["_wechat_kf_flag"] = True
        abm.self_id = str(msg.get("open_kfid", "") or "")
        abm.sender = MessageMember(external_userid, external_userid)
        abm.session_id = external_userid
        abm.type = MessageType.FRIEND_MESSAGE
        abm.message_id = str(msg.get("msgid", uuid.uuid4().hex[:8]) or "")
        abm.message_str = ""
        if msgtype == "text":
            text = msg.get("text", {}).get("content", "").strip()
            if self._is_duplicate_wechat_kf_text_message(abm.session_id, text):
                logger.debug(
                    "忽略 15 秒内重复微信客服文本消息 session_id=%s text=%s",
                    abm.session_id,
                    text,
                )
                return None
            abm.message = [Plain(text=text)]
            abm.message_str = text
        elif msgtype == "image":
            media_id = str(msg.get("image", {}).get("media_id", "") or "")
            resp = await asyncio.get_running_loop().run_in_executor(
                None,
                self.client.media.download,
                media_id,
            )
            temp_dir = get_astrbot_temp_path()
            path = os.path.join(temp_dir, f"weixinkefu_{media_id}.jpg")
            async with aiofiles.open(path, "wb") as f:
                await f.write(resp.content)
            abm.message = [Image(file=path, url=path)]
        elif msgtype == "voice":
            media_id = str(msg.get("voice", {}).get("media_id", "") or "")
            resp = await asyncio.get_running_loop().run_in_executor(
                None,
                self.client.media.download,
                media_id,
            )
            temp_dir = get_astrbot_temp_path()
            path = os.path.join(temp_dir, f"weixinkefu_{media_id}.amr")
            async with aiofiles.open(path, "wb") as f:
                await f.write(resp.content)
            try:
                path_wav = os.path.join(temp_dir, f"weixinkefu_{media_id}.wav")
                path_wav = await convert_audio_to_wav(path, path_wav)
            except Exception as e:
                logger.error(f"转换音频失败: {e}｡如果没有安装 ffmpeg 请先安装｡")
                return None
            abm.message = [Record(file=path_wav, url=path_wav)]
        else:
            logger.warning(f"未实现的微信客服消息事件: {msg}")
            return None
        await self.handle_msg(abm)
        return abm

    async def handle_msg(self, message: AstrBotMessage) -> None:
        message_event = WecomPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )
        self.commit_event(message_event)

    def get_client(self) -> WeChatClient:
        return self.client

    async def terminate(self) -> None:
        # signal server shutdown
        self.server.shutdown_event.set()
        try:
            await self.server.server.shutdown()
        except Exception:
            # best-effort shutdown; no-op on failure
            pass
        logger.info("企业微信 适配器已被关闭")
