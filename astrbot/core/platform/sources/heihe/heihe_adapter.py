import asyncio
import json
import time
import uuid
from collections.abc import Mapping
from typing import Any, cast

import websockets
from websockets.asyncio.client import ClientConnection, connect

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    Group,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion

from ...register import register_platform_adapter
from .heihe_event import HeiheMessageEvent

HEIHE_CONFIG_METADATA = {
    "heihe_ws_url": {
        "description": "Heihe WebSocket URL",
        "type": "string",
        "hint": "一般情况下不需要修改。",
    },
    "heihe_token": {
        "description": "Bot Token",
        "type": "string",
        "hint": "黑盒 Bot Token。可填写纯 Token（推荐），适配器会自动添加 Authorization 头。",
    },
    "heihe_origin": {
        "description": "WebSocket Origin",
        "type": "string",
        "hint": "用于 WebSocket 握手的 Origin 头，默认 https://chat.xiaoheihe.cn。",
    },
    "heihe_bot_id": {
        "description": "Bot ID",
        "type": "string",
        "hint": "可选。为空时会根据收到的消息自动识别机器人 ID。",
    },
    "heihe_auto_reconnect": {
        "description": "Auto Reconnect",
        "type": "bool",
        "hint": "WebSocket 断开后是否自动重连。",
    },
    "heihe_heartbeat_interval": {
        "description": "Heartbeat Interval (seconds)",
        "type": "int",
        "hint": "发送心跳包间隔。<=0 表示关闭主动心跳。",
    },
    "heihe_reconnect_delay": {
        "description": "Reconnect Delay (seconds)",
        "type": "int",
        "hint": "WebSocket 断开后的重连等待时间。",
    },
    "heihe_ignore_self_message": {
        "description": "Ignore Self Message",
        "type": "bool",
        "hint": "是否忽略机器人自身发送的消息。",
    },
}

HEIHE_I18N_RESOURCES = {
    "zh-CN": {
        "heihe_ws_url": {
            "description": "黑盒 WebSocket 地址",
            "hint": "一般情况下不需要修改。",
        },
        "heihe_token": {
            "description": "机器人 Token",
            "hint": "建议填写纯 Token，适配器会自动补齐 Authorization 头。",
        },
        "heihe_origin": {
            "description": "WebSocket Origin",
            "hint": "用于握手的 Origin 头，默认 https://chat.xiaoheihe.cn。",
        },
        "heihe_bot_id": {
            "description": "机器人 ID",
            "hint": "可选。为空时会根据收到的消息自动识别机器人 ID。",
        },
        "heihe_auto_reconnect": {
            "description": "自动重连",
            "hint": "WebSocket 断开后是否自动重连。",
        },
        "heihe_heartbeat_interval": {
            "description": "心跳间隔（秒）",
            "hint": "设置 <=0 将关闭主动心跳。",
        },
        "heihe_reconnect_delay": {
            "description": "重连间隔（秒）",
            "hint": "WebSocket 断开后的重连等待时间。",
        },
        "heihe_ignore_self_message": {
            "description": "忽略机器人自身消息",
            "hint": "开启后，机器人自己发出的消息将不会触发事件处理。",
        },
    },
    "en-US": {
        "heihe_ws_url": {
            "description": "Heihe WebSocket URL",
            "hint": "Usually no need to change this.",
        },
        "heihe_token": {
            "description": "Bot Token",
            "hint": "Plain token is recommended. Authorization header is added automatically.",
        },
        "heihe_origin": {
            "description": "WebSocket Origin",
            "hint": "Origin header used in websocket handshake. Default: https://chat.xiaoheihe.cn.",
        },
        "heihe_bot_id": {
            "description": "Bot ID",
            "hint": "Optional. If empty, the adapter will infer it from incoming messages.",
        },
        "heihe_auto_reconnect": {
            "description": "Auto Reconnect",
            "hint": "Whether to reconnect automatically after websocket disconnects.",
        },
        "heihe_heartbeat_interval": {
            "description": "Heartbeat Interval (seconds)",
            "hint": "Set <=0 to disable active heartbeat.",
        },
        "heihe_reconnect_delay": {
            "description": "Reconnect Delay (seconds)",
            "hint": "Delay before reconnecting after disconnect.",
        },
        "heihe_ignore_self_message": {
            "description": "Ignore Self Message",
            "hint": "When enabled, messages sent by the bot itself will be ignored.",
        },
    },
}


