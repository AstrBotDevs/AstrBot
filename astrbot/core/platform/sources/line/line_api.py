import asyncio
import base64
import hmac
import json
from hashlib import sha256
from typing import Any
from urllib.parse import unquote

import aiohttp

from astrbot.api import logger


class LineAPIClient:
    def __init__(
        self,
        *,
        channel_access_token: str,
        channel_secret: str,
        timeout_seconds: int = 30,
    ) -> None:
        self.channel_access_token = channel_access_token.strip()
        self.channel_secret = channel_secret.strip()
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def verify_signature(self, raw_body: bytes, signature: str | None) -> bool:
        if not signature:
            return False
        digest = hmac.new(
            self.channel_secret.encode("utf-8"),
            raw_body,
            sha256,
        ).digest()
        expected = base64.b64encode(digest).decode("utf-8")
        return hmac.compare_digest(expected, signature.strip())

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.channel_access_token}"}

    async def reply_message(
        self,
        reply_token: str,
        messages: list[dict[str, Any]],
        *,
        notification_disabled: bool = False,
    ) -> bool:
        payload = {
            "replyToken": reply_token,
            "messages": messages[:5],
            "notificationDisabled": notification_disabled,
        }
        return await self._post_json(
            "https://api.line.me/v2/bot/message/reply",
            payload=payload,
            op_name="reply",
        )

    async def push_message(
        self,
        to: str,
        messages: list[dict[str, Any]],
        *,
        notification_disabled: bool = False,
    ) -> bool:
        payload = {
            "to": to,
            "messages": messages[:5],
            "notificationDisabled": notification_disabled,
        }
        return await self._post_json(
            "https://api.line.me/v2/bot/message/push",
            payload=payload,
            op_name="push",
        )

    async def _post_json(
        self,
        url: str,
        *,
        payload: dict[str, Any],
        op_name: str,
    ) -> bool:
        session = await self._get_session()
        headers = {
            **self._auth_headers,
            "Content-Type": "application/json",
        }
        try:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status < 400:
                    return True
                body = await resp.text()
                logger.error(
                    "[LINE] %s message failed: status=%s body=%s",
                    op_name,
                    resp.status,
                    body,
                )
                return False
        except Exception as e:
            logger.error("[LINE] %s message request failed: %s", op_name, e)
            return False

    async def get_message_content(
        self,
        message_id: str,
    ) -> tuple[bytes, str | None, str | None] | None:
        session = await self._get_session()
        url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
        headers = self._auth_headers

        async with session.get(url, headers=headers) as resp:
            if resp.status == 202:
                if not await self._wait_for_transcoding(message_id):
                    return None
                async with session.get(url, headers=headers) as retry_resp:
                    if retry_resp.status != 200:
                        body = await retry_resp.text()
                        logger.warning(
                            "[LINE] get content retry failed: message_id=%s status=%s body=%s",
                            message_id,
                            retry_resp.status,
                            body,
                        )
                        return None
                    return await self._read_content_response(retry_resp)

            if resp.status != 200:
                body = await resp.text()
                logger.warning(
                    "[LINE] get content failed: message_id=%s status=%s body=%s",
                    message_id,
                    resp.status,
                    body,
                )
                return None
            return await self._read_content_response(resp)

    async def _read_content_response(
        self,
        resp: aiohttp.ClientResponse,
    ) -> tuple[bytes, str | None, str | None]:
        content = await resp.read()
        content_type = resp.headers.get("Content-Type")
        disposition = resp.headers.get("Content-Disposition")
        filename = self._extract_filename_from_disposition(disposition)
        return content, content_type, filename

    def _extract_filename_from_disposition(self, disposition: str | None) -> str | None:
        if not disposition:
            return None
        for part in disposition.split(";"):
            token = part.strip()
            if token.startswith("filename*="):
                val = token.split("=", 1)[1].strip().strip('"')
                if val.lower().startswith("utf-8''"):
                    val = val[7:]
                return unquote(val)
            if token.startswith("filename="):
                return token.split("=", 1)[1].strip().strip('"')
        return None

    async def _wait_for_transcoding(
        self,
        message_id: str,
        *,
        max_attempts: int = 10,
        interval_seconds: float = 1.0,
    ) -> bool:
        session = await self._get_session()
        url = (
            f"https://api-data.line.me/v2/bot/message/{message_id}/content/transcoding"
        )
        headers = self._auth_headers

        for _ in range(max_attempts):
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        await asyncio.sleep(interval_seconds)
                        continue
                    body = await resp.text()
                    data = json.loads(body)
                    status = str(data.get("status", "")).lower()
                    if status == "succeeded":
                        return True
                    if status == "failed":
                        return False
            except Exception:
                pass
            await asyncio.sleep(interval_seconds)
        return False
