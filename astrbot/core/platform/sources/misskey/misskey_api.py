from astrbot.core.lang import t
import asyncio
import json
import random
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, NoReturn

try:
    import aiohttp
    import websockets
except ImportError as e:
    raise ImportError(
        t("msg-fab20f57"),
    ) from e

from astrbot.api import logger

from .misskey_utils import FileIDExtractor

# Constants
API_MAX_RETRIES = 3
HTTP_OK = 200


class APIError(Exception):
    """Misskey API 基础异常"""


class APIConnectionError(APIError):
    """网络连接异常"""


class APIRateLimitError(APIError):
    """API 频率限制异常"""


class AuthenticationError(APIError):
    """认证失败异常"""


class WebSocketError(APIError):
    """WebSocket 连接异常"""


class StreamingClient:
    def __init__(self, instance_url: str, access_token: str) -> None:
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.websocket: Any | None = None
        self.is_connected = False
        self.message_handlers: dict[str, Callable] = {}
        self.channels: dict[str, str] = {}
        self.desired_channels: dict[str, dict | None] = {}
        self._running = False
        self._last_pong = None

    async def connect(self) -> bool:
        try:
            ws_url = self.instance_url.replace("https://", "wss://").replace(
                "http://",
                "ws://",
            )
            ws_url += f"/streaming?i={self.access_token}"

            self.websocket = await websockets.connect(
                ws_url,
                ping_interval=30,
                ping_timeout=10,
            )
            self.is_connected = True
            self._running = True

            logger.info(t("msg-f2eea8e1"))
            if self.desired_channels:
                try:
                    desired = list(self.desired_channels.items())
                    for channel_type, params in desired:
                        try:
                            await self.subscribe_channel(channel_type, params)
                        except Exception as e:
                            logger.warning(
                                t("msg-5efd11a2", channel_type=channel_type, e=e),
                            )
                except Exception:
                    pass
            return True

        except Exception as e:
            logger.error(t("msg-b70e2176", e=e))
            self.is_connected = False
            return False

    async def disconnect(self) -> None:
        self._running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        self.is_connected = False
        logger.info(t("msg-b9f3ee06"))

    async def subscribe_channel(
        self,
        channel_type: str,
        params: dict | None = None,
    ) -> str:
        if not self.is_connected or not self.websocket:
            raise WebSocketError(t("msg-7cd98e54"))

        channel_id = str(uuid.uuid4())
        message = {
            "type": "connect",
            "body": {"channel": channel_type, "id": channel_id, "params": params or {}},
        }

        await self.websocket.send(json.dumps(message))
        self.channels[channel_id] = channel_type
        return channel_id

    async def unsubscribe_channel(self, channel_id: str) -> None:
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
        self,
        event_type: str,
        handler: Callable[[dict], Awaitable[None]],
    ) -> None:
        self.message_handlers[event_type] = handler

    async def listen(self) -> None:
        if not self.is_connected or not self.websocket:
            raise WebSocketError(t("msg-7cd98e54"))

        try:
            async for message in self.websocket:
                if not self._running:
                    break

                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.warning(t("msg-43566304", e=e))
                except Exception as e:
                    logger.error(t("msg-e617e390", e=e))

        except websockets.exceptions.ConnectionClosedError as e:
            logger.warning(t("msg-c60715cf", e=e))
            self.is_connected = False
            try:
                await self.disconnect()
            except Exception:
                pass
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(
                t("msg-da9a2a17", res=e.code, res_2=e.reason),
            )
            self.is_connected = False
            try:
                await self.disconnect()
            except Exception:
                pass
        except websockets.exceptions.InvalidHandshake as e:
            logger.error(t("msg-bbf6a42e", e=e))
            self.is_connected = False
            try:
                await self.disconnect()
            except Exception:
                pass
        except Exception as e:
            logger.error(t("msg-254f0237", e=e))
            self.is_connected = False
            try:
                await self.disconnect()
            except Exception:
                pass

    async def _handle_message(self, data: dict[str, Any]) -> None:
        message_type = data.get("type")
        body = data.get("body", {})

        def _build_channel_summary(message_type: str | None, body: Any) -> str:
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
        logger.info(t("msg-49f7e90e", channel_summary=channel_summary))

        if message_type == "channel":
            channel_id = body.get("id")
            event_type = body.get("type")
            event_body = body.get("body", {})

            logger.debug(
                t("msg-630a4832", channel_id=channel_id, event_type=event_type),
            )

            if channel_id in self.channels:
                channel_type = self.channels[channel_id]
                handler_key = f"{channel_type}:{event_type}"

                if handler_key in self.message_handlers:
                    logger.debug(t("msg-0dc61a4d", handler_key=handler_key))
                    await self.message_handlers[handler_key](event_body)
                elif event_type in self.message_handlers:
                    logger.debug(t("msg-012666fc", event_type=event_type))
                    await self.message_handlers[event_type](event_body)
                else:
                    logger.debug(
                        t("msg-e202168a", handler_key=handler_key, event_type=event_type),
                    )
                    if "_debug" in self.message_handlers:
                        await self.message_handlers["_debug"](
                            {
                                "type": event_type,
                                "body": event_body,
                                "channel": channel_type,
                            },
                        )

        elif message_type in self.message_handlers:
            logger.debug(t("msg-a397eef1", message_type=message_type))
            await self.message_handlers[message_type](body)
        else:
            logger.debug(t("msg-a5f12225", message_type=message_type))
            if "_debug" in self.message_handlers:
                await self.message_handlers["_debug"](data)