@register_platform_adapter(
    "heihe",
    "黑盒机器人（WebSocket）适配器",
    support_streaming_message=False,
    default_config_tmpl={
        "id": "heihe",
        "type": "heihe",
        "enable": False,
        "heihe_ws_url": "wss://chat.xiaoheihe.cn/chatroom/ws/connect",
        "heihe_token": "",
        "heihe_origin": "https://chat.xiaoheihe.cn",
        "heihe_bot_id": "",
        "heihe_auto_reconnect": True,
        "heihe_heartbeat_interval": 20,
        "heihe_reconnect_delay": 5,
        "heihe_ignore_self_message": True,
    },
    config_metadata=HEIHE_CONFIG_METADATA,
    i18n_resources=HEIHE_I18N_RESOURCES,
)
class HeihePlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings

        self.ws_url = str(platform_config.get("heihe_ws_url", "")).strip()
        self.token = str(platform_config.get("heihe_token", "")).strip()
        self.origin = str(
            platform_config.get("heihe_origin", "https://chat.xiaoheihe.cn"),
        ).strip()
        self.bot_id = str(platform_config.get("heihe_bot_id", "")).strip()
        self.auto_reconnect = bool(platform_config.get("heihe_auto_reconnect", True))
        self.heartbeat_interval = int(
            cast(int, platform_config.get("heihe_heartbeat_interval", 20)),
        )
        self.reconnect_delay = int(
            cast(int, platform_config.get("heihe_reconnect_delay", 5)),
        )
        self.ignore_self_message = bool(
            platform_config.get("heihe_ignore_self_message", True),
        )

        if not self.ws_url:
            raise ValueError("heihe_ws_url 不能为空。")

        self.metadata = PlatformMetadata(
            name="heihe",
            description="黑盒机器人（WebSocket）适配器",
            id=cast(str, self.config.get("id", "heihe")),
            support_streaming_message=False,
        )

        self.ws: ClientConnection | None = None
        self.running = False
        self.heartbeat_task: asyncio.Task | None = None
        self._last_heartbeat_ts = 0

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def run(self) -> None:
        self.running = True
        while self.running:
            try:
                await self._connect_and_loop()
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning("[heihe] websocket disconnected: %s", e)
            except Exception as e:
                logger.error("[heihe] websocket failed: %s", e)

            if not self.running:
                break
            if not self.auto_reconnect:
                break
            await asyncio.sleep(max(1, self.reconnect_delay))

    async def terminate(self) -> None:
        self.running = False
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        await HeiheMessageEvent.send_with_adapter(
            self,
            message_chain,
            session.session_id,
        )
        await super().send_by_session(session, message_chain)

    async def send_payload(self, payload: Mapping[str, Any]) -> None:
        if not self.ws:
            raise RuntimeError("[heihe] websocket not connected")
        if self.ws.close_code is not None:
            raise RuntimeError("[heihe] websocket already closed")

        body = dict(payload)
        body.setdefault("timestamp", int(time.time()))
        await self.ws.send(json.dumps(body, ensure_ascii=False))

    async def _connect_and_loop(self) -> None:
        logger.info("[heihe] connecting websocket: %s", self.ws_url)

        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-Token"] = self.token

        websocket = await connect(
            self.ws_url,
            additional_headers=headers,
            max_size=10 * 1024 * 1024,
            ping_interval=None,
        )
        self.ws = websocket
        logger.info("[heihe] websocket connected")

        if self.heartbeat_interval > 0:
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            async for raw in websocket:
                await self._handle_incoming(raw)
        finally:
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    pass
                self.heartbeat_task = None
            if self.ws:
                try:
                    await self.ws.close()
                except Exception:
                    pass
                self.ws = None

    async def _heartbeat_loop(self) -> None:
        try:
            while self.running and self.ws and self.ws.close_code is None:
                await asyncio.sleep(self.heartbeat_interval)
                self._last_heartbeat_ts = int(time.time())
                await self.send_payload(
                    {
                        "type": "ping",
                        "ping": self._last_heartbeat_ts,
                    },
                )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("[heihe] heartbeat error: %s", e)

    async def _handle_incoming(self, raw: Any) -> None:
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError:
                return
        if not isinstance(raw, str):
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("[heihe] skip non-json frame: %s", raw[:200])
            return

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    await self._handle_packet(item)
            return
        if isinstance(data, dict):
            await self._handle_packet(data)

    async def _handle_packet(self, packet: dict[str, Any]) -> None:
        if "ping" in packet:
            await self.send_payload({"type": "pong", "pong": packet.get("ping")})
            return
        if str(packet.get("type", "")).lower() == "ping":
            await self.send_payload({"type": "pong", "pong": packet.get("ping")})
            return

        event_type = str(
            packet.get("event")
            or packet.get("event_type")
            or packet.get("type")
            or packet.get("topic")
            or "",
        ).lower()
        payload_obj = packet.get("data")
        payload = payload_obj if isinstance(payload_obj, dict) else packet

        if not self._is_message_event(event_type, payload):
            return

        abm = self._convert_message(payload, packet)
        if not abm:
            return
        await self.handle_msg(abm)

    @staticmethod
    def _is_message_event(event_type: str, payload: Mapping[str, Any]) -> bool:
        if "message" in event_type:
            return True
        keys = payload.keys()
        return "content" in keys or "text" in keys or "message" in keys

    def _convert_message(
        self,
        payload: Mapping[str, Any],
        raw_packet: Mapping[str, Any],
    ) -> AstrBotMessage | None:
        message_obj = payload.get("message")
        message = message_obj if isinstance(message_obj, Mapping) else payload

        sender_data_obj = (
            payload.get("sender") or payload.get("author") or payload.get("user") or {}
        )
        sender_data = sender_data_obj if isinstance(sender_data_obj, Mapping) else {}
        sender_id = str(
            sender_data.get("id")
            or sender_data.get("user_id")
            or payload.get("sender_id")
            or payload.get("user_id")
            or "",
        ).strip()
        sender_name = str(
            sender_data.get("nickname")
            or sender_data.get("name")
            or sender_data.get("username")
            or sender_id
            or "unknown",
        )

        self_id = str(
            payload.get("self_id")
            or payload.get("bot_id")
            or self.bot_id
            or self.meta().id,
        )
        if self.ignore_self_message and sender_id and self_id and sender_id == self_id:
            return None

        channel_id = str(
            payload.get("channel_id")
            or payload.get("room_id")
            or payload.get("chat_id")
            or payload.get("session_id")
            or "",
        ).strip()
        guild_id = str(
            payload.get("guild_id")
            or payload.get("server_id")
            or payload.get("group_id")
            or "",
        ).strip()
        is_private = bool(payload.get("is_private", False))
        if str(payload.get("message_type", "")).lower() in {"private", "friend", "dm"}:
            is_private = True

        session_id = channel_id or sender_id
        if not session_id:
            return None

        text = str(message.get("content") or message.get("text") or "").strip()
        components = self._build_components(text, payload)
        if not components:
            return None

        abm = AstrBotMessage()
        abm.self_id = self_id
        abm.message_id = str(
            message.get("id")
            or message.get("message_id")
            or payload.get("message_id")
            or payload.get("msg_id")
            or uuid.uuid4().hex
        )
        timestamp_raw = (
            payload.get("timestamp")
            or payload.get("time")
            or message.get("timestamp")
            or message.get("time")
        )
        abm.timestamp = int(time.time())
        if isinstance(timestamp_raw, int):
            abm.timestamp = (
                timestamp_raw // 1000
                if timestamp_raw > 1_000_000_000_000
                else timestamp_raw
            )

        if not is_private and (channel_id or guild_id):
            abm.type = MessageType.GROUP_MESSAGE
            abm.group = Group(
                group_id=guild_id or channel_id, group_name=guild_id or ""
            )
        else:
            abm.type = MessageType.FRIEND_MESSAGE

        abm.session_id = session_id
        abm.sender = MessageMember(user_id=sender_id or "unknown", nickname=sender_name)
        abm.message = components
        abm.message_str = self._build_message_str(components)
        abm.raw_message = dict(raw_packet)
        return abm

    @staticmethod
    def _build_components(text: str, payload: Mapping[str, Any]) -> list:
        components: list = []
        if text:
            components.append(Plain(text=text))

        mentions_obj = payload.get("mentions")
        if isinstance(mentions_obj, list):
            for mention in mentions_obj:
                if not isinstance(mention, Mapping):
                    continue
                user_id = str(mention.get("user_id") or mention.get("id") or "").strip()
                name = str(mention.get("name") or mention.get("nickname") or "").strip()
                if user_id or name:
                    components.append(At(qq=user_id, name=name))

        attachments_obj = payload.get("attachments")
        if isinstance(attachments_obj, list):
            for item in attachments_obj:
                if not isinstance(item, Mapping):
                    continue
                url = str(item.get("url") or item.get("file_url") or "").strip()
                if not url:
                    continue
                kind = str(item.get("type") or item.get("media_type") or "").lower()
                if "image" in kind:
                    components.append(Image.fromURL(url))
                else:
                    components.append(Plain(text=f"[{kind or 'file'}] {url}"))
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
            else:
                parts.append(f"[{comp.type}]")
        return " ".join(i for i in parts if i).strip()

    async def handle_msg(self, abm: AstrBotMessage) -> None:
        event = HeiheMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            adapter=self,
        )
        self.commit_event(event)
