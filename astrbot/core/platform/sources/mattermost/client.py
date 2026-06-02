import asyncio
import json
import mimetypes
from pathlib import Path
from typing import Any

import aiohttp

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain, Record, Reply, Video
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


class MattermostClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._session: aiohttp.ClientSession | None = None

    async def ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def get_json(self, path: str) -> dict[str, Any]:
        session = await self.ensure_session()
        url = f"{self.base_url}/api/v4/{path.lstrip('/')}"
        async with session.get(url, headers=self._headers()) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise RuntimeError(
                    f"Mattermost GET {path} failed: {resp.status} {body}"
                )
            data = await resp.json()
            if not isinstance(data, dict):
                raise RuntimeError(f"Mattermost GET {path} returned non-object JSON")
            return data

    async def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = await self.ensure_session()
        url = f"{self.base_url}/api/v4/{path.lstrip('/')}"
        async with session.post(url, headers=self._headers(), json=payload) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise RuntimeError(
                    f"Mattermost POST {path} failed: {resp.status} {body}"
                )
            data = await resp.json()
            if not isinstance(data, dict):
                raise RuntimeError(f"Mattermost POST {path} returned non-object JSON")
            return data

    async def get_me(self) -> dict[str, Any]:
        return await self.get_json("users/me")

    async def get_channel(self, channel_id: str) -> dict[str, Any]:
        return await self.get_json(f"channels/{channel_id}")

    async def get_file_info(self, file_id: str) -> dict[str, Any]:
        return await self.get_json(f"files/{file_id}/info")

    async def download_file(self, file_id: str) -> bytes:
        session = await self.ensure_session()
        url = f"{self.base_url}/api/v4/files/{file_id}"
        async with session.get(url, headers=self._auth_headers()) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise RuntimeError(
                    f"Mattermost download file {file_id} failed: {resp.status} {body}"
                )
            return await resp.read()

    async def upload_file(
        self,
        channel_id: str,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        session = await self.ensure_session()
        url = f"{self.base_url}/api/v4/files"
        form = aiohttp.FormData()
        form.add_field("channel_id", channel_id)
        form.add_field(
            "files",
            file_bytes,
            filename=filename,
            content_type=content_type,
        )
        async with session.post(url, headers=self._auth_headers(), data=form) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise RuntimeError(
                    f"Mattermost upload file failed: {resp.status} {body}"
                )
            data = await resp.json()
            file_infos = data.get("file_infos", [])
            if not file_infos:
                raise RuntimeError("Mattermost upload file returned no file_infos")
            file_id = file_infos[0].get("id", "")
            if not file_id:
                raise RuntimeError("Mattermost upload file returned empty file id")
            return str(file_id)

    async def create_post(
        self,
        channel_id: str,
        message: str,
        *,
        file_ids: list[str] | None = None,
        root_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "channel_id": channel_id,
            "message": message,
        }
        if file_ids:
            payload["file_ids"] = file_ids
        if root_id:
            payload["root_id"] = root_id
        return await self.post_json("posts", payload)

    async def ws_connect(self) -> aiohttp.ClientWebSocketResponse:
        session = await self.ensure_session()
        ws_url = self.base_url.replace("https://", "wss://", 1).replace(
            "http://", "ws://", 1
        )
        ws_url = f"{ws_url}/api/v4/websocket"
        return await session.ws_connect(ws_url, heartbeat=30.0)

    async def send_message_chain(
        self,
        channel_id: str,
        message_chain: MessageChain,
    ) -> dict[str, Any]:
        text_parts: list[str] = []
        file_ids: list[str] = []
        root_id: str | None = None

        for segment in message_chain.chain:
            if isinstance(segment, Plain):
                text_parts.append(segment.text)
            elif isinstance(segment, At):
                mention_name = str(segment.name or segment.qq or "").strip()
                if mention_name:
                    text_parts.append(f"@{mention_name}")
            elif isinstance(segment, Reply):
                if segment.id:
                    root_id = str(segment.id)
            elif isinstance(segment, Image):
                path = await segment.convert_to_file_path()
                file_path = Path(path)
                file_bytes = await asyncio.to_thread(file_path.read_bytes)
                file_ids.append(
                    await self.upload_file(
                        channel_id,
                        file_bytes,
                        file_path.name,
                        mimetypes.guess_type(file_path.name)[0] or "image/jpeg",
                    )
                )
            elif isinstance(segment, (File, Record, Video)):
                if isinstance(segment, File):
                    path = await segment.get_file()
                    filename = segment.name or Path(path).name
                else:
                    path = await segment.convert_to_file_path()
                    filename = Path(path).name
                file_path = Path(path)
                file_bytes = await asyncio.to_thread(file_path.read_bytes)
                file_ids.append(
                    await self.upload_file(
                        channel_id,
                        file_bytes,
                        filename,
                        mimetypes.guess_type(filename)[0] or "application/octet-stream",
                    )
                )
            else:
                logger.debug(
                    "Mattermost send_message_chain skipped unsupported segment: %s",
                    segment.type,
                )

        return await self.create_post(
            channel_id,
            "".join(text_parts).strip(),
            file_ids=file_ids or None,
            root_id=root_id,
        )

    async def parse_post_attachments(
        self,
        file_ids: list[str],
    ) -> tuple[list[Any], list[str]]:
        components: list[Any] = []
        temp_paths: list[str] = []

        for file_id in file_ids:
            try:
                info = await self.get_file_info(file_id)
                file_bytes = await self.download_file(file_id)
            except Exception as exc:
                logger.warning(
                    "Mattermost fetch attachment failed %s: %s", file_id, exc
                )
                continue

            filename = str(info.get("name") or f"file_{file_id}")
            mime_type = str(info.get("mime_type") or "application/octet-stream")
            suffix = Path(filename).suffix
            file_path = Path(get_astrbot_temp_path()) / f"mattermost_{file_id}{suffix}"
            try:
                await asyncio.to_thread(file_path.write_bytes, file_bytes)
            except OSError as exc:
                logger.warning(
                    "Mattermost write attachment failed %s -> %s: %s",
                    file_id,
                    file_path,
                    exc,
                )
                continue
            temp_paths.append(str(file_path))

            if mime_type.startswith("image/"):
                components.append(Image.fromFileSystem(str(file_path)))
            elif mime_type.startswith("audio/"):
                components.append(Record.fromFileSystem(str(file_path)))
            elif mime_type.startswith("video/"):
                components.append(Video.fromFileSystem(str(file_path)))
            else:
                components.append(File(name=filename, file=str(file_path)))

        return components, temp_paths

    @staticmethod
    def parse_websocket_post(raw_post: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(raw_post)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed
