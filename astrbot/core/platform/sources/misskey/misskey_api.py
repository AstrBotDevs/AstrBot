import json
from typing import Any, Optional, Dict, List, Callable, Awaitable
import uuid

try:
    import aiohttp
    import websockets
except ImportError as e:
    raise ImportError(
        "aiohttp and websockets are required for Misskey API. Please install them with: pip install aiohttp websockets"
    ) from e

from astrbot.api import logger

# Constants
API_MAX_RETRIES = 3
HTTP_OK = 200


class APIError(Exception):
    """Misskey API 基础异常"""

    pass


class APIConnectionError(APIError):
    """网络连接异常"""

    pass


class APIRateLimitError(APIError):
    """API 频率限制异常"""

    pass


class AuthenticationError(APIError):
    """认证失败异常"""

    pass


class WebSocketError(APIError):
    """WebSocket 连接异常"""

    pass


class StreamingClient:
    def __init__(self, instance_url: str, access_token: str):
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.websocket: Optional[Any] = None
        self.is_connected = False
        self.message_handlers: Dict[str, Callable] = {}
        self.channels: Dict[str, str] = {}
        self._running = False
        self._last_pong = None

    async def connect(self) -> bool:
        try:
            ws_url = self.instance_url.replace("https://", "wss://").replace(
                "http://", "ws://"
            )
            ws_url += f"/streaming?i={self.access_token}"

            self.websocket = await websockets.connect(
                ws_url, ping_interval=30, ping_timeout=10
            )
            self.is_connected = True
            self._running = True

            logger.info("[Misskey WebSocket] 已连接")
            return True

        except Exception as e:
            logger.error(f"[Misskey WebSocket] 连接失败: {e}")
            self.is_connected = False
            return False

    async def disconnect(self):
        self._running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        self.is_connected = False
        logger.info("[Misskey WebSocket] 连接已断开")

    async def subscribe_channel(
        self, channel_type: str, params: Optional[Dict] = None
    ) -> str:
        if not self.is_connected or not self.websocket:
            raise WebSocketError("WebSocket 未连接")

        channel_id = str(uuid.uuid4())
        message = {
            "type": "connect",
            "body": {"channel": channel_type, "id": channel_id, "params": params or {}},
        }

        await self.websocket.send(json.dumps(message))
        self.channels[channel_id] = channel_type
        return channel_id

    async def unsubscribe_channel(self, channel_id: str):
        if (
            not self.is_connected
            or not self.websocket
            or channel_id not in self.channels
        ):
            return

        message = {"type": "disconnect", "body": {"id": channel_id}}

        await self.websocket.send(json.dumps(message))
        del self.channels[channel_id]

    def add_message_handler(
        self, event_type: str, handler: Callable[[Dict], Awaitable[None]]
    ):
        self.message_handlers[event_type] = handler

    async def listen(self):
        if not self.is_connected or not self.websocket:
            raise WebSocketError("WebSocket 未连接")

        try:
            async for message in self.websocket:
                if not self._running:
                    break

                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.warning(f"[Misskey WebSocket] 无法解析消息: {e}")
                except Exception as e:
                    logger.error(f"[Misskey WebSocket] 处理消息失败: {e}")

        except websockets.exceptions.ConnectionClosedError as e:
            logger.warning(f"[Misskey WebSocket] 连接意外关闭: {e}")
            self.is_connected = False
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(
                f"[Misskey WebSocket] 连接已关闭 (代码: {e.code}, 原因: {e.reason})"
            )
            self.is_connected = False
        except websockets.exceptions.InvalidHandshake as e:
            logger.error(f"[Misskey WebSocket] 握手失败: {e}")
            self.is_connected = False
        except Exception as e:
            logger.error(f"[Misskey WebSocket] 监听消息失败: {e}")
            self.is_connected = False

    async def _handle_message(self, data: Dict[str, Any]):
        message_type = data.get("type")
        body = data.get("body", {})

        logger.debug(
            f"[Misskey WebSocket] 收到消息类型: {message_type}\n数据: {json.dumps(data, indent=2, ensure_ascii=False)}"
        )

        if message_type == "channel":
            channel_id = body.get("id")
            event_type = body.get("type")
            event_body = body.get("body", {})

            logger.debug(
                f"[Misskey WebSocket] 频道消息: {channel_id}, 事件类型: {event_type}"
            )

            if channel_id in self.channels:
                channel_type = self.channels[channel_id]
                handler_key = f"{channel_type}:{event_type}"

                if handler_key in self.message_handlers:
                    logger.debug(f"[Misskey WebSocket] 使用处理器: {handler_key}")
                    await self.message_handlers[handler_key](event_body)
                elif event_type in self.message_handlers:
                    logger.debug(f"[Misskey WebSocket] 使用事件处理器: {event_type}")
                    await self.message_handlers[event_type](event_body)
                else:
                    logger.debug(
                        f"[Misskey WebSocket] 未找到处理器: {handler_key} 或 {event_type}"
                    )
                    if "_debug" in self.message_handlers:
                        await self.message_handlers["_debug"](
                            {
                                "type": event_type,
                                "body": event_body,
                                "channel": channel_type,
                            }
                        )

        elif message_type in self.message_handlers:
            logger.debug(f"[Misskey WebSocket] 直接消息处理器: {message_type}")
            await self.message_handlers[message_type](body)
        else:
            logger.debug(f"[Misskey WebSocket] 未处理的消息类型: {message_type}")
            if "_debug" in self.message_handlers:
                await self.message_handlers["_debug"](data)


