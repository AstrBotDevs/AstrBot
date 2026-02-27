from astrbot.core.lang import t
import asyncio
import io
import json
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

from astrbot.core import logger


class CozeAPIClient:
    def __init__(self, api_key: str, api_base: str = "https://api.coze.cn") -> None:
        self.api_key = api_key
        self.api_base = api_base
        self.session = None

    async def _ensure_session(self):
        """确保HTTP session存在"""
        if self.session is None:
            connector = aiohttp.TCPConnector(
                ssl=False if self.api_base.startswith("http://") else True,
                limit=100,
                limit_per_host=30,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
            )
            timeout = aiohttp.ClientTimeout(
                total=120,  # 默认超时时间
                connect=30,
                sock_read=120,
            )
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "text/event-stream",
            }
            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=timeout,
                connector=connector,
            )
        return self.session

    async def upload_file(
        self,
        file_data: bytes,
    ) -> str:
        """上传文件到 Coze 并返回 file_id

        Args:
            file_data (bytes): 文件的二进制数据
        Returns:
            str: 上传成功后返回的 file_id

        """
        session = await self._ensure_session()
        url = f"{self.api_base}/v1/files/upload"

        try:
            file_io = io.BytesIO(file_data)
            async with session.post(
                url,
                data={
                    "file": file_io,
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status == 401:
                    raise Exception(t("msg-76f97104"))

                response_text = await response.text()
                logger.debug(
                    t("msg-3653b652", res=response.status, response_text=response_text),
                )

                if response.status != 200:
                    raise Exception(
                        t("msg-13fe060c", res=response.status, response_text=response_text),
                    )

                try:
                    result = await response.json()
                except json.JSONDecodeError:
                    raise Exception(t("msg-5604b862", response_text=response_text))

                if result.get("code") != 0:
                    raise Exception(t("msg-c0373c50", res=result.get('msg', '未知错误')))

                file_id = result["data"]["id"]
                logger.debug(t("msg-010e4299", file_id=file_id))
                return file_id

        except asyncio.TimeoutError:
            logger.error(t("msg-719f13cb"))
            raise Exception(t("msg-719f13cb"))
        except Exception as e:
            logger.error(t("msg-121c11fb", e=e))
            raise Exception(t("msg-121c11fb", e=e))

    async def download_image(self, image_url: str) -> bytes:
        """下载图片并返回字节数据

        Args:
            image_url (str): 图片的URL
        Returns:
            bytes: 图片的二进制数据

        """
        session = await self._ensure_session()

        try:
            async with session.get(image_url) as response:
                if response.status != 200:
                    raise Exception(t("msg-f6101892", res=response.status))

                image_data = await response.read()
                return image_data

        except Exception as e:
            logger.error(t("msg-c09c56c9", image_url=image_url, e=e))
            raise Exception(t("msg-15211c7c", e=e))

    async def chat_messages(
        self,
        bot_id: str,
        user_id: str,
        additional_messages: list[dict] | None = None,
        conversation_id: str | None = None,
        auto_save_history: bool = True,
        stream: bool = True,
        timeout: float = 120,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """发送聊天消息并返回流式响应

        Args:
            bot_id: Bot ID
            user_id: 用户ID
            additional_messages: 额外消息列表
            conversation_id: 会话ID
            auto_save_history: 是否自动保存历史
            stream: 是否流式响应
            timeout: 超时时间

        """
        session = await self._ensure_session()
        url = f"{self.api_base}/v3/chat"

        payload = {
            "bot_id": bot_id,
            "user_id": user_id,
            "stream": stream,
            "auto_save_history": auto_save_history,
        }

        if additional_messages:
            payload["additional_messages"] = additional_messages

        params = {}
        if conversation_id:
            params["conversation_id"] = conversation_id

        logger.debug(t("msg-2245219f", payload=payload, params=params))

        try:
            async with session.post(
                url,
                json=payload,
                params=params,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status == 401:
                    raise Exception(t("msg-76f97104"))

                if response.status != 200:
                    raise Exception(t("msg-d8fd415c", res=response.status))

                # SSE
                buffer = ""
                event_type = None
                event_data = None

                async for chunk in response.content:
                    if chunk:
                        buffer += chunk.decode("utf-8", errors="ignore")
                        lines = buffer.split("\n")
                        buffer = lines[-1]

                        for line in lines[:-1]:
                            line = line.strip()

                            if not line:
                                if event_type and event_data:
                                    yield {"event": event_type, "data": event_data}
                                    event_type = None
                                    event_data = None
                            elif line.startswith("event:"):
                                event_type = line[6:].strip()
                            elif line.startswith("data:"):
                                data_str = line[5:].strip()
                                if data_str and data_str != "[DONE]":
                                    try:
                                        event_data = json.loads(data_str)
                                    except json.JSONDecodeError:
                                        event_data = {"content": data_str}

        except asyncio.TimeoutError:
            raise Exception(t("msg-f5cc7604", timeout=timeout))
        except Exception as e:
            raise Exception(t("msg-30c0a9d6", e=e))

    async def clear_context(self, conversation_id: str):
        """清空会话上下文

        Args:
            conversation_id: 会话ID
        Returns:
            dict: API响应结果

        """
        session = await self._ensure_session()
        url = f"{self.api_base}/v3/conversation/message/clear_context"
        payload = {"conversation_id": conversation_id}

        try:
            async with session.post(url, json=payload) as response:
                response_text = await response.text()

                if response.status == 401:
                    raise Exception(t("msg-76f97104"))

                if response.status != 200:
                    raise Exception(t("msg-11509aba", res=response.status))

                try:
                    return json.loads(response_text)
                except json.JSONDecodeError:
                    raise Exception(t("msg-002af11d"))

        except asyncio.TimeoutError:
            raise Exception(t("msg-c0b8fc7c"))
        except aiohttp.ClientError as e:
            raise Exception(t("msg-a68a33fa", e=e))

    async def get_message_list(
        self,
        conversation_id: str,
        order: str = "desc",
        limit: int = 10,
        offset: int = 0,
    ):
        """获取消息列表

        Args:
            conversation_id: 会话ID
            order: 排序方式 (asc/desc)
            limit: 限制数量
            offset: 偏移量
        Returns:
            dict: API响应结果

        """
        session = await self._ensure_session()
        url = f"{self.api_base}/v3/conversation/message/list"
        params = {
            "conversation_id": conversation_id,
            "order": order,
            "limit": limit,
            "offset": offset,
        }

        try:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.json()

        except Exception as e:
            logger.error(t("msg-c26e068e", e=e))
            raise Exception(t("msg-c26e068e", e=e))

    async def close(self) -> None:
        """关闭会话"""
        if self.session:
            await self.session.close()
            self.session = None


if __name__ == "__main__":
    import asyncio
    import os

    async def test_coze_api_client() -> None:
        api_key = os.getenv("COZE_API_KEY", "")
        bot_id = os.getenv("COZE_BOT_ID", "")
        client = CozeAPIClient(api_key=api_key)

        try:
            with open("README.md", "rb") as f:
                file_data = f.read()
            file_id = await client.upload_file(file_data)
            print(t("msg-5bc0a49d", file_id=file_id))
            async for event in client.chat_messages(
                bot_id=bot_id,
                user_id="test_user",
                additional_messages=[
                    {
                        "role": "user",
                        "content": json.dumps(
                            [
                                {"type": "text", "text": "这是什么"},
                                {"type": "file", "file_id": file_id},
                            ],
                            ensure_ascii=False,
                        ),
                        "content_type": "object_string",
                    },
                ],
                stream=True,
            ):
                print(t("msg-7c08bdaf", event=event))

        finally:
            await client.close()

    asyncio.run(test_coze_api_client())
