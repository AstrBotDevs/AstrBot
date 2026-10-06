"""Sendblue direct-message iMessage/SMS adapter."""

import asyncio
import hmac
import json
import re
from collections import OrderedDict
from typing import Any

import httpx

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.message_session import MessageSesion
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.utils.webhook_utils import log_webhook_info

_PHONE = re.compile(r"\+[1-9][0-9]{7,14}\Z")


@register_platform_adapter(
    "sendblue", "Sendblue iMessage and SMS", support_streaming_message=False
)
class SendblueAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ):
        super().__init__(platform_config, event_queue)
        self.config["unified_webhook_mode"] = True
        self.from_number = platform_config.get("sendblue_from_number", "")
        self.allow_from = platform_config.get("sendblue_allow_from", [])
        self.signing_secret = platform_config.get("sendblue_signing_secret", "")
        key = platform_config.get("sendblue_api_key", "")
        secret = platform_config.get("sendblue_api_secret", "")
        if not all(
            isinstance(value, str) and value
            for value in (self.from_number, self.signing_secret, key, secret)
        ):
            raise ValueError(
                "Sendblue requires API credentials, a signing secret and a sending line"
            )
        if not _PHONE.fullmatch(self.from_number):
            raise ValueError("Sendblue sending line must be an E.164 number")
        if (
            not isinstance(self.allow_from, list)
            or not self.allow_from
            or any(
                not isinstance(number, str)
                or (number != "*" and not _PHONE.fullmatch(number))
                for number in self.allow_from
            )
        ):
            raise ValueError(
                "Sendblue requires a nonempty E.164 sender allowlist (or explicit '*')"
            )
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._stopped = asyncio.Event()
        self.client = httpx.AsyncClient(
            base_url="https://api.sendblue.com",
            headers={"sb-api-key-id": key, "sb-api-secret-key": secret},
            timeout=30,
            follow_redirects=False,
        )

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="sendblue",
            description="Sendblue iMessage and SMS",
            id=self.config.get("id", "sendblue"),
            support_streaming_message=False,
        )

    async def run(self) -> None:
        if not self.config.get("webhook_uuid"):
            raise ValueError(
                "Sendblue requires a generated webhook UUID; save the bot configuration first"
            )
        log_webhook_info(self.meta().id, self.config["webhook_uuid"])
        await self._stopped.wait()

    async def terminate(self) -> None:
        self._stopped.set()
        await self.client.aclose()

    async def webhook_callback(self, request: Any) -> tuple[str, int]:
        """Authenticate and enqueue a bounded direct-message callback.

        Args:
            request: DashboardRequest supplied by the unified webhook route.

        Returns:
            Plain HTTP acknowledgement and status. Accepted messages are held in
            AstrBot's process-local event queue, not a durable inbox.
        """
        if request.method != "POST":
            return "method not allowed", 405
        if not hmac.compare_digest(
            request.headers.get("sb-signing-secret", "").encode(),
            self.signing_secret.encode(),
        ):
            return "unauthorized", 401
        try:
            raw = await request.get_data(max_size=65536)
        except ValueError:
            return "payload too large", 413
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return "bad request", 400
        if not isinstance(payload, dict):
            return "bad request", 400
        if (
            payload.get("is_outbound") is not False
            or payload.get("status") != "RECEIVED"
            or payload.get("group_id") not in (None, "")
            or payload.get("to_number") != self.from_number
        ):
            return "ignored", 200
        sender, handle = payload.get("from_number"), payload.get("message_handle")
        content, media = payload.get("content"), payload.get("media_url")
        if (
            not isinstance(sender, str)
            or not _PHONE.fullmatch(sender)
            or not isinstance(handle, str)
            or not 0 < len(handle) <= 256
            or (content is not None and not isinstance(content, str))
            or (media is not None and not isinstance(media, str))
        ):
            return "bad request", 400
        if sender not in self.allow_from and "*" not in self.allow_from:
            return "ignored", 200
        if handle in self._seen:
            return "duplicate", 200
        text = content or ""
        if media:
            text += "\n[Attachment received; this channel supports text only. Please resend its contents as text.]"
        if not text.strip():
            return "ignored", 200
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.self_id = self.from_number
        message.session_id = sender
        message.sender = MessageMember(user_id=sender)
        message.message_id = handle
        message.message_str = text
        message.message = [Plain(text=text)]
        # Retain the correlation ID, not the callback's account metadata or media URL.
        message.raw_message = {"message_handle": handle}
        # The global queue may be unbounded; this adapter applies its own admission cap.
        if self._event_queue.qsize() >= 128:
            return "busy", 503
        try:
            self.commit_event(SendblueMessageEvent(message, self))
        except asyncio.QueueFull:
            return "busy", 503
        self._seen[handle] = None
        if len(self._seen) > 4096:
            self._seen.popitem(last=False)
        return "ok", 200

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ) -> None:
        if session.message_type != MessageType.FRIEND_MESSAGE:
            raise ValueError("Sendblue supports direct messages only")
        await self.send_text(session.session_id, message_chain)
        await super().send_by_session(session, message_chain)

    async def send_text(self, recipient: str, message: MessageChain) -> None:
        """Deliver text once; require provider acceptance without retrying POSTs.

        Args:
            recipient: Authorized E.164 recipient number.
            message: Text-only message chain to deliver in 2000-character chunks.

        Raises:
            ValueError: The recipient or message type is unsupported.
            RuntimeError: Provider acceptance could not be confirmed. Earlier chunks
                may have been accepted; inspect Sendblue before manually retrying.
        """
        if not _PHONE.fullmatch(recipient) or (
            recipient not in self.allow_from and "*" not in self.allow_from
        ):
            raise ValueError("Sendblue recipient must be an allowed E.164 number")
        if any(not isinstance(part, Plain) for part in message.chain):
            raise ValueError(
                "Sendblue supports text only; media delivery is unavailable"
            )
        text = message.get_plain_text()
        for offset in range(0, len(text), 2000):
            try:
                response = await self.client.post(
                    "/api/send-message",
                    json={
                        "number": recipient,
                        "from_number": self.from_number,
                        "content": text[offset : offset + 2000],
                    },
                )
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise RuntimeError(
                    "Sendblue delivery unconfirmed; inspect provider status before retrying"
                ) from exc
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("message_handle"), str)
                or not data["message_handle"]
                or data.get("error_code") not in (None, 0)
                or data.get("status") not in ("QUEUED", "SENT", "DELIVERED", "READ")
            ):
                raise RuntimeError(
                    "Sendblue did not confirm acceptance; inspect provider status before retrying"
                )


class SendblueMessageEvent(AstrMessageEvent):
    def __init__(self, message: AstrBotMessage, adapter: SendblueAdapter):
        super().__init__(
            message.message_str, message, adapter.meta(), message.session_id
        )
        self.adapter = adapter

    async def send(self, message: MessageChain) -> None:
        await self.adapter.send_text(self.get_sender_id(), message)
        await super().send(message)