def retry_async(
    max_retries: int = 3,
    retryable_exceptions: tuple = (APIConnectionError, APIRateLimitError),
    backoff_base: float = 1.0,
    max_backoff: float = 30.0,
):
    """智能异步重试装饰器

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
                            t("msg-ad61d480", func_name=func_name, max_retries=max_retries, e=e),
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
                        t("msg-7de2ca49", func_name=func_name, attempt=attempt, e=e, sleep_time=sleep_time),
                    )
                    await asyncio.sleep(sleep_time)
                    continue
                except Exception as e:
                    # 非可重试异常直接抛出
                    logger.error(t("msg-f5aecf37", func_name=func_name, e=e))
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
        max_download_bytes: int | None = None,
    ) -> None:
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self._session: aiohttp.ClientSession | None = None
        self.streaming: StreamingClient | None = None
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
        logger.debug(t("msg-e5852be5"))

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

    def _handle_response_status(self, status: int, endpoint: str) -> NoReturn:
        """处理 HTTP 响应状态码"""
        if status == 400:
            logger.error(t("msg-21fc185c", endpoint=endpoint, status=status))
            raise APIError(t("msg-5b106def", endpoint=endpoint))
        if status == 401:
            logger.error(t("msg-28afff67", endpoint=endpoint, status=status))
            raise AuthenticationError(t("msg-e12f2d28", endpoint=endpoint))
        if status == 403:
            logger.error(t("msg-beda662d", endpoint=endpoint, status=status))
            raise AuthenticationError(t("msg-795ca227", endpoint=endpoint))
        if status == 404:
            logger.error(t("msg-5c6ba873", endpoint=endpoint, status=status))
            raise APIError(t("msg-74f2bac2", endpoint=endpoint))
        if status == 413:
            logger.error(t("msg-9ceafe4c", endpoint=endpoint, status=status))
            raise APIError(t("msg-3e336b73", endpoint=endpoint))
        if status == 429:
            logger.warning(t("msg-a47067de", endpoint=endpoint, status=status))
            raise APIRateLimitError(t("msg-901dc2da", endpoint=endpoint))
        if status == 500:
            logger.error(t("msg-2bea8c2e", endpoint=endpoint, status=status))
            raise APIConnectionError(t("msg-ae8d3725", endpoint=endpoint))
        if status == 502:
            logger.error(t("msg-7b028462", endpoint=endpoint, status=status))
            raise APIConnectionError(t("msg-978414ef", endpoint=endpoint))
        if status == 503:
            logger.error(t("msg-50895a69", endpoint=endpoint, status=status))
            raise APIConnectionError(t("msg-62adff89", endpoint=endpoint))
        if status == 504:
            logger.error(t("msg-1cf15497", endpoint=endpoint, status=status))
            raise APIConnectionError(t("msg-a8a2578d", endpoint=endpoint))
        logger.error(t("msg-c012110a", endpoint=endpoint, status=status))
        raise APIConnectionError(t("msg-dc96bbb8", status=status, endpoint=endpoint))

    async def _process_response(
        self,
        response: aiohttp.ClientResponse,
        endpoint: str,
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
                            t("msg-4c7598b6", res=len(notifications_data)),
                        )
                else:
                    logger.debug(t("msg-851a2a54", endpoint=endpoint))
                return result
            except json.JSONDecodeError as e:
                logger.error(t("msg-5f5609b6", e=e))
                raise APIConnectionError(t("msg-c8f7bbeb")) from e
        else:
            try:
                error_text = await response.text()
                logger.error(
                    t("msg-82748b31", endpoint=endpoint, res=response.status, error_text=error_text),
                )
            except Exception:
                logger.error(
                    t("msg-c6de3320", endpoint=endpoint, res=response.status),
                )

            self._handle_response_status(response.status, endpoint)

    @retry_async(
        max_retries=API_MAX_RETRIES,
        retryable_exceptions=(APIConnectionError, APIRateLimitError),
    )
    async def _make_request(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.instance_url}/api/{endpoint}"
        payload = {"i": self.access_token}
        if data:
            payload.update(data)

        try:
            async with self.session.post(url, json=payload) as response:
                return await self._process_response(response, endpoint)
        except aiohttp.ClientError as e:
            logger.error(t("msg-affb19a7", e=e))
            raise APIConnectionError(t("msg-9f1286b3", e=e)) from e

    async def create_note(
        self,
        text: str | None = None,
        visibility: str = "public",
        reply_id: str | None = None,
        visible_user_ids: list[str] | None = None,
        file_ids: list[str] | None = None,
        local_only: bool = False,
        cw: str | None = None,
        poll: dict[str, Any] | None = None,
        renote_id: str | None = None,
        channel_id: str | None = None,
        reaction_acceptance: str | None = None,
        no_extract_mentions: bool | None = None,
        no_extract_hashtags: bool | None = None,
        no_extract_emojis: bool | None = None,
        media_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a note (wrapper for notes/create). All additional fields are optional and passed through to the API."""
        data: dict[str, Any] = {}

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
        logger.debug(t("msg-44f91be2", note_id=note_id))
        return result

    async def upload_file(
        self,
        file_path: str,
        name: str | None = None,
        folder_id: str | None = None,
    ) -> dict[str, Any]:
        """Upload a file to Misskey drive/files/create and return a dict containing id and raw result."""
        if not file_path:
            raise APIError(t("msg-fbafd3db"))

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
                logger.error(t("msg-872d8419", file_path=file_path))
                raise APIError(t("msg-37186dea", file_path=file_path)) from e

            try:
                form.add_field("file", f, filename=filename)
                async with self.session.post(url, data=form) as resp:
                    result = await self._process_response(resp, "drive/files/create")
                    file_id = FileIDExtractor.extract_file_id(result)
                    logger.debug(
                        t("msg-65ef68e0", filename=filename, file_id=file_id),
                    )
                    return {"id": file_id, "raw": result}
            finally:
                f.close()
        except aiohttp.ClientError as e:
            logger.error(t("msg-0951db67", e=e))
            raise APIConnectionError(t("msg-e3a322f5", e=e)) from e

    async def find_files_by_hash(self, md5_hash: str) -> list[dict[str, Any]]:
        """Find files by MD5 hash"""
        if not md5_hash:
            raise APIError(t("msg-f28772b9"))

        data = {"md5": md5_hash}

        try:
            logger.debug(t("msg-25e566ef", md5_hash=md5_hash))
            result = await self._make_request("drive/files/find-by-hash", data)
            logger.debug(
                t("msg-a036a942", res=len(result) if isinstance(result, list) else 0),
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(t("msg-ea3581d5", e=e))
            raise

    async def find_files_by_name(
        self,
        name: str,
        folder_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find files by name"""
        if not name:
            raise APIError(t("msg-1d2a84ff"))

        data: dict[str, Any] = {"name": name}
        if folder_id:
            data["folderId"] = folder_id

        try:
            logger.debug(t("msg-f25e28b4", name=name, folder_id=folder_id))
            result = await self._make_request("drive/files/find", data)
            logger.debug(
                t("msg-cd43861a", res=len(result) if isinstance(result, list) else 0),
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(t("msg-05cd55ef", e=e))
            raise

    async def find_files(
        self,
        limit: int = 10,
        folder_id: str | None = None,
        type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List files with optional filters"""
        data: dict[str, Any] = {"limit": limit}
        if folder_id is not None:
            data["folderId"] = folder_id
        if type is not None:
            data["type"] = type

        try:
            logger.debug(
                t("msg-c01052a4", limit=limit, folder_id=folder_id, type=type),
            )
            result = await self._make_request("drive/files", data)
            logger.debug(
                t("msg-7c81620d", res=len(result) if isinstance(result, list) else 0),
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(t("msg-a187a089", e=e))
            raise

    async def _download_with_existing_session(
        self,
        url: str,
        ssl_verify: bool = True,
    ) -> bytes | None:
        """使用现有会话下载文件"""
        if not (hasattr(self, "session") and self.session):
            raise APIConnectionError(t("msg-9e776259"))

        async with self.session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=15),
            ssl=ssl_verify,
        ) as response:
            if response.status == 200:
                return await response.read()
        return None

    async def _download_with_temp_session(
        self,
        url: str,
        ssl_verify: bool = True,
    ) -> bytes | None:
        """使用临时会话下载文件"""
        connector = aiohttp.TCPConnector(ssl=ssl_verify)
        async with aiohttp.ClientSession(connector=connector) as temp_session:
            async with temp_session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 200:
                    return await response.read()
        return None

    async def upload_and_find_file(
        self,
        url: str,
        name: str | None = None,
        folder_id: str | None = None,
        max_wait_time: float = 30.0,
        check_interval: float = 2.0,
    ) -> dict[str, Any] | None:
        """简化的文件上传：尝试 URL 上传，失败则下载后本地上传

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
            raise APIError(t("msg-de18c220"))

        # 通过本地上传获取即时文件 ID（下载文件 → 上传 → 返回 ID）
        try:
            import os
            import tempfile

            # SSL 验证下载，失败则重试不验证 SSL
            tmp_bytes = None
            try:
                tmp_bytes = await self._download_with_existing_session(
                    url,
                    ssl_verify=True,
                ) or await self._download_with_temp_session(url, ssl_verify=True)
            except Exception as ssl_error:
                logger.debug(
                    t("msg-25b15b61", ssl_error=ssl_error),
                )
                try:
                    tmp_bytes = await self._download_with_existing_session(
                        url,
                        ssl_verify=False,
                    ) or await self._download_with_temp_session(url, ssl_verify=False)
                except Exception:
                    pass

            if tmp_bytes:
                with tempfile.NamedTemporaryFile(delete=False) as tmpf:
                    tmpf.write(tmp_bytes)
                    tmp_path = tmpf.name

                try:
                    result = await self.upload_file(tmp_path, name, folder_id)
                    logger.debug(t("msg-b6cbeef6", res=result.get('id')))
                    return result
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(t("msg-a4a898e2", e=e))

        return None

    async def get_current_user(self) -> dict[str, Any]:
        """获取当前用户信息"""
        return await self._make_request("i", {})

    async def send_message(
        self,
        user_id_or_payload: Any,
        text: str | None = None,
    ) -> dict[str, Any]:
        """发送聊天消息。

        Accepts either (user_id: str, text: str) or a single dict payload prepared by caller.
        """
        if isinstance(user_id_or_payload, dict):
            data = user_id_or_payload
        else:
            data = {"toUserId": user_id_or_payload, "text": text}

        result = await self._make_request("chat/messages/create-to-user", data)
        message_id = result.get("id", "unknown")
        logger.debug(t("msg-46b7ea4b", message_id=message_id))
        return result

    async def send_room_message(
        self,
        room_id_or_payload: Any,
        text: str | None = None,
    ) -> dict[str, Any]:
        """发送房间消息。

        Accepts either (room_id: str, text: str) or a single dict payload.
        """
        if isinstance(room_id_or_payload, dict):
            data = room_id_or_payload
        else:
            data = {"toRoomId": room_id_or_payload, "text": text}

        result = await self._make_request("chat/messages/create-to-room", data)
        message_id = result.get("id", "unknown")
        logger.debug(t("msg-32f71df4", message_id=message_id))
        return result

    async def get_messages(
        self,
        user_id: str,
        limit: int = 10,
        since_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取聊天消息历史"""
        data: dict[str, Any] = {"userId": user_id, "limit": limit}
        if since_id:
            data["sinceId"] = since_id

        result = await self._make_request("chat/messages/user-timeline", data)
        if isinstance(result, list):
            return result
        logger.warning(t("msg-7829f3b3", res=type(result)))
        return []

    async def get_mentions(
        self,
        limit: int = 10,
        since_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取提及通知"""
        data: dict[str, Any] = {"limit": limit}
        if since_id:
            data["sinceId"] = since_id
        data["includeTypes"] = ["mention", "reply", "quote"]

        result = await self._make_request("i/notifications", data)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "notifications" in result:
            return result["notifications"]
        logger.warning(t("msg-d74c86a1", res=type(result)))
        return []

    async def send_message_with_media(
        self,
        message_type: str,
        target_id: str,
        text: str | None = None,
        media_urls: list[str] | None = None,
        local_files: list[str] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """通用消息发送函数：统一处理文本+媒体发送

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
            raise APIError(t("msg-65ccb697"))

        file_ids = []

        # 处理远程媒体文件
        if media_urls:
            file_ids.extend(await self._process_media_urls(media_urls))

        # 处理本地文件
        if local_files:
            file_ids.extend(await self._process_local_files(local_files))

        # 根据消息类型发送
        return await self._dispatch_message(
            message_type,
            target_id,
            text,
            file_ids,
            **kwargs,
        )

    async def _process_media_urls(self, urls: list[str]) -> list[str]:
        """处理远程媒体文件URL列表，返回文件ID列表"""
        file_ids = []
        for url in urls:
            try:
                result = await self.upload_and_find_file(url)
                if result and result.get("id"):
                    file_ids.append(result["id"])
                    logger.debug(t("msg-b6afb123", res=result['id']))
                else:
                    logger.error(t("msg-4e62bcdc", url=url))
            except Exception as e:
                logger.error(t("msg-71cc9d61", url=url, e=e))
                # 继续处理其他文件，不中断整个流程
                continue
        return file_ids

    async def _process_local_files(self, file_paths: list[str]) -> list[str]:
        """处理本地文件路径列表，返回文件ID列表"""
        file_ids = []
        for file_path in file_paths:
            try:
                result = await self.upload_file(file_path)
                if result and result.get("id"):
                    file_ids.append(result["id"])
                    logger.debug(t("msg-75890c2b", res=result['id']))
                else:
                    logger.error(t("msg-024d0ed5", file_path=file_path))
            except Exception as e:
                logger.error(t("msg-f1fcb5e1", file_path=file_path, e=e))
                continue
        return file_ids

    async def _dispatch_message(
        self,
        message_type: str,
        target_id: str,
        text: str | None,
        file_ids: list[str],
        **kwargs,
    ) -> dict[str, Any]:
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

        if message_type == "room":
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

        if message_type == "note":
            # 发帖使用 fileIds (复数)
            note_kwargs = {
                "text": text,
                "file_ids": file_ids or None,
            }
            # 合并其他参数
            note_kwargs.update(kwargs)
            return await self.create_note(**note_kwargs)

        raise APIError(t("msg-1ee80a6b", message_type=message_type))
