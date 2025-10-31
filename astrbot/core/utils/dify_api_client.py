import codecs
import json
from collections.abc import AsyncGenerator
from typing import Any

from aiohttp import ClientResponse, ClientSession

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
        files: list[dict[str, Any]] = [],
        timeout: float = 60,
    ) -> AsyncGenerator[dict[str, Any], None]:
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
        files: list[dict[str, Any]] = [],
        timeout: float = 60,
    ):
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
        file_path: str,
        user: str,
    ) -> dict[str, Any]:
        url = f"{self.api_base}/files/upload"
        with open(file_path, "rb") as f:
            payload = {
                "user": user,
                "file": f,
            }
            async with self.session.post(
                url,
                data=payload,
                headers=self.headers,
            ) as resp:
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
