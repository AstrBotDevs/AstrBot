import json
from aiohttp import ClientSession
from typing import Dict, List, Any, AsyncGenerator


class DifyAPIClient:
    def __init__(self, api_key: str, api_base: str = "https://api.dify.ai/v1"):
        self.api_key = api_key
        self.api_base = api_base
        self.session = ClientSession()
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
        async with self.session.post(
            url, json=payload, headers=self.headers, timeout=timeout
        ) as resp:
            async for data in resp.content:
                if not data.strip():
                    continue
                if data.startswith(b"data:"):
                    yield json.loads(data[5:])
                    
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
        async with self.session.post(
            url, json=payload, headers=self.headers, timeout=timeout
        ) as resp:
            async for data in resp.content:
                if not data.strip():
                    continue
                if data.startswith(b"data:"):
                    yield json.loads(data[5:])
                    
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
        async with self.session.post(
            url, data=payload, headers=self.headers
        ) as resp:
            return await resp.json() # {"id": "xxx", ...}
        
        
        
                
    async def close(self):
        await self.session.close()