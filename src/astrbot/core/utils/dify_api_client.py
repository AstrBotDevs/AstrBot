import json
from astrbot.core import logger
from aiohttp import ClientSession
from typing import Dict, List, Any, AsyncGenerator


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
        inputs: Dict,
        query: str,
        user: str,
        response_mode: str = "streaming",
        conversation_id: str = "",
        files: List[Dict[str, Any]] = [],
        timeout: float = 60,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = f"{self.api_base}/chat-messages"
        payload = locals()
        payload.pop("self")
        payload.pop("timeout")
        logger.info(f"chat_messages payload: {payload}")
        async with self.session.post(
            url, json=payload, headers=self.headers, timeout=timeout
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"chat_messages 请求失败：{resp.status}. {text}")

            buffer = ""
            while True:
                # 保持原有的8192字节限制，防止数据过大导致高水位报错
                chunk = await resp.content.read(8192)
                if not chunk:
                    break

                buffer += chunk.decode("utf-8")
                blocks = buffer.split("\n\n")

                # 处理完整的数据块
                for block in blocks[:-1]:
                    if block.strip() and block.startswith("data:"):
                        try:
                            json_str = block[5:]  # 移除 "data:" 前缀
                            json_obj = json.loads(json_str)
                            yield json_obj
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON解析错误: {str(e)}")
                            logger.error(f"原始数据块: {json_str}")

                # 保留最后一个可能不完整的块
                buffer = blocks[-1] if blocks else ""

    async def workflow_run(
        self,
        inputs: Dict,
        user: str,
        response_mode: str = "streaming",
        files: List[Dict[str, Any]] = [],
        timeout: float = 60,
    ):
        url = f"{self.api_base}/workflows/run"
        payload = locals()
        payload.pop("self")
        payload.pop("timeout")
        logger.info(f"workflow_run payload: {payload}")
        async with self.session.post(
            url, json=payload, headers=self.headers, timeout=timeout
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"workflow_run 请求失败：{resp.status}. {text}")

            buffer = ""
            while True:
                # 保持原有的8192字节限制，防止数据过大导致高水位报错
                chunk = await resp.content.read(8192)
                if not chunk:
                    break

                buffer += chunk.decode("utf-8")
                blocks = buffer.split("\n\n")

                # 处理完整的数据块
                for block in blocks[:-1]:
                    if block.strip() and block.startswith("data:"):
                        try:
                            json_str = block[5:]  # 移除 "data:" 前缀
                            json_obj = json.loads(json_str)
                            yield json_obj
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON解析错误: {str(e)}")
                            logger.error(f"原始数据块: {json_str}")

                # 保留最后一个可能不完整的块
                buffer = blocks[-1] if blocks else ""

    async def file_upload(
        self,
        file_path: str,
        user: str,
    ) -> Dict[str, Any]:
        url = f"{self.api_base}/files/upload"
        payload = {
            "user": user,
            "file": open(file_path, "rb"),
        }
        async with self.session.post(url, data=payload, headers=self.headers) as resp:
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
        self, conversation_id: str, name: str, user: str, auto_generate: bool = False
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
