import asyncio
import time
import uuid
from typing import Any, cast

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain, Record, Video
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion

from ...register import register_platform_adapter
from .ntfy_api import NtfyAPIClient
from .ntfy_event import NtfyMessageEvent

NTFY_CONFIG_METADATA = {
    "server_url": {
        "description": "ntfy Server URL",
        "type": "string",
        "hint": "ntfy 服务器地址，例如 https://ntfy.sh 或您的自建实例地址。",
    },
    "topic": {
        "description": "ntfy Topic",
        "type": "string",
        "hint": "用于收发消息的唯一订阅主题名称 (请确保其足够私密)。",
    },
    "access_token": {
        "description": "Access Token (Optional)",
        "type": "string",
        "hint": "如果您的 ntfy 服务器开启了身份验证，请在此输入 Bearer Token。",
    },
}

NTFY_I18N_RESOURCES = {
    "zh-CN": {
        "ntfy_server_url": {
            "description": "ntfy 服务器地址",
            "hint": "ntfy 服务器地址，例如 https://ntfy.sh",
        },
        "ntfy_topic": {
            "description": "订阅主题 (Topic)",
            "hint": "用于收发消息的唯一订阅主题名称。",
        },
        "ntfy_access_token": {
            "description": "访问令牌 (可选)",
            "hint": "有访问权限控制的服务器需要填写此 Token。",
        },
    },
    "en-US": {
        "ntfy_server_url": {
            "description": "ntfy Server URL",
            "hint": "The ntfy instance server base URL, e.g., https://ntfy.sh",
        },
        "ntfy_topic": {
            "description": "Subscription Topic",
            "hint": "The secret unique topic used to listen and publish messages.",
        },
        "ntfy_access_token": {
            "description": "Access Token (Optional)",
            "hint": "Bearer token if your ntfy server requires authentication.",
        },
    },
}


@register_platform_adapter(
    "ntfy",
    "ntfy 消息通知适配器",
    support_streaming_message=False,
    config_metadata=NTFY_CONFIG_METADATA,
    i18n_resources=NTFY_I18N_RESOURCES,
)
class NtfyPlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self._event_id_timestamps: dict[str, float] = {}
        self.shutdown_event = asyncio.Event()

        server_url = str(
            platform_config.get("ntfy_server_url", "https://ntfy.sh")
        ).strip()
        topic = str(platform_config.get("ntfy_topic", "")).strip()
        access_token = str(platform_config.get("ntfy_access_token", "")).strip()

        logger.info(platform_config)

        if not topic:
            raise ValueError("ntfy 适配器必须配置有效的订阅主题 (topic)。")

        self.ntfy_api = NtfyAPIClient(
            server_url=server_url,
            topic=topic,
            access_token=access_token if access_token else None,
        )
        self._listener_task: asyncio.Task | None = None

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        """Sends messages back using the active session tracking wrapper."""
        # Delegating formatting pipelines downstream into event instance layer
        pass

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="ntfy",
            description="ntfy 消息通知适配器",
            id=cast(str, self.config.get("id", "ntfy")),
            support_streaming_message=False,
        )

    async def run(self) -> None:
        """Launches the background long-polling subscription stream client loop."""
        logger.info(
            "[ntfy] Instantiating subscriber client on topic: %s", self.ntfy_api.topic
        )
        self._listener_task = asyncio.create_task(self._stream_listener_loop())
        await self.shutdown_event.wait()

    async def terminate(self) -> None:
        self.shutdown_event.set()
        if self._listener_task:
            self._listener_task.cancel()
        await self.ntfy_api.close()

    async def _stream_listener_loop(self) -> None:
        """Monitors incoming real-time notifications with an automatic reconnection strategy."""
        while not self.shutdown_event.is_set():
            try:
                async for raw_event in self.ntfy_api.get_stream():
                    if self.shutdown_event.is_set():
                        break

                    if str(raw_event.get("event", "")) != "message":
                        continue

                    # Skips notifications marked with a 'robot' tag to prevent endless feedback loops
                    if "robot" in raw_event.get(
                        "tags", []
                    ) or "AstrBot" in raw_event.get("title", ""):
                        continue

                    event_id = str(raw_event.get("id", ""))
                    if event_id and self._is_duplicate_event(event_id):
                        continue

                    abm = await self.convert_message(raw_event)
                    if abm is None:
                        continue
                    await self.handle_msg(abm)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self.shutdown_event.is_set():
                    logger.warning(
                        "[ntfy] Stream pipe disconnected (%s). Reconnecting in 3s...", e
                    )
                    await asyncio.sleep(3)

    async def convert_message(self, event: dict[str, Any]) -> AstrBotMessage | None:
        message_text = str(event.get("message", ""))
        topic = str(event.get("topic", "unknown"))

        abm = AstrBotMessage()
        abm.self_id = self.meta().id
        abm.message = []
        abm.raw_message = event
        abm.message_id = str(event.get("id") or uuid.uuid4().hex)

        event_timestamp = event.get("time")
        abm.timestamp = (
            int(event_timestamp)
            if isinstance(event_timestamp, int)
            else int(time.time())
        )

        abm.type = MessageType.FRIEND_MESSAGE
        abm.session_id = topic
        abm.sender = MessageMember(
            user_id="ntfy_client", nickname=f"ntfy ({topic[:6]})"
        )

        components = await self._parse_ntfy_message_components(message_text, event)
        if not components:
            return None

        abm.message = components
        abm.message_str = self._build_message_str(components)
        return abm

    async def _parse_ntfy_message_components(
        self, text: str, event: dict[str, Any]
    ) -> list:
        components = []
        if text:
            components.append(Plain(text=text))

        attachment = event.get("attachment")
        if isinstance(attachment, dict):
            file_url = str(attachment.get("url", "")).strip()
            mime_type = str(attachment.get("type", "")).lower().strip()
            filename = str(attachment.get("name", "")).strip() or "attachment.bin"

            if file_url:
                if mime_type.startswith("image/"):
                    components.append(Image.fromURL(file_url))
                elif mime_type.startswith("video/"):
                    components.append(Video.fromURL(file_url))
                elif mime_type.startswith("audio/"):
                    components.append(Record.fromURL(file_url))
                else:
                    components.append(File(name=filename, file=file_url, url=file_url))

        return components

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
        return " ".join(i for i in parts if i).strip()

    def _clean_expired_events(self) -> None:
        current = time.time()
        expired = [
            ev_id
            for ev_id, ts in self._event_id_timestamps.items()
            if current - ts > 1800
        ]
        for ev_id in expired:
            del self._event_id_timestamps[ev_id]

    def _is_duplicate_event(self, event_id: str) -> bool:
        self._clean_expired_events()
        if event_id in self._event_id_timestamps:
            return True
        self._event_id_timestamps[event_id] = time.time()
        return False

    async def handle_msg(self, abm: AstrBotMessage) -> None:
        event = NtfyMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            ntfy_api=self.ntfy_api,
        )
        self._event_queue.put_nowait(event)
