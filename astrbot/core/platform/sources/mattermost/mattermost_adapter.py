import asyncio
import json
import re
import time
from collections import deque
from typing import Any, cast

import aiohttp

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion

from ...register import register_platform_adapter
from .client import MattermostClient
from .mattermost_event import MattermostMessageEvent


@register_platform_adapter(
    "mattermost",
    "Mattermost 平台适配器",
    support_streaming_message=False,
)
class MattermostPlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.base_url = str(platform_config.get("mattermost_url", "")).rstrip("/")
        self.bot_token = str(platform_config.get("mattermost_bot_token", "")).strip()
        self.reconnect_delay = float(
            platform_config.get("mattermost_reconnect_delay", 5.0)
        )

        if not self.base_url:
            raise ValueError("Mattermost URL 是必需的")
        if not self.bot_token:
            raise ValueError("Mattermost bot token 是必需的")

        self.client = MattermostClient(self.base_url, self.bot_token)
        self.metadata = PlatformMetadata(
            name="mattermost",
            description="Mattermost 平台适配器",
            id=cast(str, self.config.get("id", "mattermost")),
            support_streaming_message=False,
        )
        self.bot_self_id = ""
        self.bot_username = ""
        self._mention_pattern: re.Pattern[str] | None = None
        self._running = True
        self._seen_post_ids: dict[str, float] = {}
        self._seen_post_queue: deque[tuple[str, float]] = deque()
        self._dedup_ttl = 300.0

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        await self.client.send_message_chain(session.session_id, message_chain)
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def run(self) -> None:
        me = await self.client.get_me()
        self.bot_self_id = str(me.get("id", ""))
        self.bot_username = str(me.get("username", ""))
        self._mention_pattern = self._build_mention_pattern(self.bot_username)
        if not self.bot_self_id:
            raise RuntimeError("Mattermost auth succeeded but returned empty user id")

        logger.info(
            "Mattermost auth test OK. Bot: @%s (%s)",
            self.bot_username,
            self.bot_self_id,
        )

        while self._running:
            try:
                await self._ws_connect_and_listen()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._running:
                    break
                logger.warning(
                    "Mattermost websocket disconnected: %s. Retrying in %.1fs.",
                    exc,
                    self.reconnect_delay,
                )
                await asyncio.sleep(self.reconnect_delay)

    async def _ws_connect_and_listen(self) -> None:
        ws = await self.client.ws_connect()
        try:
            await ws.send_json(
                {
                    "seq": 1,
                    "action": "authentication_challenge",
                    "data": {"token": self.bot_token},
                }
            )

            async for message in ws:
                if message.type != aiohttp.WSMsgType.TEXT:
                    if message.type in {
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.CLOSING,
                        aiohttp.WSMsgType.ERROR,
                    }:
                        break
                    continue

                try:
                    payload = json.loads(message.data)
                except json.JSONDecodeError:
                    logger.debug(
                        "Mattermost websocket received non-JSON text frame: %r",
                        message.data,
                    )
                    continue
                if isinstance(payload, dict):
                    await self._handle_ws_event(payload)
        finally:
            await ws.close()

    async def _handle_ws_event(self, payload: dict[str, Any]) -> None:
        if payload.get("event") != "posted":
            return

        data = payload.get("data")
        if not isinstance(data, dict):
            return

        raw_post = data.get("post")
        if not isinstance(raw_post, str):
            return

        post = self.client.parse_websocket_post(raw_post)
        if not post:
            return

        user_id = str(post.get("user_id", ""))
        if not user_id or user_id == self.bot_self_id:
            return
        if post.get("type"):
            return

        post_id = str(post.get("id", ""))
        if post_id and self._is_duplicate_post(post_id):
            return

        abm = await self.convert_message(post=post, data=data)
        if abm is not None:
            await self.handle_msg(abm)

    def _is_duplicate_post(self, post_id: str) -> bool:
        now = time.monotonic()
        self._prune_seen_posts(now)
        if post_id in self._seen_post_ids:
            return True
        self._seen_post_ids[post_id] = now
        self._seen_post_queue.append((post_id, now))
        return False

    def _prune_seen_posts(self, now: float) -> None:
        while self._seen_post_queue:
            queued_post_id, seen_at = self._seen_post_queue[0]
            if now - seen_at <= self._dedup_ttl:
                break
            self._seen_post_queue.popleft()
            current_seen_at = self._seen_post_ids.get(queued_post_id)
            if current_seen_at == seen_at:
                del self._seen_post_ids[queued_post_id]

    async def convert_message(
        self,
        *,
        post: dict[str, Any],
        data: dict[str, Any],
    ) -> AstrBotMessage | None:
        channel_id = str(post.get("channel_id", "") or "")
        if not channel_id:
            return None

        channel_type = str(data.get("channel_type", "O") or "O")
        sender_id = str(post.get("user_id", "") or "")
        sender_name = str(data.get("sender_name", "") or sender_id).lstrip("@")
        message_text = str(post.get("message", "") or "")
        file_ids = [
            str(file_id)
            for file_id in (post.get("file_ids") or [])
            if str(file_id).strip()
        ]

        abm = AstrBotMessage()
        abm.self_id = self.bot_self_id
        abm.sender = MessageMember(user_id=sender_id, nickname=sender_name)
        abm.session_id = channel_id
        abm.message_id = str(post.get("id") or channel_id)
        abm.raw_message = post
        abm.timestamp = self._parse_timestamp(post.get("create_at"))
        abm.message = self._parse_text_components(message_text)

        if channel_type == "D":
            abm.type = MessageType.FRIEND_MESSAGE
        else:
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = channel_id

        if file_ids:
            (
                attachment_components,
                temp_paths,
            ) = await self.client.parse_post_attachments(file_ids)
            abm.message.extend(attachment_components)
            setattr(abm, "temporary_file_paths", temp_paths)

        abm.message_str = self._build_message_str(
            abm.message,
            message_text,
            self.bot_self_id,
        )
        return abm

    def _parse_text_components(self, message_text: str) -> list[Any]:
        if not message_text:
            return []

        components: list[Any] = []
        if not self.bot_username:
            return [Plain(message_text)]

        mention_pattern = self._mention_pattern
        if mention_pattern is None:
            mention_pattern = self._build_mention_pattern(self.bot_username)
            if mention_pattern is None:
                return [Plain(message_text)]
        last_end = 0

        for match in mention_pattern.finditer(message_text):
            if match.start() > last_end:
                components.append(Plain(message_text[last_end : match.start()]))
            components.append(At(qq=self.bot_self_id, name=self.bot_username))
            last_end = match.end()

        if last_end < len(message_text):
            components.append(Plain(message_text[last_end:]))

        if not components:
            components.append(Plain(message_text))
        return components

    @staticmethod
    def _build_mention_pattern(bot_username: str) -> re.Pattern[str] | None:
        if not bot_username:
            return None
        return re.compile(
            rf"(?<![A-Za-z0-9_.-])@{re.escape(bot_username)}(?![A-Za-z0-9_.-])",
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _build_message_str(
        components: list[Any],
        fallback: str,
        self_id: str,
    ) -> str:
        text_parts: list[str] = []
        leading_self_mention_skipped = False

        for component in components:
            if isinstance(component, Plain):
                text_parts.append(component.text)
            elif isinstance(component, At):
                is_self_mention = str(component.qq) == self_id
                if not leading_self_mention_skipped and is_self_mention:
                    leading_self_mention_skipped = True
                    if not text_parts or not "".join(text_parts).strip():
                        continue
                mention_name = str(component.name or component.qq or "").strip()
                if mention_name:
                    text_parts.append(f"@{mention_name}")
        message_str = "".join(text_parts).strip()
        return message_str or fallback.strip()

    @staticmethod
    def _parse_timestamp(raw_value: Any) -> int:
        if isinstance(raw_value, int):
            return raw_value // 1000 if raw_value > 1_000_000_000_000 else raw_value
        return int(time.time())

    async def handle_msg(self, message: AstrBotMessage) -> None:
        message_event = MattermostMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )
        self.commit_event(message_event)

    async def terminate(self) -> None:
        self._running = False
        await self.client.close()

    def get_client(self) -> MattermostClient:
        return self.client
