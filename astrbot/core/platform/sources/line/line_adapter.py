import asyncio
import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any, cast

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain, Record, Video
from astrbot.api.platform import (
    AstrBotMessage,
    Group,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.webhook_utils import log_webhook_info

from ...register import register_platform_adapter
from .line_api import LineAPIClient
from .line_event import LineMessageEvent

LINE_CONFIG_METADATA = {
    "channel_access_token": {
        "description": "LINE Channel Access Token",
        "type": "string",
        "hint": "LINE Messaging API 的 channel access token。",
    },
    "channel_secret": {
        "description": "LINE Channel Secret",
        "type": "string",
        "hint": "用于校验 LINE Webhook 签名。",
    },
}

LINE_I18N_RESOURCES = {
    "zh-CN": {
        "channel_access_token": {
            "description": "LINE Channel Access Token",
            "hint": "LINE Messaging API 的 channel access token。",
        },
        "channel_secret": {
            "description": "LINE Channel Secret",
            "hint": "用于校验 LINE Webhook 签名。",
        },
    },
    "en-US": {
        "channel_access_token": {
            "description": "LINE Channel Access Token",
            "hint": "Channel access token for LINE Messaging API.",
        },
        "channel_secret": {
            "description": "LINE Channel Secret",
            "hint": "Used to verify LINE webhook signatures.",
        },
    },
}


@register_platform_adapter(
    "line",
    "LINE Messaging API 适配器",
    support_streaming_message=False,
    default_config_tmpl={
        "id": "line",
        "type": "line",
        "enable": False,
        "channel_access_token": "",
        "channel_secret": "",
        "unified_webhook_mode": True,
        "webhook_uuid": "",
    },
    config_metadata=LINE_CONFIG_METADATA,
    i18n_resources=LINE_I18N_RESOURCES,
)
class LinePlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.config["unified_webhook_mode"] = True
        self.destination = "unknown"
        self.settings = platform_settings
        self._event_id_timestamps: dict[str, float] = {}
        self.shutdown_event = asyncio.Event()

        channel_access_token = str(platform_config.get("channel_access_token", ""))
        channel_secret = str(platform_config.get("channel_secret", ""))
        if not channel_access_token or not channel_secret:
            raise ValueError(
                "LINE 适配器需要 channel_access_token 和 channel_secret。",
            )

        self.line_api = LineAPIClient(
            channel_access_token=channel_access_token,
            channel_secret=channel_secret,
        )

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        messages = await LineMessageEvent.build_line_messages(message_chain)
        if messages:
            await self.line_api.push_message(session.session_id, messages)
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="line",
            description="LINE Messaging API 适配器",
            id=cast(str, self.config.get("id", "line")),
            support_streaming_message=False,
        )

    async def run(self) -> None:
        webhook_uuid = self.config.get("webhook_uuid")
        if webhook_uuid:
            log_webhook_info(f"{self.meta().id}(LINE)", webhook_uuid)
        else:
            logger.warning("[LINE] webhook_uuid 为空，统一 Webhook 可能无法接收消息。")
        await self.shutdown_event.wait()

    async def terminate(self) -> None:
        self.shutdown_event.set()
        await self.line_api.close()

    async def webhook_callback(self, request: Any) -> Any:
        raw_body = await request.get_data()
        signature = request.headers.get("x-line-signature")
        if not self.line_api.verify_signature(raw_body, signature):
            logger.warning("[LINE] invalid webhook signature")
            return "invalid signature", 400

        try:
            payload = await request.get_json(force=True, silent=False)
        except Exception as e:
            logger.warning("[LINE] invalid webhook body: %s", e)
            return "bad request", 400

        if not isinstance(payload, dict):
            return "bad request", 400

        await self.handle_webhook_event(payload)
        return "ok", 200

    async def handle_webhook_event(self, payload: dict[str, Any]) -> None:
        destination = str(payload.get("destination", "")).strip()
        if destination:
            self.destination = destination

        events = payload.get("events")
        if not isinstance(events, list):
            return

        for event in events:
            if not isinstance(event, dict):
                continue

            event_id = str(event.get("webhookEventId", ""))
            if event_id and self._is_duplicate_event(event_id):
                logger.debug("[LINE] duplicate event skipped: %s", event_id)
                continue

            abm = await self.convert_message(event)
            if abm is None:
                continue
            await self.handle_msg(abm)

    async def convert_message(self, event: dict[str, Any]) -> AstrBotMessage | None:
        if str(event.get("type", "")) != "message":
            return None
        if str(event.get("mode", "active")) == "standby":
            return None

        source = event.get("source", {})
        if not isinstance(source, dict):
            return None

        message = event.get("message", {})
        if not isinstance(message, dict):
            return None

        source_type = str(source.get("type", ""))
        user_id = str(source.get("userId", "")).strip()
        group_id = str(source.get("groupId", "")).strip()
        room_id = str(source.get("roomId", "")).strip()

        abm = AstrBotMessage()
        abm.self_id = self.destination or self.meta().id
        abm.message = []
        abm.raw_message = event
        abm.message_id = str(
            message.get("id")
            or event.get("webhookEventId")
            or event.get("deliveryContext", {}).get("deliveryId", "")
            or uuid.uuid4().hex
        )

        event_timestamp = event.get("timestamp")
        if isinstance(event_timestamp, int):
            abm.timestamp = (
                event_timestamp // 1000
                if event_timestamp > 1_000_000_000_000
                else event_timestamp
            )
        else:
            abm.timestamp = int(time.time())

        if source_type in {"group", "room"}:
            abm.type = MessageType.GROUP_MESSAGE
            container_id = group_id or room_id
            abm.group = Group(group_id=container_id, group_name=container_id)
            abm.session_id = container_id
            sender_id = user_id or container_id
        elif source_type == "user":
            abm.type = MessageType.FRIEND_MESSAGE
            abm.session_id = user_id
            sender_id = user_id
        else:
            abm.type = MessageType.OTHER_MESSAGE
            abm.session_id = user_id or group_id or room_id or "unknown"
            sender_id = abm.session_id

        abm.sender = MessageMember(user_id=sender_id, nickname=sender_id[:8])

        components = await self._parse_line_message_components(message)
        if not components:
            return None
        abm.message = components
        abm.message_str = self._build_message_str(components)
        return abm

    async def _parse_line_message_components(
        self,
        message: dict[str, Any],
    ) -> list:
        msg_type = str(message.get("type", ""))
        message_id = str(message.get("id", "")).strip()

        if msg_type == "text":
            text = str(message.get("text", ""))
            mention = message.get("mention")
            if isinstance(mention, dict):
                return self._parse_text_with_mentions(text, mention)
            return [Plain(text=text)] if text else []

        if msg_type == "image":
            image_component = await self._build_image_component(message_id, message)
            return [image_component] if image_component else [Plain(text="[image]")]

        if msg_type == "video":
            video_component = await self._build_video_component(message_id, message)
            return [video_component] if video_component else [Plain(text="[video]")]

        if msg_type == "audio":
            audio_component = await self._build_audio_component(message_id, message)
            return [audio_component] if audio_component else [Plain(text="[audio]")]

        if msg_type == "file":
            file_component = await self._build_file_component(message_id, message)
            return [file_component] if file_component else [Plain(text="[file]")]

        if msg_type == "sticker":
            return [Plain(text="[sticker]")]

        return [Plain(text=f"[{msg_type}]")]

    def _parse_text_with_mentions(self, text: str, mention_obj: dict[str, Any]) -> list:
        mentions = mention_obj.get("mentionees", [])
        if not isinstance(mentions, list) or not mentions:
            return [Plain(text=text)] if text else []

        normalized = []
        for item in mentions:
            if not isinstance(item, dict):
                continue
            start = item.get("index")
            length = item.get("length")
            if not isinstance(start, int) or not isinstance(length, int):
                continue
            normalized.append((start, length, item))
        normalized.sort(key=lambda x: x[0])

        ret = []
        cursor = 0
        for start, length, item in normalized:
            if start > cursor:
                part = text[cursor:start]
                if part:
                    ret.append(Plain(text=part))

            label = text[start : start + length] or "@user"
            mention_type = str(item.get("type", ""))
            if mention_type == "user":
                target_id = str(item.get("userId", "")).strip()
                ret.append(At(qq=target_id, name=label.lstrip("@")))
            else:
                ret.append(Plain(text=label))
            cursor = max(cursor, start + length)

        if cursor < len(text):
            tail = text[cursor:]
            if tail:
                ret.append(Plain(text=tail))
        return ret

    async def _build_image_component(
        self,
        message_id: str,
        message: dict[str, Any],
    ) -> Image | None:
        external_url = self._get_external_content_url(message)
        if external_url:
            return Image.fromURL(external_url)

        content = await self.line_api.get_message_content(message_id)
        if not content:
            return None
        content_bytes, _, _ = content
        return Image.fromBytes(content_bytes)

    async def _build_video_component(
        self,
        message_id: str,
        message: dict[str, Any],
    ) -> Video | None:
        external_url = self._get_external_content_url(message)
        if external_url:
            return Video.fromURL(external_url)

        content = await self.line_api.get_message_content(message_id)
        if not content:
            return None
        content_bytes, content_type, _ = content
        suffix = self._guess_suffix(content_type, ".mp4")
        file_path = self._store_temp_content("video", message_id, content_bytes, suffix)
        return Video(file=file_path, path=file_path)

    async def _build_audio_component(
        self,
        message_id: str,
        message: dict[str, Any],
    ) -> Record | None:
        external_url = self._get_external_content_url(message)
        if external_url:
            return Record.fromURL(external_url)

        content = await self.line_api.get_message_content(message_id)
        if not content:
            return None
        content_bytes, content_type, _ = content
        suffix = self._guess_suffix(content_type, ".m4a")
        file_path = self._store_temp_content("audio", message_id, content_bytes, suffix)
        return Record(file=file_path, url=file_path)

    async def _build_file_component(
        self,
        message_id: str,
        message: dict[str, Any],
    ) -> File | None:
        content = await self.line_api.get_message_content(message_id)
        if not content:
            return None
        content_bytes, content_type, filename = content
        default_name = str(message.get("fileName", "")).strip() or f"{message_id}.bin"
        suffix = Path(default_name).suffix or self._guess_suffix(content_type, ".bin")
        final_name = filename or default_name
        file_path = self._store_temp_content(
            "file",
            message_id,
            content_bytes,
            suffix,
            original_name=final_name,
        )
        return File(name=final_name, file=file_path, url=file_path)

    @staticmethod
    def _get_external_content_url(message: dict[str, Any]) -> str:
        provider = message.get("contentProvider")
        if not isinstance(provider, dict):
            return ""
        if str(provider.get("type", "")) != "external":
            return ""
        return str(provider.get("originalContentUrl", "")).strip()

    @staticmethod
    def _guess_suffix(content_type: str | None, fallback: str) -> str:
        if not content_type:
            return fallback
        base_type = content_type.split(";", 1)[0].strip().lower()
        guessed = mimetypes.guess_extension(base_type)
        if guessed:
            return guessed
        return fallback

    @staticmethod
    def _store_temp_content(
        content_type: str,
        message_id: str,
        content: bytes,
        suffix: str,
        original_name: str = "",
    ) -> str:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        name_prefix = f"line_{content_type}"
        if original_name:
            safe_stem = Path(original_name).stem.strip()
            safe_stem = "".join(
                ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in safe_stem
            )
            safe_stem = safe_stem.strip("._")
            if safe_stem:
                name_prefix = safe_stem[:64]
        file_path = temp_dir / f"{name_prefix}_{message_id}_{uuid.uuid4().hex[:6]}"
        file_path = file_path.with_suffix(suffix)
        file_path.write_bytes(content)
        return str(file_path.resolve())

    @staticmethod
    def _build_message_str(components: list) -> str:
        parts: list[str] = []
        for comp in components:
            if isinstance(comp, Plain):
                parts.append(comp.text)
            elif isinstance(comp, At):
                parts.append(f"@{comp.name or comp.qq}")
            elif isinstance(comp, Image):
                parts.append("[image]")
            elif isinstance(comp, Video):
                parts.append("[video]")
            elif isinstance(comp, Record):
                parts.append("[audio]")
            elif isinstance(comp, File):
                parts.append(str(comp.name or "[file]"))
            else:
                parts.append(f"[{comp.type}]")
        return " ".join(i for i in parts if i).strip()

    def _clean_expired_events(self) -> None:
        current = time.time()
        expired = [
            event_id
            for event_id, ts in self._event_id_timestamps.items()
            if current - ts > 1800
        ]
        for event_id in expired:
            del self._event_id_timestamps[event_id]

    def _is_duplicate_event(self, event_id: str) -> bool:
        self._clean_expired_events()
        if event_id in self._event_id_timestamps:
            return True
        self._event_id_timestamps[event_id] = time.time()
        return False

    async def handle_msg(self, abm: AstrBotMessage) -> None:
        event = LineMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            line_api=self.line_api,
        )
        self._event_queue.put_nowait(event)
