import json
import random
import asyncio
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
from .misskey_utils import FileIDExtractor

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
        self.desired_channels: Dict[str, Optional[Dict]] = {}
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
            if self.desired_channels:
                try:
                    desired = list(self.desired_channels.items())
                    for channel_type, params in desired:
                        try:
                            await self.subscribe_channel(channel_type, params)
                        except Exception as e:
                            logger.warning(
                                f"[Misskey WebSocket] 重新订阅 {channel_type} 失败: {e}"
                            )
                except Exception:
                    pass
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
        channel_type = self.channels.get(channel_id)
        if channel_id in self.channels:
            del self.channels[channel_id]
        if channel_type and channel_type not in self.channels.values():
            self.desired_channels.pop(channel_type, None)

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
            try:
                await self.disconnect()
            except Exception:
                pass
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(
                f"[Misskey WebSocket] 连接已关闭 (代码: {e.code}, 原因: {e.reason})"
            )
            self.is_connected = False
            try:
                await self.disconnect()
            except Exception:
                pass
        except websockets.exceptions.InvalidHandshake as e:
            logger.error(f"[Misskey WebSocket] 握手失败: {e}")
            self.is_connected = False
            try:
                await self.disconnect()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"[Misskey WebSocket] 监听消息失败: {e}")
            self.is_connected = False
            try:
                await self.disconnect()
            except Exception:
                pass

    async def _handle_message(self, data: Dict[str, Any]):
        message_type = data.get("type")
        body = data.get("body", {})

        def _build_channel_summary(message_type: Optional[str], body: Any) -> str:
            try:
                if not isinstance(body, dict):
                    return f"[Misskey WebSocket] 收到消息类型: {message_type}"

                inner = body.get("body") if isinstance(body.get("body"), dict) else body
                note = (
                    inner.get("note")
                    if isinstance(inner, dict) and isinstance(inner.get("note"), dict)
                    else None
                )

                text = note.get("text") if note else None
                note_id = note.get("id") if note else None
                files = note.get("files") or [] if note else []
                has_files = bool(files)
                is_hidden = bool(note.get("isHidden")) if note else False
                user = note.get("user", {}) if note else None

                return (
                    f"[Misskey WebSocket] 收到消息类型: {message_type} | "
                    f"note_id={note_id} | user={user.get('username') if user else None} | "
                    f"text={text[:80] if text else '[no-text]'} | files={has_files} | hidden={is_hidden}"
                )
            except Exception:
                return f"[Misskey WebSocket] 收到消息类型: {message_type}"

        channel_summary = _build_channel_summary(message_type, body)
        logger.info(channel_summary)

        logger.debug(
            f"[Misskey WebSocket] 收到完整消息: {json.dumps(data, indent=2, ensure_ascii=False)}"
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


def retry_async(
    max_retries: int = 3,
    retryable_exceptions: tuple = (APIConnectionError, APIRateLimitError),
    backoff_base: float = 1.0,
    max_backoff: float = 30.0,
):
    """
    智能异步重试装饰器

    Args:
        max_retries: 最大重试次数
        retryable_exceptions: 可重试的异常类型
        backoff_base: 退避基数
        max_backoff: 最大退避时间
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            last_exc = None
            func_name = getattr(func, "__name__", "unknown")

            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exc = e
                    if attempt == max_retries:
                        logger.error(
                            f"[Misskey API] {func_name} 重试 {max_retries} 次后仍失败: {e}"
                        )
                        break

                    # 智能退避策略
                    if isinstance(e, APIRateLimitError):
                        # 频率限制用更长的退避时间
                        backoff = min(backoff_base * (3**attempt), max_backoff)
                    else:
                        # 其他错误用指数退避
                        backoff = min(backoff_base * (2**attempt), max_backoff)

                    jitter = random.uniform(0.1, 0.5)  # 随机抖动
                    sleep_time = backoff + jitter

                    logger.warning(
                        f"[Misskey API] {func_name} 第 {attempt} 次重试失败: {e}，"
                        f"{sleep_time:.1f}s后重试"
                    )
                    await asyncio.sleep(sleep_time)
                    continue
                except Exception as e:
                    # 非可重试异常直接抛出
                    logger.error(f"[Misskey API] {func_name} 遇到不可重试异常: {e}")
                    raise

            if last_exc:
                raise last_exc

        return wrapper

    return decorator


class MisskeyAPI:
    def __init__(
        self,
        instance_url: str,
        access_token: str,
        *,
        allow_insecure_downloads: bool = False,
        download_timeout: int = 15,
        chunk_size: int = 64 * 1024,
        max_download_bytes: Optional[int] = None,
    ):
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self._session: Optional[aiohttp.ClientSession] = None
        self.streaming: Optional[StreamingClient] = None
        # download options
        self.allow_insecure_downloads = allow_insecure_downloads
        self.download_timeout = download_timeout
        self.chunk_size = chunk_size
        self.max_download_bytes = (
            int(max_download_bytes) if max_download_bytes is not None else None
        )

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
            logger.error(f"[Misskey API] 请求参数错误: {endpoint} (HTTP {status})")
            raise APIError(f"Bad request for {endpoint}")
        elif status == 401:
            logger.error(f"[Misskey API] 未授权访问: {endpoint} (HTTP {status})")
            raise AuthenticationError(f"Unauthorized access for {endpoint}")
        elif status == 403:
            logger.error(f"[Misskey API] 访问被禁止: {endpoint} (HTTP {status})")
            raise AuthenticationError(f"Forbidden access for {endpoint}")
        elif status == 404:
            logger.error(f"[Misskey API] 资源不存在: {endpoint} (HTTP {status})")
            raise APIError(f"Resource not found for {endpoint}")
        elif status == 413:
            logger.error(f"[Misskey API] 请求体过大: {endpoint} (HTTP {status})")
            raise APIError(f"Request entity too large for {endpoint}")
        elif status == 429:
            logger.warning(f"[Misskey API] 请求频率限制: {endpoint} (HTTP {status})")
            raise APIRateLimitError(f"Rate limit exceeded for {endpoint}")
        elif status == 500:
            logger.error(f"[Misskey API] 服务器内部错误: {endpoint} (HTTP {status})")
            raise APIConnectionError(f"Internal server error for {endpoint}")
        elif status == 502:
            logger.error(f"[Misskey API] 网关错误: {endpoint} (HTTP {status})")
            raise APIConnectionError(f"Bad gateway for {endpoint}")
        elif status == 503:
            logger.error(f"[Misskey API] 服务不可用: {endpoint} (HTTP {status})")
            raise APIConnectionError(f"Service unavailable for {endpoint}")
        elif status == 504:
            logger.error(f"[Misskey API] 网关超时: {endpoint} (HTTP {status})")
            raise APIConnectionError(f"Gateway timeout for {endpoint}")
        else:
            logger.error(f"[Misskey API] 未知错误: {endpoint} (HTTP {status})")
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
                        logger.debug(
                            f"[Misskey API] 获取到 {len(notifications_data)} 条新通知"
                        )
                else:
                    logger.debug(f"[Misskey API] 请求成功: {endpoint}")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"[Misskey API] 响应格式错误: {e}")
                raise APIConnectionError("Invalid JSON response") from e
        else:
            try:
                error_text = await response.text()
                logger.error(
                    f"[Misskey API] 请求失败: {endpoint} - HTTP {response.status}, 响应: {error_text}"
                )
            except Exception:
                logger.error(
                    f"[Misskey API] 请求失败: {endpoint} - HTTP {response.status}"
                )

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
            logger.error(f"[Misskey API] HTTP 请求错误: {e}")
            raise APIConnectionError(f"HTTP request failed: {e}") from e

    async def create_note(
        self,
        text: Optional[str] = None,
        visibility: str = "public",
        reply_id: Optional[str] = None,
        visible_user_ids: Optional[List[str]] = None,
        file_ids: Optional[List[str]] = None,
        local_only: bool = False,
        cw: Optional[str] = None,
        poll: Optional[Dict[str, Any]] = None,
        renote_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        reaction_acceptance: Optional[str] = None,
        no_extract_mentions: Optional[bool] = None,
        no_extract_hashtags: Optional[bool] = None,
        no_extract_emojis: Optional[bool] = None,
        media_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a note (wrapper for notes/create). All additional fields are optional and passed through to the API."""
        data: Dict[str, Any] = {}

        if text is not None:
            data["text"] = text

        data["visibility"] = visibility
        data["localOnly"] = local_only

        if reply_id:
            data["replyId"] = reply_id

        if visible_user_ids and visibility == "specified":
            data["visibleUserIds"] = visible_user_ids

        if file_ids:
            data["fileIds"] = file_ids
        if media_ids:
            data["mediaIds"] = media_ids

        if cw is not None:
            data["cw"] = cw
        if poll is not None:
            data["poll"] = poll
        if renote_id is not None:
            data["renoteId"] = renote_id
        if channel_id is not None:
            data["channelId"] = channel_id
        if reaction_acceptance is not None:
            data["reactionAcceptance"] = reaction_acceptance
        if no_extract_mentions is not None:
            data["noExtractMentions"] = bool(no_extract_mentions)
        if no_extract_hashtags is not None:
            data["noExtractHashtags"] = bool(no_extract_hashtags)
        if no_extract_emojis is not None:
            data["noExtractEmojis"] = bool(no_extract_emojis)

        result = await self._make_request("notes/create", data)
        note_id = (
            result.get("createdNote", {}).get("id", "unknown")
            if isinstance(result, dict)
            else "unknown"
        )
        logger.debug(f"[Misskey API] 发帖成功: {note_id}")
        return result

    async def upload_file(
        self,
        file_path: str,
        name: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload a file to Misskey drive/files/create and return a dict containing id and raw result."""
        if not file_path:
            raise APIError("No file path provided for upload")

        url = f"{self.instance_url}/api/drive/files/create"
        form = aiohttp.FormData()
        form.add_field("i", self.access_token)

        try:
            filename = name or file_path.split("/")[-1]
            if folder_id:
                form.add_field("folderId", str(folder_id))

            try:
                f = open(file_path, "rb")
            except FileNotFoundError as e:
                logger.error(f"[Misskey API] 本地文件不存在: {file_path}")
                raise APIError(f"File not found: {file_path}") from e

            try:
                form.add_field("file", f, filename=filename)
                async with self.session.post(url, data=form) as resp:
                    result = await self._process_response(resp, "drive/files/create")
                    file_id = FileIDExtractor.extract_file_id(result)
                    logger.debug(
                        f"[Misskey API] 本地文件上传成功: {filename} -> {file_id}"
                    )
                    return {"id": file_id, "raw": result}
            finally:
                f.close()
        except aiohttp.ClientError as e:
            logger.error(f"[Misskey API] 文件上传网络错误: {e}")
            raise APIConnectionError(f"Upload failed: {e}") from e

    async def find_files_by_hash(self, md5_hash: str) -> List[Dict[str, Any]]:
        """Find files by MD5 hash"""
        if not md5_hash:
            raise APIError("No MD5 hash provided for find-by-hash")

        data = {"md5": md5_hash}

        try:
            logger.debug(f"[Misskey API] find-by-hash 请求: md5={md5_hash}")
            result = await self._make_request("drive/files/find-by-hash", data)
            logger.debug(
                f"[Misskey API] find-by-hash 响应: 找到 {len(result) if isinstance(result, list) else 0} 个文件"
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"[Misskey API] 根据哈希查找文件失败: {e}")
            raise

    async def find_files_by_name(
        self, name: str, folder_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Find files by name"""
        if not name:
            raise APIError("No name provided for find")

        data: Dict[str, Any] = {"name": name}
        if folder_id:
            data["folderId"] = folder_id

        try:
            logger.debug(f"[Misskey API] find 请求: name={name}, folder_id={folder_id}")
            result = await self._make_request("drive/files/find", data)
            logger.debug(
                f"[Misskey API] find 响应: 找到 {len(result) if isinstance(result, list) else 0} 个文件"
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"[Misskey API] 根据名称查找文件失败: {e}")
            raise

    async def find_files(
        self,
        limit: int = 10,
        folder_id: Optional[str] = None,
        type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List files with optional filters"""
        data: Dict[str, Any] = {"limit": limit}
        if folder_id is not None:
            data["folderId"] = folder_id
        if type is not None:
            data["type"] = type

        try:
            logger.debug(
                f"[Misskey API] 列表文件请求: limit={limit}, folder_id={folder_id}, type={type}"
            )
            result = await self._make_request("drive/files", data)
            logger.debug(
                f"[Misskey API] 列表文件响应: 找到 {len(result) if isinstance(result, list) else 0} 个文件"
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"[Misskey API] 列表文件失败: {e}")
            raise

    async def _download_with_existing_session(
        self, url: str, ssl_verify: bool = True
    ) -> Optional[bytes]:
        """使用现有会话下载文件"""
        if not (hasattr(self, "session") and self.session):
            raise APIConnectionError("No existing session available")

        async with self.session.get(
            url, timeout=aiohttp.ClientTimeout(total=15), ssl=ssl_verify
        ) as response:
            if response.status == 200:
                return await response.read()
        return None

    async def _download_with_temp_session(
        self, url: str, ssl_verify: bool = True
    ) -> Optional[bytes]:
        """使用临时会话下载文件"""
        connector = aiohttp.TCPConnector(ssl=ssl_verify)
        async with aiohttp.ClientSession(connector=connector) as temp_session:
            async with temp_session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    return await response.read()
        return None

    async def upload_and_find_file(
        self,
        url: str,
        name: Optional[str] = None,
        folder_id: Optional[str] = None,
        max_wait_time: float = 30.0,
        check_interval: float = 2.0,
    ) -> Optional[Dict[str, Any]]:
        """
        简化的文件上传：尝试 URL 上传，失败则下载后本地上传

        Args:
            url: 文件URL
            name: 文件名（可选）
            folder_id: 文件夹ID（可选）
            max_wait_time: 保留参数（未使用）
            check_interval: 保留参数（未使用）

        Returns:
            包含文件ID和元信息的字典，失败时返回None
        """
        if not url:
            raise APIError("URL不能为空")

        # 通过本地上传获取即时文件 ID（下载文件 → 上传 → 返回 ID）
        try:
            import tempfile
            import os

            # SSL 验证下载，失败则重试不验证 SSL
            tmp_bytes = None
            try:
                tmp_bytes = await self._download_with_existing_session(
                    url, ssl_verify=True
                ) or await self._download_with_temp_session(url, ssl_verify=True)
            except Exception as ssl_error:
                logger.debug(
                    f"[Misskey API] SSL 验证下载失败: {ssl_error}，重试不验证 SSL"
                )
                try:
                    tmp_bytes = await self._download_with_existing_session(
                        url, ssl_verify=False
                    ) or await self._download_with_temp_session(url, ssl_verify=False)
                except Exception:
                    pass

            if tmp_bytes:
                with tempfile.NamedTemporaryFile(delete=False) as tmpf:
                    tmpf.write(tmp_bytes)
                    tmp_path = tmpf.name

                try:
                    result = await self.upload_file(tmp_path, name, folder_id)
                    logger.debug(f"[Misskey API] 本地上传成功: {result.get('id')}")
                    return result
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"[Misskey API] 本地上传失败: {e}")

        return None

    async def get_current_user(self) -> Dict[str, Any]:
        """获取当前用户信息"""
        return await self._make_request("i", {})

    async def send_message(
        self, user_id_or_payload: Any, text: Optional[str] = None
    ) -> Dict[str, Any]:
        """发送聊天消息。

        Accepts either (user_id: str, text: str) or a single dict payload prepared by caller.
        """
        if isinstance(user_id_or_payload, dict):
            data = user_id_or_payload
        else:
            data = {"toUserId": user_id_or_payload, "text": text}

        result = await self._make_request("chat/messages/create-to-user", data)
        message_id = result.get("id", "unknown")
        logger.debug(f"[Misskey API] 聊天消息发送成功: {message_id}")
        return result

    async def send_room_message(
        self, room_id_or_payload: Any, text: Optional[str] = None
    ) -> Dict[str, Any]:
        """发送房间消息。

        Accepts either (room_id: str, text: str) or a single dict payload.
        """
        if isinstance(room_id_or_payload, dict):
            data = room_id_or_payload
        else:
            data = {"toRoomId": room_id_or_payload, "text": text}

        result = await self._make_request("chat/messages/create-to-room", data)
        message_id = result.get("id", "unknown")
        logger.debug(f"[Misskey API] 房间消息发送成功: {message_id}")
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
        logger.warning(f"[Misskey API] 聊天消息响应格式异常: {type(result)}")
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
            logger.warning(f"[Misskey API] 提及通知响应格式异常: {type(result)}")
            return []

    async def send_message_with_media(
        self,
        message_type: str,
        target_id: str,
        text: Optional[str] = None,
        media_urls: Optional[List[str]] = None,
        local_files: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        通用消息发送函数：统一处理文本+媒体发送

        Args:
            message_type: 消息类型 ('chat', 'room', 'note')
            target_id: 目标ID (用户ID/房间ID/频道ID等)
            text: 文本内容
            media_urls: 媒体文件URL列表
            local_files: 本地文件路径列表
            **kwargs: 其他参数（如visibility等）

        Returns:
            发送结果字典

        Raises:
            APIError: 参数错误或发送失败
        """
        if not text and not media_urls and not local_files:
            raise APIError("消息内容不能为空：需要文本或媒体文件")

        file_ids = []

        # 处理远程媒体文件
        if media_urls:
            file_ids.extend(await self._process_media_urls(media_urls))

        # 处理本地文件
        if local_files:
            file_ids.extend(await self._process_local_files(local_files))

        # 根据消息类型发送
        return await self._dispatch_message(
            message_type, target_id, text, file_ids, **kwargs
        )

    async def _process_media_urls(self, urls: List[str]) -> List[str]:
        """处理远程媒体文件URL列表，返回文件ID列表"""
        file_ids = []
        for url in urls:
            try:
                result = await self.upload_and_find_file(url)
                if result and result.get("id"):
                    file_ids.append(result["id"])
                    logger.debug(f"[Misskey API] URL媒体上传成功: {result['id']}")
                else:
                    logger.error(f"[Misskey API] URL媒体上传失败: {url}")
            except Exception as e:
                logger.error(f"[Misskey API] URL媒体处理失败 {url}: {e}")
                # 继续处理其他文件，不中断整个流程
                continue
        return file_ids

    async def _process_local_files(self, file_paths: List[str]) -> List[str]:
        """处理本地文件路径列表，返回文件ID列表"""
        file_ids = []
        for file_path in file_paths:
            try:
                result = await self.upload_file(file_path)
                if result and result.get("id"):
                    file_ids.append(result["id"])
                    logger.debug(f"[Misskey API] 本地文件上传成功: {result['id']}")
                else:
                    logger.error(f"[Misskey API] 本地文件上传失败: {file_path}")
            except Exception as e:
                logger.error(f"[Misskey API] 本地文件处理失败 {file_path}: {e}")
                continue
        return file_ids

    async def _dispatch_message(
        self,
        message_type: str,
        target_id: str,
        text: Optional[str],
        file_ids: List[str],
        **kwargs,
    ) -> Dict[str, Any]:
        """根据消息类型分发到对应的发送方法"""
        if message_type == "chat":
            # 聊天消息使用 fileId (单数)
            payload = {"toUserId": target_id}
            if text:
                payload["text"] = text
            if file_ids:
                if len(file_ids) == 1:
                    payload["fileId"] = file_ids[0]
                else:
                    # 多文件时逐个发送
                    results = []
                    for file_id in file_ids:
                        single_payload = payload.copy()
                        single_payload["fileId"] = file_id
                        result = await self.send_message(single_payload)
                        results.append(result)
                    return {"multiple": True, "results": results}
            return await self.send_message(payload)

        elif message_type == "room":
            # 房间消息使用 fileId (单数)
            payload = {"toRoomId": target_id}
            if text:
                payload["text"] = text
            if file_ids:
                if len(file_ids) == 1:
                    payload["fileId"] = file_ids[0]
                else:
                    # 多文件时逐个发送
                    results = []
                    for file_id in file_ids:
                        single_payload = payload.copy()
                        single_payload["fileId"] = file_id
                        result = await self.send_room_message(single_payload)
                        results.append(result)
                    return {"multiple": True, "results": results}
            return await self.send_room_message(payload)

        elif message_type == "note":
            # 发帖使用 fileIds (复数)
            note_kwargs = {
                "text": text,
                "file_ids": file_ids or None,
            }
            # 合并其他参数
            note_kwargs.update(kwargs)
            return await self.create_note(**note_kwargs)

        else:
            raise APIError(f"不支持的消息类型: {message_type}")
