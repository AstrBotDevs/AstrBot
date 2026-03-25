from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote

import qrcode as qrcode_lib

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Image, Plain, Record, Video
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core import astrbot_config
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .weixin_oc_client import WeixinOCClient
from .weixin_oc_event import WeixinOCMessageEvent

if TYPE_CHECKING:  # pragma: no cover - typing-only helper
    pass


@dataclass
class OpenClawLoginSession:
    session_key: str
    qrcode: str
    qrcode_img_content: str
    started_at: float
    status: str = "wait"
    bot_token: str | None = None
    account_id: str | None = None
    base_url: str | None = None
    user_id: str | None = None
    error: str | None = None


@register_platform_adapter(
    "weixin_oc",
    "个人微信",
    support_streaming_message=False,
)
class WeixinOCAdapter(Platform):
    IMAGE_ITEM_TYPE = 2
    VOICE_ITEM_TYPE = 3
    FILE_ITEM_TYPE = 4
    VIDEO_ITEM_TYPE = 5
    IMAGE_UPLOAD_TYPE = 1
    VIDEO_UPLOAD_TYPE = 2
    FILE_UPLOAD_TYPE = 3

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.settings = platform_settings
        self.base_url = str(
            platform_config.get("weixin_oc_base_url", "https://ilinkai.weixin.qq.com")
        ).rstrip("/")
        self.bot_type = str(platform_config.get("weixin_oc_bot_type", "3"))
        self.qr_poll_interval = max(
            1,
            int(platform_config.get("weixin_oc_qr_poll_interval", 1)),
        )
        self.long_poll_timeout_ms = int(
            platform_config.get("weixin_oc_long_poll_timeout_ms", 35_000),
        )
        self.api_timeout_ms = int(
            platform_config.get("weixin_oc_api_timeout_ms", 15_000),
        )
        self.cdn_base_url = str(
            platform_config.get(
                "weixin_oc_cdn_base_url",
                "https://novac2c.cdn.weixin.qq.com/c2c",
            )
        ).rstrip("/")

        self.metadata = PlatformMetadata(
            name="weixin_oc",
            description="个人微信",
            id=cast(str, self.config.get("id", "weixin_oc")),
            support_streaming_message=False,
        )

        self._shutdown_event = asyncio.Event()
        self._login_session: OpenClawLoginSession | None = None
        self._sync_buf = ""
        self._qr_expired_count = 0
        self._context_tokens: dict[str, str] = {}
        self._last_inbound_error = ""

        self.token = str(platform_config.get("weixin_oc_token", "")).strip() or None
        self.account_id = (
            str(platform_config.get("weixin_oc_account_id", "")).strip() or None
        )
        self._load_account_state()
        self.client = WeixinOCClient(
            adapter_id=self.meta().id,
            base_url=self.base_url,
            cdn_base_url=self.cdn_base_url,
            api_timeout_ms=self.api_timeout_ms,
            token=self.token,
        )

        if self.token:
            logger.info(
                "weixin_oc adapter %s loaded with token from config.",
                self.meta().id,
            )

    def _sync_client_state(self) -> None:
        self.client.base_url = self.base_url
        self.client.cdn_base_url = self.cdn_base_url
        self.client.api_timeout_ms = self.api_timeout_ms
        self.client.token = self.token

    def _load_account_state(self) -> None:
        if not self.token:
            token = str(self.config.get("weixin_oc_token", "")).strip()
            if token:
                self.token = token
        if not self.account_id:
            account_id = str(self.config.get("weixin_oc_account_id", "")).strip()
            if account_id:
                self.account_id = account_id
        sync_buf = str(self.config.get("weixin_oc_sync_buf", "")).strip()
        if sync_buf:
            self._sync_buf = sync_buf
        saved_base = str(self.config.get("weixin_oc_base_url", "")).strip()
        if saved_base:
            self.base_url = saved_base.rstrip("/")

    async def _save_account_state(self) -> None:
        self.config["weixin_oc_token"] = self.token or ""
        self.config["weixin_oc_account_id"] = self.account_id or ""
        self.config["weixin_oc_sync_buf"] = self._sync_buf
        self.config["weixin_oc_base_url"] = self.base_url

        for platform in astrbot_config.get("platform", []):
            if not isinstance(platform, dict):
                continue
            if platform.get("id") != self.config.get("id"):
                continue
            if platform.get("type") != self.config.get("type"):
                continue
            platform["weixin_oc_token"] = self.token or ""
            platform["weixin_oc_account_id"] = self.account_id or ""
            platform["weixin_oc_sync_buf"] = self._sync_buf
            platform["weixin_oc_base_url"] = self.base_url
            break

        self._sync_client_state()
        astrbot_config.save_config()

    def _is_login_session_valid(
        self, login_session: OpenClawLoginSession | None
    ) -> bool:
        if not login_session:
            return False
        return (time.time() - login_session.started_at) * 1000 < 5 * 60_000

    def _resolve_inbound_media_dir(self) -> Path:
        media_dir = Path(get_astrbot_temp_path())
        media_dir.mkdir(parents=True, exist_ok=True)
        return media_dir

    @staticmethod
    def _normalize_inbound_filename(file_name: str, fallback_name: str) -> str:
        normalized = Path(file_name or "").name.strip()
        return normalized or fallback_name

    def _save_inbound_media(
        self,
        content: bytes,
        *,
        prefix: str,
        file_name: str,
        fallback_suffix: str,
    ) -> Path:
        normalized_name = self._normalize_inbound_filename(
            file_name,
            f"{prefix}{fallback_suffix}",
        )
        stem = Path(normalized_name).stem or prefix
        suffix = Path(normalized_name).suffix or fallback_suffix
        target = (
            self._resolve_inbound_media_dir()
            / f"{prefix}_{uuid.uuid4().hex}_{stem}{suffix}"
        )
        target.write_bytes(content)
        return target

    @staticmethod
    def _build_plain_text_item(text: str) -> dict[str, Any]:
        return {
            "type": 1,
            "text_item": {
                "text": text,
            },
        }

    async def _prepare_media_item(
        self,
        user_id: str,
        media_path: Path,
        upload_media_type: int,
        item_type: int,
        file_name: str,
    ) -> dict[str, Any]:
        raw_bytes = media_path.read_bytes()
        raw_size = len(raw_bytes)
        raw_md5 = hashlib.md5(raw_bytes).hexdigest()
        file_key = uuid.uuid4().hex
        aes_key_hex = uuid.uuid4().bytes.hex()
        ciphertext_size = self.client.aes_padded_size(raw_size)

        payload = await self.client.request_json(
            "POST",
            "ilink/bot/getuploadurl",
            payload={
                "filekey": file_key,
                "media_type": upload_media_type,
                "to_user_id": user_id,
                "rawsize": raw_size,
                "rawfilemd5": raw_md5,
                "filesize": ciphertext_size,
                "no_need_thumb": True,
                "aeskey": aes_key_hex,
                "base_info": {
                    "channel_version": "astrbot",
                },
            },
            token_required=True,
            timeout_ms=self.api_timeout_ms,
        )
        logger.debug(
            "weixin_oc(%s): getuploadurl response user=%s media_type=%s raw_size=%s raw_md5=%s filekey=%s file=%s upload_param_len=%s",
            self.meta().id,
            user_id,
            upload_media_type,
            raw_size,
            raw_md5,
            file_key,
            media_path.name,
            len(str(payload.get("upload_param", ""))),
        )
        upload_param = str(payload.get("upload_param", "")).strip()
        if not upload_param:
            raise RuntimeError("getuploadurl returned empty upload_param")

        encrypted_query_param = await self.client.upload_to_cdn(
            upload_param,
            file_key,
            aes_key_hex,
            media_path,
        )
        logger.debug(
            "weixin_oc(%s): prepared media item type=%s file=%s user=%s mid_size=%s upload_param_len=%s query_len=%s",
            self.meta().id,
            item_type,
            media_path.name,
            user_id,
            ciphertext_size,
            len(upload_param),
            len(encrypted_query_param),
        )

        aes_key_b64 = base64.b64encode(aes_key_hex.encode("utf-8")).decode("utf-8")
        media_payload = {
            "encrypt_query_param": encrypted_query_param,
            "aes_key": aes_key_b64,
            "encrypt_type": 1,
        }

        if item_type == self.IMAGE_ITEM_TYPE:
            return {
                "type": self.IMAGE_ITEM_TYPE,
                "image_item": {
                    "media": media_payload,
                    "mid_size": ciphertext_size,
                },
            }
        if item_type == self.VIDEO_ITEM_TYPE:
            return {
                "type": self.VIDEO_ITEM_TYPE,
                "video_item": {
                    "media": media_payload,
                    "video_size": ciphertext_size,
                },
            }

        file_len = str(raw_size)
        return {
            "type": self.FILE_ITEM_TYPE,
            "file_item": {
                "media": media_payload,
                "file_name": file_name,
                "len": file_len,
            },
        }

    async def _resolve_inbound_media_component(
        self,
        item: dict[str, Any],
    ) -> Image | Video | File | Record | None:
        item_type = int(item.get("type") or 0)

        if item_type == self.IMAGE_ITEM_TYPE:
            image_item = cast(dict[str, Any], item.get("image_item", {}) or {})
            media = cast(dict[str, Any], image_item.get("media", {}) or {})
            encrypted_query_param = str(media.get("encrypt_query_param", "")).strip()
            if not encrypted_query_param:
                return None
            image_aes_key = str(image_item.get("aeskey", "")).strip()
            if image_aes_key:
                aes_key_value = base64.b64encode(bytes.fromhex(image_aes_key)).decode(
                    "utf-8"
                )
            else:
                aes_key_value = str(media.get("aes_key", "")).strip()
            if aes_key_value:
                content = await self.client.download_and_decrypt_media(
                    encrypted_query_param,
                    aes_key_value,
                )
            else:
                content = await self.client.download_cdn_bytes(encrypted_query_param)
            image_path = self._save_inbound_media(
                content,
                prefix="weixin_oc_img",
                file_name="image.jpg",
                fallback_suffix=".jpg",
            )
            return Image.fromFileSystem(str(image_path))

        if item_type == self.VIDEO_ITEM_TYPE:
            video_item = cast(dict[str, Any], item.get("video_item", {}) or {})
            media = cast(dict[str, Any], video_item.get("media", {}) or {})
            encrypted_query_param = str(media.get("encrypt_query_param", "")).strip()
            aes_key_value = str(media.get("aes_key", "")).strip()
            if not encrypted_query_param or not aes_key_value:
                return None
            content = await self.client.download_and_decrypt_media(
                encrypted_query_param,
                aes_key_value,
            )
            video_path = self._save_inbound_media(
                content,
                prefix="weixin_oc_video",
                file_name="video.mp4",
                fallback_suffix=".mp4",
            )
            return Video.fromFileSystem(str(video_path))

        if item_type == self.FILE_ITEM_TYPE:
            file_item = cast(dict[str, Any], item.get("file_item", {}) or {})
            media = cast(dict[str, Any], file_item.get("media", {}) or {})
            encrypted_query_param = str(media.get("encrypt_query_param", "")).strip()
            aes_key_value = str(media.get("aes_key", "")).strip()
            if not encrypted_query_param or not aes_key_value:
                return None
            file_name = self._normalize_inbound_filename(
                str(file_item.get("file_name", "")).strip(),
                "file.bin",
            )
            content = await self.client.download_and_decrypt_media(
                encrypted_query_param,
                aes_key_value,
            )
            file_path = self._save_inbound_media(
                content,
                prefix="weixin_oc_file",
                file_name=file_name,
                fallback_suffix=".bin",
            )
            return File(name=file_name, file=str(file_path))

        if item_type == self.VOICE_ITEM_TYPE:
            voice_item = cast(dict[str, Any], item.get("voice_item", {}) or {})
            media = cast(dict[str, Any], voice_item.get("media", {}) or {})
            encrypted_query_param = str(media.get("encrypt_query_param", "")).strip()
            aes_key_value = str(media.get("aes_key", "")).strip()
            if not encrypted_query_param or not aes_key_value:
                return None
            content = await self.client.download_and_decrypt_media(
                encrypted_query_param,
                aes_key_value,
            )
            voice_path = self._save_inbound_media(
                content,
                prefix="weixin_oc_voice",
                file_name="voice.silk",
                fallback_suffix=".silk",
            )
            return Record.fromFileSystem(str(voice_path))

        return None

    async def _resolve_media_file_path(
        self, segment: Image | Video | File
    ) -> Path | None:
        try:
            if isinstance(segment, File):
                path = await segment.get_file()
            elif isinstance(segment, (Image, Video)):
                path = await segment.convert_to_file_path()
            else:
                path = ""
        except Exception as e:
            logger.warning("weixin_oc(%s): media resolve failed: %s", self.meta().id, e)
            return None

        if not path:
            return None
        media_path = Path(path)
        if not media_path.exists() or not media_path.is_file():
            return None
        return media_path

    async def _send_items_to_session(
        self,
        user_id: str,
        item_list: list[dict[str, Any]],
    ) -> bool:
        if not self.token:
            logger.warning("weixin_oc(%s): missing token, skip send", self.meta().id)
            return False
        if not item_list:
            logger.warning(
                "weixin_oc(%s): empty message payload is ignored",
                self.meta().id,
            )
            return False
        context_token = self._context_tokens.get(user_id)
        if not context_token:
            logger.warning(
                "weixin_oc(%s): context token missing for %s, skip send",
                self.meta().id,
                user_id,
            )
            return False
        await self.client.request_json(
            "POST",
            "ilink/bot/sendmessage",
            payload={
                "base_info": {
                    "channel_version": "astrbot",
                },
                "msg": {
                    "from_user_id": "",
                    "to_user_id": user_id,
                    "client_id": uuid.uuid4().hex,
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": context_token,
                    "item_list": item_list,
                },
            },
            token_required=True,
            headers={},
        )
        return True

    async def _send_media_segment(
        self,
        user_id: str,
        segment: Image | Video | File,
        text: str | None = None,
    ) -> bool:
        if not self.token:
            logger.warning(
                "weixin_oc(%s): missing token, skip media send", self.meta().id
            )
            return False
        media_path = await self._resolve_media_file_path(segment)
        if media_path is None:
            logger.warning(
                "weixin_oc(%s): skip media segment, media file not resolvable",
                self.meta().id,
            )
            return False

        item_type = self.IMAGE_ITEM_TYPE
        upload_media_type = self.IMAGE_UPLOAD_TYPE
        if isinstance(segment, Video):
            item_type = self.VIDEO_ITEM_TYPE
            upload_media_type = self.VIDEO_UPLOAD_TYPE
        elif isinstance(segment, File):
            item_type = self.FILE_ITEM_TYPE
            upload_media_type = self.FILE_UPLOAD_TYPE

        file_name = (
            segment.name
            if isinstance(segment, File) and segment.name
            else media_path.name
        )
        try:
            media_item = await self._prepare_media_item(
                user_id,
                media_path,
                upload_media_type,
                item_type,
                file_name,
            )
        except Exception as e:
            logger.error("weixin_oc(%s): prepare media failed: %s", self.meta().id, e)
            return False

        if text:
            await self._send_items_to_session(
                user_id,
                [self._build_plain_text_item(text)],
            )
        return await self._send_items_to_session(user_id, [media_item])

    async def _start_login_session(self) -> OpenClawLoginSession:
        endpoint = "ilink/bot/get_bot_qrcode"
        params = {"bot_type": self.bot_type}
        logger.info("weixin_oc(%s): request QR code from %s", self.meta().id, endpoint)
        data = await self.client.request_json(
            "GET",
            endpoint,
            params=params,
            token_required=False,
            timeout_ms=15_000,
        )
        qrcode = str(data.get("qrcode", "")).strip()
        qrcode_url = str(data.get("qrcode_img_content", "")).strip()
        if not qrcode or not qrcode_url:
            raise RuntimeError("qrcode response missing qrcode or qrcode_img_content")
        qr_console_url = (
            f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data="
            f"{quote(qrcode_url)}"
        )
        logger.info(
            "weixin_oc(%s): QR session started, qr_link=%s 请使用手机微信扫码登录,二维码有效期 5 分钟,过期后会自动刷新｡",
            self.meta().id,
            qr_console_url,
        )
        try:
            qr = qrcode_lib.QRCode(border=1)
            qr.add_data(qrcode_url)
            qr.make(fit=True)
            qr_buffer = io.StringIO()
            qr.print_ascii(out=qr_buffer, tty=False)
            logger.info(
                "weixin_oc(%s): terminal QR code:\n%s",
                self.meta().id,
                qr_buffer.getvalue(),
            )
        except Exception as e:
            logger.warning(
                "weixin_oc(%s): failed to render terminal QR code: %s",
                self.meta().id,
                e,
            )
        login_session = OpenClawLoginSession(
            session_key=str(uuid.uuid4()),
            qrcode=qrcode,
            qrcode_img_content=qrcode_url,
            started_at=time.time(),
        )
        self._login_session = login_session
        self._qr_expired_count = 0
        self._last_inbound_error = ""
        return login_session

    async def _poll_qr_status(self, login_session: OpenClawLoginSession) -> None:
        endpoint = "ilink/bot/get_qrcode_status"
        logger.debug("weixin_oc(%s): poll qrcode status", self.meta().id)
        data = await self.client.request_json(
            "GET",
            endpoint,
            params={"qrcode": login_session.qrcode},
            token_required=False,
            timeout_ms=self.long_poll_timeout_ms,
            headers={"iLink-App-ClientVersion": "1"},
        )
        status = str(data.get("status", "wait")).strip()
        login_session.status = status
        if status == "expired":
            self._qr_expired_count += 1
            if self._qr_expired_count > 3:
                login_session.error = "二维码已过期,超过重试次数,等待下次重试"
                self._login_session = None
                return
            logger.warning(
                "weixin_oc(%s): qr expired, refreshing (%s/%s)",
                self.meta().id,
                self._qr_expired_count,
                3,
            )
            new_session = await self._start_login_session()
            self._login_session = new_session
            return

        if status == "confirmed":
            bot_token = data.get("bot_token")
            account_id = data.get("ilink_bot_id")
            base_url = data.get("baseurl")
            user_id = data.get("ilink_user_id")
            if not bot_token:
                login_session.error = "登录返回成功但未返回 bot_token"
                return
            login_session.bot_token = str(bot_token)
            login_session.account_id = str(account_id) if account_id else None
            login_session.base_url = str(base_url) if base_url else self.base_url
            login_session.user_id = str(user_id) if user_id else None
            self.token = login_session.bot_token
            self.account_id = login_session.account_id
            if login_session.base_url:
                self.base_url = login_session.base_url.rstrip("/")
            await self._save_account_state()

    def _message_text_from_item_list(
        self, item_list: list[dict[str, Any]] | None
    ) -> str:
        if not item_list:
            return ""
        text_parts: list[str] = []
        for item in item_list:
            item_type = int(item.get("type") or 0)
            if item_type == 1:
                text = str(item.get("text_item", {}).get("text", "")).strip()
                if text:
                    text_parts.append(text)
            elif item_type == 2:
                text_parts.append("[图片]")
            elif item_type == 3:
                voice_text = str(item.get("voice_item", {}).get("text", "")).strip()
                if voice_text:
                    text_parts.append(voice_text)
                else:
                    text_parts.append("[语音]")
            elif item_type == 4:
                text_parts.append("[文件]")
            elif item_type == 5:
                text_parts.append("[视频]")
            else:
                ref = item.get("ref_msg")
                if isinstance(ref, dict):
                    ref_item = ref.get("message_item")
                    if isinstance(ref_item, dict):
                        ref_text = str(self._message_text_from_item_list([ref_item]))
                        if ref_text:
                            text_parts.append(f"[引用:{ref_text}]")
        return "\n".join(text_parts).strip()

    async def _item_list_to_components(
        self, item_list: list[dict[str, Any]] | None
    ) -> list[Any]:
        if not item_list:
            return []
        parts: list[Any] = []
        for item in item_list:
            item_type = int(item.get("type") or 0)
            if item_type == 1:
                text = str(item.get("text_item", {}).get("text", "")).strip()
                if text:
                    parts.append(Plain(text))
                continue
            try:
                media_component = await self._resolve_inbound_media_component(item)
            except Exception as e:
                logger.warning(
                    "weixin_oc(%s): resolve inbound media failed: %s",
                    self.meta().id,
                    e,
                )
                media_component = None
            if media_component is not None:
                parts.append(media_component)
        return parts

    async def _handle_inbound_message(self, msg: dict[str, Any]) -> None:
        from_user_id = str(msg.get("from_user_id", "")).strip()
        if not from_user_id:
            logger.debug("weixin_oc: skip message with empty from_user_id.")
            return

        context_token = str(msg.get("context_token", "")).strip()
        if context_token:
            self._context_tokens[from_user_id] = context_token

        item_list = cast(list[dict[str, Any]], msg.get("item_list", []))
        components = await self._item_list_to_components(item_list)
        text = self._message_text_from_item_list(item_list)
        message_id = str(msg.get("message_id") or msg.get("msg_id") or uuid.uuid4().hex)
        create_time = msg.get("create_time_ms") or msg.get("create_time")
        if isinstance(create_time, (int, float)) and create_time > 1_000_000_000_000:
            ts = int(float(create_time) / 1000)
        elif isinstance(create_time, (int, float)):
            ts = int(create_time)
        else:
            ts = int(time.time())

        abm = AstrBotMessage()
        abm.self_id = self.meta().id
        abm.sender = MessageMember(user_id=from_user_id, nickname=from_user_id)
        abm.type = MessageType.FRIEND_MESSAGE
        abm.session_id = from_user_id
        abm.message_id = message_id
        abm.message = components
        abm.message_str = text
        abm.timestamp = ts
        abm.raw_message = msg

        self.commit_event(
            WeixinOCMessageEvent(
                message_str=text,
                message_obj=abm,
                platform_meta=self.meta(),
                session_id=abm.session_id,
                platform=self,
            )
        )

    async def _poll_inbound_updates(self) -> None:
        data = await self.client.request_json(
            "POST",
            "ilink/bot/getupdates",
            payload={
                "base_info": {
                    "channel_version": "astrbot",
                },
                "get_updates_buf": self._sync_buf,
            },
            token_required=True,
            timeout_ms=self.long_poll_timeout_ms,
        )
        ret = int(data.get("ret") or 0)
        errcode = data.get("errcode", 0)
        if ret != 0 and ret is not None:
            errmsg = str(data.get("errmsg", ""))
            self._last_inbound_error = f"ret={ret}, errcode={errcode}, errmsg={errmsg}"
            logger.warning(
                "weixin_oc(%s): getupdates error: %s",
                self.meta().id,
                self._last_inbound_error,
            )
            return
        if errcode and int(errcode) != 0:
            errmsg = str(data.get("errmsg", ""))
            self._last_inbound_error = f"ret={ret}, errcode={errcode}, errmsg={errmsg}"
            logger.warning(
                "weixin_oc(%s): getupdates error: %s",
                self.meta().id,
                self._last_inbound_error,
            )
            return

        if data.get("get_updates_buf"):
            self._sync_buf = str(data.get("get_updates_buf"))
            await self._save_account_state()

        for msg in data.get("msgs", []) if isinstance(data.get("msgs"), list) else []:
            if self._shutdown_event.is_set():
                return
            if not isinstance(msg, dict):
                continue
            await self._handle_inbound_message(msg)

    def _message_chain_to_text(self, message_chain: MessageChain) -> str:
        text = ""
        for segment in message_chain.chain:
            if isinstance(segment, Plain):
                text += segment.text
        return text.strip()

    async def _send_to_session(
        self, user_id: str, text: str, _components: list[Any] | None = None
    ) -> bool:
        if not text:
            text = self._message_chain_to_text(MessageChain(_components or []))
        if not text:
            logger.warning(
                "weixin_oc(%s): message without plain text is ignored",
                self.meta().id,
            )
            return False
        return await self._send_items_to_session(
            user_id,
            [self._build_plain_text_item(text)],
        )

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        target_user = session.session_id
        pending_text = ""
        has_supported_segment = False
        for segment in message_chain.chain:
            if isinstance(segment, Plain):
                pending_text += segment.text
                continue

            if isinstance(segment, (Image, Video, File)):
                has_supported_segment = True
                await self._send_media_segment(
                    target_user,
                    segment,
                    text=pending_text.strip() or None,
                )
                pending_text = ""
                continue

            logger.debug(
                "weixin_oc(%s): unsupported outbound segment type %s",
                self.meta().id,
                type(segment).__name__,
            )

        if pending_text:
            has_supported_segment = True
            await self._send_to_session(target_user, pending_text.strip())

        if not has_supported_segment:
            logger.warning(
                "weixin_oc(%s): outbound message ignored, no supported segments",
                self.meta().id,
            )
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def run(self) -> None:
        try:
            while not self._shutdown_event.is_set():
                if not self.token:
                    if not self._is_login_session_valid(self._login_session):
                        try:
                            self._login_session = await self._start_login_session()
                            self._qr_expired_count = 0
                        except Exception as e:
                            logger.error(
                                "weixin_oc(%s): start login failed: %s",
                                self.meta().id,
                                e,
                            )
                            await asyncio.sleep(5)
                            continue

                    current_login = self._login_session
                    if current_login is None:
                        continue

                    try:
                        await self._poll_qr_status(current_login)
                    except asyncio.TimeoutError:
                        logger.debug(
                            "weixin_oc(%s): qr status long-poll timeout",
                            self.meta().id,
                        )
                    except Exception as e:
                        logger.error(
                            "weixin_oc(%s): poll qr status failed: %s",
                            self.meta().id,
                            e,
                        )
                        current_login.error = str(e)
                        await asyncio.sleep(2)

                    if self.token:
                        logger.info(
                            "weixin_oc(%s): login confirmed, account=%s",
                            self.meta().id,
                            self.account_id or "",
                        )
                        continue

                    if current_login.error:
                        await asyncio.sleep(2)
                    else:
                        await asyncio.sleep(self.qr_poll_interval)
                    continue

                try:
                    await self._poll_inbound_updates()
                except asyncio.TimeoutError:
                    logger.debug(
                        "weixin_oc(%s): inbound long-poll timeout",
                        self.meta().id,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("weixin_oc(%s): run failed: %s", self.meta().id, e)
        finally:
            await self.client.close()

    async def terminate(self) -> None:
        self._shutdown_event.set()

    def get_stats(self) -> dict:
        stat = super().get_stats()
        login_session = self._login_session
        stat["weixin_oc"] = {
            "configured": bool(self.token),
            "account_id": self.account_id,
            "base_url": self.base_url,
            "qr_session_key": login_session.session_key if login_session else None,
            "qr_status": login_session.status if login_session else None,
            "qrcode": login_session.qrcode if login_session else None,
            "qrcode_img_content": login_session.qrcode_img_content
            if login_session
            else None,
            "qr_error": login_session.error if login_session else None,
            "sync_buf_len": len(self._sync_buf),
            "last_error": self._last_inbound_error,
        }
        return stat
