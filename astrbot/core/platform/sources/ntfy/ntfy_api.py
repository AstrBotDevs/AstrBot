import asyncio
import json
from typing import Any, Optional
from urllib.parse import unquote
import aiohttp

from astrbot.api import logger


class NtfyAPIClient:
    def __init__(
        self,
        *,
        server_url: str,
        topic: str,
        access_token: Optional[str] = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.server_url = server_url.strip().rstrip("/")
        self.topic = topic.strip()
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: Optional[aiohttp.ClientSession] = None

        self.headers = {}
        if access_token:
            self.headers["Authorization"] = f"Bearer {access_token.strip()}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    @property
    def _base_url(self) -> str:
        return f"{self.server_url}/{self.topic}"

    async def get_stream(self) -> Any:
        """Yields live JSON structures from the persistent ntfy event pipe."""
        url = f"{self._base_url}/json"
        session = await self._get_session()
        try:
            async with session.get(url, headers=self.headers, timeout=None) as resp:
                if resp.status != 200:
                    logger.error(
                        "[ntfy-api] Streaming connection failed: status=%s", resp.status
                    )
                    return
                async for line in resp.content:
                    if line:
                        try:
                            yield json.loads(line.decode("utf-8"))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error("[ntfy-api] Exception encountered in stream: %s", e)
            raise e

    async def send_notification(
        self,
        message: str,
        *,
        title: Optional[str] = "AstrBot",
        tags: Optional[list[str]] = None,
        click_url: Optional[str] = None,
        actions: Optional[list[dict[str, Any]]] = None,
    ) -> bool:
        """Sends a standard text notification payload."""
        headers = {**self.headers}
        # if title:
        #     headers["X-Title"] = title
        # if tags:
        #     headers["X-Tags"] = ",".join(tags)
        headers["X-Title"] = "AstrBot"
        headers["X-Tags"] = "robot"
        if click_url:
            headers["X-Click"] = click_url
        if actions:
            headers["X-Actions"] = json.dumps(actions)

        session = await self._get_session()
        try:
            async with session.post(
                self._base_url, data=message.encode("utf-8"), headers=headers
            ) as resp:
                if resp.status < 400:
                    return True
                body = await resp.text()
                logger.error(
                    "[ntfy-api] Post message failed: status=%s body=%s",
                    resp.status,
                    body,
                )
                return False
        except Exception as e:
            logger.error("[ntfy-api] Post message request failed: %s", e)
            return False

    async def send_file(
        self,
        file_bytes: bytes,
        filename: str,
        message: Optional[str] = None,
    ) -> bool:
        """Uploads a rich attachment asset via PUT binary stream."""
        headers = {
            **self.headers,
            "X-Title": "AstrBot",
            "X-Tags": "robot",
            "X-Filename": filename,
        }
        if message:
            headers["X-Message"] = message

        session = await self._get_session()
        try:
            async with session.put(
                self._base_url, data=file_bytes, headers=headers
            ) as resp:
                if resp.status < 400:
                    return True
                body = await resp.text()
                logger.error(
                    "[ntfy-api] Upload file failed: status=%s body=%s",
                    resp.status,
                    body,
                )
                return False
        except Exception as e:
            logger.error("[ntfy-api] Upload file request failed: %s", e)
            return False

    async def get_message_content(
        self, url: str
    ) -> tuple[bytes, str | None, str | None] | None:
        """Downloads external/incoming attachment binary targets if needed."""
        session = await self._get_session()
        try:
            async with session.get(url, headers=self.headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        "[ntfy-api] Content download failed: status=%s body=%s",
                        resp.status,
                        body,
                    )
                    return None

                content = await resp.read()
                content_type = resp.headers.get("Content-Type")
                disposition = resp.headers.get("Content-Disposition")
                filename = self._extract_filename_from_disposition(disposition)
                return content, content_type, filename
        except Exception as e:
            logger.error("[ntfy-api] Content retrieval exception: %s", e)
            return None

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
