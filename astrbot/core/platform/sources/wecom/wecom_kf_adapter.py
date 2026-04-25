import asyncio
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import quart
from requests import Response
from wechatpy.enterprise import WeChatClient, parse_message
from wechatpy.enterprise.crypto import WeChatCrypto
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


class WecomKFServer:
    def __init__(self, config: dict) -> None:
        self.server = quart.Quart(__name__)
        self.port = int(cast(str, config.get("port")))
        self.callback_server_host = config.get("callback_server_host", "0.0.0.0")
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

        self.crypto = WeChatCrypto(
            config["token"].strip(),
            config["encoding_aes_key"].strip(),
            config["corpid"].strip(),
        )

        self.callback: Callable[[BaseMessage], Awaitable[None]] | None = None
        self.shutdown_event = asyncio.Event()

    async def verify(self):
        return await self.handle_verify(quart.request)

    async def handle_verify(self, request) -> str:
        logger.info(f"验证微信客服请求有效性: {request.args}")
        args = request.args
        try:
            echo_str = self.crypto.check_signature(
                args.get("msg_signature"),
                args.get("timestamp"),
                args.get("nonce"),
                args.get("echostr"),
            )
            logger.info("验证微信客服请求有效性成功。")
            return echo_str
        except InvalidSignatureException:
            logger.error("验证微信客服请求有效性失败，签名异常，请检查配置。")
            raise

    async def callback_command(self):
        return await self.handle_callback(quart.request)

    async def handle_callback(self, request) -> str:
        data = await request.get_data()
        msg_signature = request.args.get("msg_signature")
        timestamp = request.args.get("timestamp")
        nonce = request.args.get("nonce")
        try:
            xml = self.crypto.decrypt_message(data, msg_signature, timestamp, nonce)
        except InvalidSignatureException:
            logger.error("解密微信客服回调失败，签名异常，请检查配置。")
            raise

        msg = cast(BaseMessage, parse_message(xml))
        logger.info(f"解析微信客服回调成功: {msg}")
        if self.callback:
            await self.callback(msg)
        return "success"

    async def start_polling(self) -> None:
        logger.info(
            f"将在 {self.callback_server_host}:{self.port} 端口启动 微信客服 适配器。",
        )
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self) -> None:
        await self.shutdown_event.wait()


