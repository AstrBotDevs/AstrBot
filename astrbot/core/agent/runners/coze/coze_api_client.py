import asyncio
import io
import json
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

from astrbot.core import logger


class CozeAPIClient:
    def __init__(self, api_key: str, api_base: str = "https://api.coze.cn"):
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
                    raise Exception("Coze API 认证失败，请检查 API Key 是否正确")

                response_text = await response.text()
                logger.debug(
                    f"文件上传响应状态: {response.status}, 内容: {response_text}",
                )

                if response.status != 200:
                    raise Exception(
                        f"文件上传失败，状态码: {response.status}, 响应: {response_text}",
                    )

                try:
                    result = await response.json()
                except json.JSONDecodeError:
                    raise Exception(f"文件上传响应解析失败: {response_text}")

                if result.get("code") != 0:
                    raise Exception(f"文件上传失败: {result.get('msg', '未知错误')}")

                file_id = result["data"]["id"]
                logger.debug(f"[Coze] 图片上传成功，file_id: {file_id}")
                return file_id

        except asyncio.TimeoutError:
            logger.error("文件上传超时")
            raise Exception("文件上传超时")
        except Exception as e:
            logger.error(f"文件上传失败: {e!s}")
            raise Exception(f"文件上传失败: {e!s}")

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
                    raise Exception(f"下载图片失败，状态码: {response.status}")

                image_data = await response.read()
                return image_data

        except Exception as e:
            logger.error(f"下载图片失败 {image_url}: {e!s}")
            raise Exception(f"下载图片失败: {e!s}")

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

        logger.debug(f"Coze chat_messages payload: {payload}, params: {params}")

        try:
            async with session.post(
                url,
                json=payload,
                params=params,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status == 401:
                    raise Exception("Coze API 认证失败，请检查 API Key 是否正确")

                if response.status != 200:
                    raise Exception(f"Coze API 流式请求失败，状态码: {response.status}")

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
            raise Exception(f"Coze API 流式请求超时 ({timeout}秒)")
        except Exception as e:
            raise Exception(f"Coze API 流式请求失败: {e!s}")

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
                    raise Exception("Coze API 认证失败，请检查 API Key 是否正确")

                if response.status != 200:
                    raise Exception(f"Coze API 请求失败，状态码: {response.status}")

                try:
                    return json.loads(response_text)
                except json.JSONDecodeError:
                    raise Exception("Coze API 返回非JSON格式")

        except asyncio.TimeoutError:
            raise Exception("Coze API 请求超时")
        except aiohttp.ClientError as e:
            raise Exception(f"Coze API 请求失败: {e!s}")

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
            logger.error(f"获取Coze消息列表失败: {e!s}")
            raise Exception(f"获取Coze消息列表失败: {e!s}")

    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.close()
            self.session = None


if __name__ == "__main__":
    import asyncio
    import os

    async def test_coze_api_client():
        api_key = os.getenv("COZE_API_KEY", "")
        bot_id = os.getenv("COZE_BOT_ID", "")
        client = CozeAPIClient(api_key=api_key)

        try:
            with open("README.md", "rb") as f:
                file_data = f.read()
            file_id = await client.upload_file(file_data)
            print(f"Uploaded file_id: {file_id}")
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
                print(f"Event: {event}")

        finally:
            await client.close()

    asyncio.run(test_coze_api_client())
