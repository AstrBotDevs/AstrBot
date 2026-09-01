import asyncio
import base64
import hmac
import json
from hashlib import sha256
from typing import Any
from urllib.parse import unquote

import aiohttp

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error


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

    async def _get_json(
        self,
        url: str,
        *,
        op_name: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Fetch a JSON object from a LINE Messaging API endpoint.

        Args:
            url: Fully qualified LINE API endpoint.
            op_name: Short operation name used in logs.
            params: Optional query parameters.

        Returns:
            Parsed JSON object, or ``None`` when the request fails.
        """
        session = await self._get_session()
        try:
            async with session.get(
                url,
                headers=self._auth_headers,
                params=params,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.debug(
                        "[LINE] %s failed: status=%s body=%s",
                        op_name,
                        resp.status,
                        body,
                    )
                    return None
                data = await resp.json()
                if isinstance(data, dict):
                    return data
                logger.debug("[LINE] %s returned a non-object response", op_name)
                return None
        except Exception as e:
            logger.debug("[LINE] %s request failed: %s", op_name, safe_error("", e))
            return None

    async def get_group_summary(self, group_id: str) -> dict[str, Any] | None:
        """Get a LINE group chat's name and icon.

        Args:
            group_id: LINE group chat ID.

        Returns:
            Group summary, or ``None`` when unavailable.
        """
        return await self._get_json(
            f"https://api.line.me/v2/bot/group/{group_id}/summary",
            op_name="get group summary",
        )

    async def get_chat_member_count(
        self,
        chat_type: str,
        chat_id: str,
    ) -> int | None:
        """Get the user count for a LINE group or multi-person chat.

        Args:
            chat_type: LINE source type, either ``group`` or ``room``.
            chat_id: LINE group or room ID.

        Returns:
            Member count excluding the bot, or ``None`` when unavailable.
        """
        data = await self._get_json(
            f"https://api.line.me/v2/bot/{chat_type}/{chat_id}/members/count",
            op_name=f"get {chat_type} member count",
        )
        if not data:
            return None
        count = data.get("count")
        return count if isinstance(count, int) and count >= 0 else None

    async def get_chat_member_ids(
        self,
        chat_type: str,
        chat_id: str,
    ) -> list[str] | None:
        """Get all accessible member IDs for a LINE chat.

        LINE returns at most 100 IDs per response. This follows continuation
        tokens until all pages are consumed. The endpoint is restricted to
        verified or premium LINE Official Accounts.

        Args:
            chat_type: LINE source type, either ``group`` or ``room``.
            chat_id: LINE group or room ID.

        Returns:
            Member IDs, or ``None`` when the endpoint is unavailable.
        """
        member_ids: list[str] = []
        start = ""
        seen_tokens: set[str] = set()
        while True:
            data = await self._get_json(
                f"https://api.line.me/v2/bot/{chat_type}/{chat_id}/members/ids",
                op_name=f"get {chat_type} member IDs",
                params={"start": start} if start else None,
            )
            if data is None:
                return None

            page_member_ids = data.get("memberIds")
            if isinstance(page_member_ids, list):
                member_ids.extend(
                    member_id
                    for item in page_member_ids
                    if (member_id := str(item).strip())
                )

            next_token = str(data.get("next", "")).strip()
            if not next_token or next_token in seen_tokens:
                return list(dict.fromkeys(member_ids))
            seen_tokens.add(next_token)
            start = next_token

    async def get_chat_member_profile(
        self,
        chat_type: str,
        chat_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """Get a member profile within a LINE chat.

        Args:
            chat_type: LINE source type, either ``group`` or ``room``.
            chat_id: LINE group or room ID.
            user_id: LINE member user ID.

        Returns:
            Member profile, or ``None`` when unavailable.
        """
        return await self._get_json(
            f"https://api.line.me/v2/bot/{chat_type}/{chat_id}/member/{user_id}",
            op_name=f"get {chat_type} member profile",
        )

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
