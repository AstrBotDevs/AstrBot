import codecs
import json
from collections.abc import AsyncGenerator
from typing import Any

from aiohttp import ClientResponse, ClientSession, FormData

from astrbot.core import logger


async def _stream_sse(resp: ClientResponse) -> AsyncGenerator[dict, None]:
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer = ""
    async for chunk in resp.content.iter_chunked(8192):
        buffer += decoder.decode(chunk)
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            if block.strip().startswith("data:"):
                try:
                    yield json.loads(block[5:])
                except json.JSONDecodeError:
                    logger.warning(f"Drop invalid dify json data: {block[5:]}")
                    continue
    # flush any remaining text
    buffer += decoder.decode(b"", final=True)
    if buffer.strip().startswith("data:"):
        try:
            yield json.loads(buffer[5:])
        except json.JSONDecodeError:
            logger.warning(f"Drop invalid dify json data: {buffer[5:]}")


class DifyAPIClient:
    def __init__(self, api_key: str, api_base: str = "https://api.dify.ai/v1"):
        self.api_key = api_key
        self.api_base = api_base
        self.session = ClientSession(trust_env=True)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

    async def chat_messages(
        self,
        inputs: dict,
        query: str,
        user: str,
        response_mode: str = "streaming",
        conversation_id: str = "",
        files: list[dict[str, Any]] | None = None,
        timeout: float = 60,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if files is None:
            files = []
        url = f"{self.api_base}/chat-messages"
        payload = locals()
        payload.pop("self")
        payload.pop("timeout")
        logger.info(f"chat_messages payload: {payload}")
        async with self.session.post(
            url,
            json=payload,
            headers=self.headers,
            timeout=timeout,
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(
                    f"Dify /chat-messages 接口请求失败：{resp.status}. {text}",
                )
            async for event in _stream_sse(resp):
                yield event

    async def workflow_run(
        self,
        inputs: dict,
        user: str,
        response_mode: str = "streaming",
        files: list[dict[str, Any]] | None = None,
        timeout: float = 60,
    ):
        if files is None:
            files = []
        url = f"{self.api_base}/workflows/run"
        payload = locals()
        payload.pop("self")
        payload.pop("timeout")
        logger.info(f"workflow_run payload: {payload}")
        async with self.session.post(
            url,
            json=payload,
            headers=self.headers,
            timeout=timeout,
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(
                    f"Dify /workflows/run 接口请求失败：{resp.status}. {text}",
                )
            async for event in _stream_sse(resp):
                yield event

    async def file_upload(
        self,
        user: str,
        file_path: str | None = None,
        file_data: bytes | None = None,
        file_name: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        """Upload a file to Dify. Must provide either file_path or file_data.

        Args:
            user: The user ID.
            file_path: The path to the file to upload.
            file_data: The file data in bytes.
            file_name: Optional file name when using file_data.
        Returns:
            A dictionary containing the uploaded file information.
        """
        url = f"{self.api_base}/files/upload"

        form = FormData()
        form.add_field("user", user)

        if file_data is not None:
            # 使用 bytes 数据
            form.add_field(
                "file",
                file_data,
                filename=file_name or "uploaded_file",
                content_type=mime_type or "application/octet-stream",
            )
        elif file_path is not None:
            # 使用文件路径
            import os

            with open(file_path, "rb") as f:
                file_content = f.read()
                form.add_field(
                    "file",
                    file_content,
                    filename=os.path.basename(file_path),
                    content_type=mime_type or "application/octet-stream",
                )
        else:
            raise ValueError("file_path 和 file_data 不能同时为 None")

        async with self.session.post(
            url,
            data=form,
            headers=self.headers,  # 不包含 Content-Type，让 aiohttp 自动设置
        ) as resp:
            if resp.status != 200 and resp.status != 201:
                text = await resp.text()
                raise Exception(f"Dify 文件上传失败：{resp.status}. {text}")
            return await resp.json()  # {"id": "xxx", ...}

    async def close(self):
        await self.session.close()

    async def get_chat_convs(self, user: str, limit: int = 20):
        # conversations. GET
        url = f"{self.api_base}/conversations"
        payload = {
            "user": user,
            "limit": limit,
        }
        async with self.session.get(url, params=payload, headers=self.headers) as resp:
            return await resp.json()

    async def delete_chat_conv(self, user: str, conversation_id: str):
        # conversation. DELETE
        url = f"{self.api_base}/conversations/{conversation_id}"
        payload = {
            "user": user,
        }
        async with self.session.delete(url, json=payload, headers=self.headers) as resp:
            return await resp.json()

    async def rename(
        self,
        conversation_id: str,
        name: str,
        user: str,
        auto_generate: bool = False,
    ):
        # /conversations/:conversation_id/name
        url = f"{self.api_base}/conversations/{conversation_id}/name"
        payload = {
            "user": user,
            "name": name,
            "auto_generate": auto_generate,
        }
        async with self.session.post(url, json=payload, headers=self.headers) as resp:
            return await resp.json()