@register_platform_adapter(
    "wecom_kf", "微信客服适配器", support_streaming_message=False
)
class WecomKFPlatformAdapter(Platform):
    MSGID_DEDUP_TTL_SECONDS = 300
    TEXT_CONTENT_DEDUP_TTL_SECONDS = 15

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.api_base_url = platform_config.get(
            "api_base_url",
            "https://qyapi.weixin.qq.com/cgi-bin/",
        )
        self.unified_webhook_mode = platform_config.get("unified_webhook_mode", False)

        if not self.api_base_url:
            self.api_base_url = "https://qyapi.weixin.qq.com/cgi-bin/"
        self.api_base_url = self.api_base_url.removesuffix("/")
        if not self.api_base_url.endswith("/cgi-bin"):
            self.api_base_url += "/cgi-bin"
        if not self.api_base_url.endswith("/"):
            self.api_base_url += "/"

        self.server = WecomKFServer(self.config)
        self.client = WeChatClient(
            self.config["corpid"].strip(),
            self.config["secret"].strip(),
        )
        self.wechat_kf_api = WeChatKF(client=self.client)
        self.wechat_kf_message_api = WeChatKFMessage(self.client)
        self.client.__setattr__("kf", self.wechat_kf_api)
        self.client.__setattr__("kf_message", self.wechat_kf_message_api)
        self.client.__setattr__("API_BASE_URL", self.api_base_url)

        self._seen_msgids: dict[str, float] = {}
        self._seen_text_messages: dict[str, float] = {}
        self._kf_accounts: list[dict[str, Any]] = []
        self._kf_contact_links: list[dict[str, str]] = []
        self._kf_link_error = ""

        async def callback(msg: BaseMessage) -> None:
            if msg.type == "unknown" and msg._data.get("Event") == "kf_msg_or_event":
                await self._handle_kf_msg_or_event(msg)
                return
            logger.debug("微信客服适配器忽略非客服回调: %s", msg)

        self.server.callback = callback

    @override
    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            "wecom_kf",
            "微信客服适配器",
            id=self.config.get("id", "wecom_kf"),
            support_streaming_message=False,
            support_proactive_message=False,
        )

    @override
    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        logger.warning("微信客服适配器不支持 send_by_session 主动发送。")
        await super().send_by_session(session, message_chain)

    async def run(self) -> None:
        await self._refresh_kf_contact_links()

        webhook_uuid = self.config.get("webhook_uuid")
        if self.unified_webhook_mode and webhook_uuid:
            log_webhook_info(f"{self.meta().id}(微信客服)", webhook_uuid)
            await self.server.shutdown_event.wait()
        else:
            await self.server.start_polling()

    async def webhook_callback(self, request: Any) -> Any:
        if request.method == "GET":
            return await self.server.handle_verify(request)
        return await self.server.handle_callback(request)

    async def _refresh_kf_contact_links(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            account_payload = await loop.run_in_executor(
                None,
                self.wechat_kf_api.get_account_list,
            )
            accounts = account_payload.get("account_list", [])
            self._kf_accounts = accounts if isinstance(accounts, list) else []

            contact_links: list[dict[str, str]] = []
            for index, account in enumerate(self._kf_accounts):
                if not isinstance(account, dict):
                    continue
                open_kfid = str(account.get("open_kfid", "")).strip()
                if not open_kfid:
                    continue
                scene = f"astrbot_{index}"
                contact_payload = await loop.run_in_executor(
                    None,
                    self.wechat_kf_api.add_contact_way,
                    open_kfid,
                    scene,
                )
                url = str(contact_payload.get("url", "")).strip()
                if not url:
                    continue
                contact_links.append(
                    {
                        "open_kfid": open_kfid,
                        "name": str(account.get("name", "")).strip() or open_kfid,
                        "qrcode": url,
                        "qrcode_img_content": url,
                    }
                )

            self._kf_contact_links = contact_links
            self._kf_link_error = ""
            logger.info(
                "微信客服适配器获取到 %s 个客服账号，生成 %s 个客服链接。",
                len(self._kf_accounts),
                len(self._kf_contact_links),
            )
        except Exception as e:
            self._kf_link_error = str(e)
            logger.error("获取微信客服列表或客服链接失败: %s", e, exc_info=True)

    async def get_kf_accounts_payload(self) -> dict[str, Any]:
        await self._refresh_kf_contact_links()
        return {
            "accounts": self._kf_accounts,
            "contact_links": self._kf_contact_links,
            "link_error": self._kf_link_error,
        }

    async def add_kf_account(self, name: str, media_id: str = "") -> dict[str, Any]:
        payload = await asyncio.get_running_loop().run_in_executor(
            None,
            self.wechat_kf_api.add_account,
            name,
            media_id,
        )
        await self._refresh_kf_contact_links()
        return cast(dict[str, Any], payload)

    async def update_kf_account(
        self, open_kfid: str, name: str = "", media_id: str = ""
    ) -> dict[str, Any]:
        payload = await asyncio.get_running_loop().run_in_executor(
            None,
            self.wechat_kf_api.update_account,
            open_kfid,
            name,
            media_id,
        )
        await self._refresh_kf_contact_links()
        return cast(dict[str, Any], payload)

    async def upload_kf_avatar(self, file_path: Path) -> dict[str, Any]:
        def upload() -> dict[str, Any]:
            with file_path.open("rb") as f:
                return cast(dict[str, Any], self.client.media.upload("image", f))

        return await asyncio.get_running_loop().run_in_executor(None, upload)

    async def delete_kf_account(self, open_kfid: str) -> dict[str, Any]:
        payload = await asyncio.get_running_loop().run_in_executor(
            None,
            self.wechat_kf_api.del_account,
            open_kfid,
        )
        await self._refresh_kf_contact_links()
        return cast(dict[str, Any], payload)

    async def _handle_kf_msg_or_event(self, msg: BaseMessage) -> None:
        token = msg._data.get("Token", "")
        open_kfid = msg._data.get("OpenKfId", "")
        messages = await asyncio.get_running_loop().run_in_executor(
            None,
            self._sync_all_messages,
            token,
            open_kfid,
        )
        for item in messages:
            await self.convert_wechat_kf_message(item)

    def _sync_all_messages(self, token: str, open_kfid: str) -> list[dict[str, Any]]:
        cursor = ""
        has_more = 1
        messages: list[dict[str, Any]] = []
        while has_more:
            payload = self.wechat_kf_api.sync_msg(token, open_kfid, cursor=cursor)
            msg_list = payload.get("msg_list", [])
            if isinstance(msg_list, list):
                messages.extend(item for item in msg_list if isinstance(item, dict))
            has_more = int(payload.get("has_more", 0) or 0)
            next_cursor = str(payload.get("next_cursor", "")).strip()
            if not has_more or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return messages

    def _is_duplicate_msgid(self, msgid: str) -> bool:
        now = time.monotonic()
        expired_msgids = [
            cached_msgid
            for cached_msgid, expires_at in self._seen_msgids.items()
            if expires_at <= now
        ]
        for cached_msgid in expired_msgids:
            self._seen_msgids.pop(cached_msgid, None)

        if msgid in self._seen_msgids:
            return True
        self._seen_msgids[msgid] = now + self.MSGID_DEDUP_TTL_SECONDS
        return False

    def _is_duplicate_text_message(self, session_id: str, text: str) -> bool:
        normalized_text = text.strip()
        if not normalized_text:
            return False

        now = time.monotonic()
        expired_keys = [
            key
            for key, expires_at in self._seen_text_messages.items()
            if expires_at <= now
        ]
        for key in expired_keys:
            self._seen_text_messages.pop(key, None)

        dedup_key = f"{session_id}:{normalized_text}"
        if dedup_key in self._seen_text_messages:
            return True
        self._seen_text_messages[dedup_key] = now + self.TEXT_CONTENT_DEDUP_TTL_SECONDS
        return False

    async def convert_wechat_kf_message(self, msg: dict) -> AstrBotMessage | None:
        logger.info(f"收到微信客服消息: {msg}")

        msgid = str(msg.get("msgid", "")).strip()
        if msgid and self._is_duplicate_msgid(msgid):
            logger.debug("忽略重复微信客服消息 msgid=%s", msgid)
            return None

        msgtype = msg.get("msgtype")
        open_kfid = str(msg.get("open_kfid", "")).strip()
        external_userid = str(msg.get("external_userid", "")).strip()
        if not open_kfid or not external_userid:
            logger.debug(
                "忽略缺少 open_kfid 或 external_userid 的微信客服消息: %s", msg
            )
            return None

        abm = AstrBotMessage()
        abm.raw_message = dict(msg)
        abm.raw_message["_wechat_kf_flag"] = None
        abm.self_id = open_kfid
        abm.sender = MessageMember(external_userid, external_userid)
        abm.session_id = f"{open_kfid}_{external_userid}"
        abm.type = MessageType.FRIEND_MESSAGE
        abm.message_id = msgid or uuid.uuid4().hex[:8]
        abm.timestamp = int(msg.get("send_time", time.time()))
        abm.message_str = ""

        if msgtype == "text":
            text = msg.get("text", {}).get("content", "").strip()
            if self._is_duplicate_text_message(abm.session_id, text):
                logger.debug(
                    "忽略 15 秒内重复微信客服文本消息 session_id=%s text=%s",
                    abm.session_id,
                    text,
                )
                return None
            abm.message = [Plain(text=text)]
            abm.message_str = text
        elif msgtype == "image":
            media_id = msg.get("image", {}).get("media_id", "")
            path = await self._download_media(media_id, "wecom_kf_img", ".jpg")
            abm.message = [Image(file=str(path), url=str(path))]
            abm.message_str = "[图片]"
        elif msgtype == "voice":
            media_id = msg.get("voice", {}).get("media_id", "")
            path = await self._download_media(media_id, "wecom_kf_voice", ".amr")
            try:
                wav_path = path.with_suffix(".wav")
                converted_path = await convert_audio_to_wav(str(path), str(wav_path))
            except Exception as e:
                logger.error(
                    f"转换微信客服音频失败: {e}。如果没有安装 ffmpeg 请先安装。"
                )
                return None
            abm.message = [Record(file=converted_path, url=converted_path)]
        else:
            logger.warning(f"未实现的微信客服消息事件: {msg}")
            return None

        await self.handle_msg(abm)
        return abm

    async def _download_media(self, media_id: str, prefix: str, suffix: str) -> Path:
        resp: Response = await asyncio.get_running_loop().run_in_executor(
            None,
            self.client.media.download,
            media_id,
        )
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        path = temp_dir / f"{prefix}_{media_id or uuid.uuid4().hex}{suffix}"
        path.write_bytes(resp.content)
        return path

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

    def get_stats(self) -> dict:
        stat = super().get_stats()
        stat["wecom_kf"] = {
            "accounts": self._kf_accounts,
            "contact_links": self._kf_contact_links,
            "link_error": self._kf_link_error,
        }
        return stat

    async def terminate(self) -> None:
        self.server.shutdown_event.set()
        try:
            await self.server.server.shutdown()
        except Exception:
            pass
        logger.info("微信客服适配器已被关闭")