def retry_async(max_retries: int = 3, retryable_exceptions: tuple = ()):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            last_exc = None
            for _ in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exc = e
                    continue
            if last_exc:
                raise last_exc

        return wrapper

    return decorator


class MisskeyAPI:
    def __init__(self, instance_url: str, access_token: str):
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self._session: Optional[aiohttp.ClientSession] = None
        self.streaming: Optional[StreamingClient] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def close(self) -> None:
        if self.streaming:
            await self.streaming.disconnect()
            self.streaming = None
        if self._session:
            await self._session.close()
            self._session = None
        logger.debug("[Misskey API] 客户端已关闭")

    def get_streaming_client(self) -> StreamingClient:
        if not self.streaming:
            self.streaming = StreamingClient(self.instance_url, self.access_token)
        return self.streaming

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    def _handle_response_status(self, status: int, endpoint: str):
        """处理 HTTP 响应状态码"""
        if status == 400:
            logger.error(f"API 请求错误: {endpoint} (状态码: {status})")
            raise APIError(f"Bad request for {endpoint}")
        elif status in (401, 403):
            logger.error(f"API 认证失败: {endpoint} (状态码: {status})")
            raise AuthenticationError(f"Authentication failed for {endpoint}")
        elif status == 429:
            logger.warning(f"API 频率限制: {endpoint} (状态码: {status})")
            raise APIRateLimitError(f"Rate limit exceeded for {endpoint}")
        else:
            logger.error(f"API 请求失败: {endpoint} (状态码: {status})")
            raise APIConnectionError(f"HTTP {status} for {endpoint}")

    async def _process_response(
        self, response: aiohttp.ClientResponse, endpoint: str
    ) -> Any:
        """处理 API 响应"""
        if response.status == HTTP_OK:
            try:
                result = await response.json()
                if endpoint == "i/notifications":
                    notifications_data = (
                        result
                        if isinstance(result, list)
                        else result.get("notifications", [])
                        if isinstance(result, dict)
                        else []
                    )
                    if notifications_data:
                        logger.debug(f"获取到 {len(notifications_data)} 条新通知")
                else:
                    logger.debug(f"API 请求成功: {endpoint}")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"响应不是有效的 JSON 格式: {e}")
                raise APIConnectionError("Invalid JSON response") from e
        else:
            try:
                error_text = await response.text()
                logger.error(
                    f"API 请求失败: {endpoint} - 状态码: {response.status}, 响应: {error_text}"
                )
            except Exception:
                logger.error(f"API 请求失败: {endpoint} - 状态码: {response.status}")

            self._handle_response_status(response.status, endpoint)
            raise APIConnectionError(f"Request failed for {endpoint}")

    @retry_async(
        max_retries=API_MAX_RETRIES,
        retryable_exceptions=(APIConnectionError, APIRateLimitError),
    )
    async def _make_request(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Any:
        url = f"{self.instance_url}/api/{endpoint}"
        payload = {"i": self.access_token}
        if data:
            payload.update(data)

        try:
            async with self.session.post(url, json=payload) as response:
                return await self._process_response(response, endpoint)
        except aiohttp.ClientError as e:
            logger.error(f"HTTP 请求错误: {e}")
            raise APIConnectionError(f"HTTP request failed: {e}") from e

    async def create_note(
        self,
        text: str,
        visibility: str = "public",
        reply_id: Optional[str] = None,
        visible_user_ids: Optional[List[str]] = None,
        local_only: bool = False,
    ) -> Dict[str, Any]:
        """创建新贴文"""
        data: Dict[str, Any] = {
            "text": text,
            "visibility": visibility,
            "localOnly": local_only,
        }
        if reply_id:
            data["replyId"] = reply_id
        if visible_user_ids and visibility == "specified":
            data["visibleUserIds"] = visible_user_ids

        result = await self._make_request("notes/create", data)
        note_id = result.get("createdNote", {}).get("id", "unknown")
        logger.debug(f"发帖成功，note_id: {note_id}")
        return result

    async def get_current_user(self) -> Dict[str, Any]:
        """获取当前用户信息"""
        return await self._make_request("i", {})

    async def send_message(self, user_id: str, text: str) -> Dict[str, Any]:
        """发送聊天消息"""
        result = await self._make_request(
            "chat/messages/create-to-user", {"toUserId": user_id, "text": text}
        )
        message_id = result.get("id", "unknown")
        logger.debug(f"聊天发送成功，message_id: {message_id}")
        return result

    async def send_room_message(self, room_id: str, text: str) -> Dict[str, Any]:
        """发送房间消息"""
        result = await self._make_request(
            "chat/messages/create-to-room", {"toRoomId": room_id, "text": text}
        )
        message_id = result.get("id", "unknown")
        logger.debug(f"房间消息发送成功，message_id: {message_id}")
        return result

    async def get_messages(
        self, user_id: str, limit: int = 10, since_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取聊天消息历史"""
        data: Dict[str, Any] = {"userId": user_id, "limit": limit}
        if since_id:
            data["sinceId"] = since_id

        result = await self._make_request("chat/messages/user-timeline", data)
        if isinstance(result, list):
            return result
        else:
            logger.warning(f"获取聊天消息响应格式异常: {type(result)}")
            return []

    async def get_mentions(
        self, limit: int = 10, since_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取提及通知"""
        data: Dict[str, Any] = {"limit": limit}
        if since_id:
            data["sinceId"] = since_id
        data["includeTypes"] = ["mention", "reply", "quote"]

        result = await self._make_request("i/notifications", data)
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and "notifications" in result:
            return result["notifications"]
        else:
            logger.warning(f"获取提及通知响应格式异常: {type(result)}")
            return []
