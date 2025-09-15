import json
from typing import Any, Optional

try:
    import aiohttp
except ImportError as e:
    raise ImportError(
        "aiohttp is required for Misskey API. Please install it with: pip install aiohttp"
    ) from e

try:
    from loguru import logger  # type: ignore
except ImportError:
    try:
        from astrbot import logger
    except ImportError:
        import logging

        logger = logging.getLogger(__name__)

# Constants
API_MAX_RETRIES = 3
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_TOO_MANY_REQUESTS = 429


# Exceptions
class APIError(Exception):
    pass


class APIBadRequestError(APIError):
    pass


class APIConnectionError(APIError):
    pass


class APIRateLimitError(APIError):
    pass


class AuthenticationError(APIError):
    pass


# HTTP Client Session Manager
class ClientSession:
    session: aiohttp.ClientSession | None = None
    _token: str | None = None

    @classmethod
    def set_token(cls, token: str):
        cls._token = token

    @classmethod
    async def close_session(cls, silent: bool = False):
        if cls.session is not None:
            try:
                await cls.session.close()
            except Exception:
                if not silent:
                    raise
            finally:
                cls.session = None

    @classmethod
    def _ensure_session(cls):
        if cls.session is None:
            headers = {}
            if cls._token:
                headers["Authorization"] = f"Bearer {cls._token}"
            cls.session = aiohttp.ClientSession(headers=headers)

    @classmethod
    def post(cls, url, json=None):
        cls._ensure_session()
        if cls.session is None:
            raise RuntimeError("Failed to create HTTP session")
        return cls.session.post(url, json=json)


# Retry decorator for API requests
def retry_async(max_retries=3, retryable_exceptions=()):
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


__all__ = ("MisskeyAPI",)


class MisskeyAPI:
    """Misskey API 客户端，专为 AstrBot 适配器优化"""

    def __init__(self, instance_url: str, access_token: str):
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.transport = ClientSession
        self.transport.set_token(access_token)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def close(self) -> None:
        """关闭 API 客户端"""
        await self.transport.close_session(silent=True)
        logger.debug("Misskey API 客户端已关闭")

    @property
    def session(self):
        self.transport._ensure_session()
        if self.transport.session is None:
            raise RuntimeError("Failed to create HTTP session")
        return self.transport.session

    def _handle_response_status(self, response, endpoint: str):
        status = response.status
        if status == HTTP_BAD_REQUEST:
            logger.error(f"API 请求错误: {endpoint} (状态码: {status})")
            raise APIBadRequestError()
        if status == HTTP_UNAUTHORIZED:
            logger.error(f"API 认证失败: {endpoint} (状态码: {status})")
            raise AuthenticationError()
        if status == HTTP_FORBIDDEN:
            logger.error(f"API 权限不足: {endpoint} (状态码: {status})")
            raise AuthenticationError()
        if status == HTTP_TOO_MANY_REQUESTS:
            logger.warning(f"API 频率限制: {endpoint} (状态码: {status})")
            raise APIRateLimitError()

    async def _process_response(self, response, endpoint: str):
        if response.status == HTTP_OK:
            try:
                result = await response.json()
                logger.debug(f"Misskey API 请求成功: {endpoint}")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"响应不是有效的 JSON 格式: {e}")
                raise APIConnectionError() from e
        # 获取错误响应的详细内容
        try:
            error_text = await response.text()
            logger.error(
                f"API 请求失败: {endpoint} - 状态码: {response.status}, 响应: {error_text}"
            )
        except Exception:
            logger.error(
                f"API 请求失败: {endpoint} - 状态码: {response.status}, 无法读取错误响应"
            )

        self._handle_response_status(response, endpoint)
        raise APIConnectionError()

    @retry_async(
        max_retries=API_MAX_RETRIES,
        retryable_exceptions=(APIConnectionError, APIRateLimitError),
    )
    async def _make_request(
        self, endpoint: str, data: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """发送 API 请求"""
        url = f"{self.instance_url}/api/{endpoint}"
        payload = {"i": self.access_token}
        if data:
            payload |= data
        try:
            async with self.session.post(url, json=payload) as response:
                return await self._process_response(response, endpoint)
        except (aiohttp.ClientError, json.JSONDecodeError) as e:
            logger.error(f"HTTP 请求错误: {e}")
            raise APIConnectionError() from e

    async def create_note(
        self,
        text: str,
        visibility: str = "public",
        reply_id: Optional[str] = None,
        visible_user_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """创建帖子/回复"""
        data: dict[str, Any] = {"text": text, "visibility": visibility}
        if reply_id:
            data["replyId"] = reply_id
        if visible_user_ids and visibility == "specified":
            data["visibleUserIds"] = visible_user_ids

        result = await self._make_request("notes/create", data)
        note_id = result.get("createdNote", {}).get("id", "unknown")
        logger.debug(f"Misskey 发帖成功，note_id: {note_id}")
        return result

    async def get_current_user(self) -> dict[str, Any]:
        """获取当前用户信息"""
        return await self._make_request("i", {})

    async def send_message(self, user_id: str, text: str) -> dict[str, Any]:
        """发送私信"""
        result = await self._make_request(
            "chat/messages/create-to-user", {"toUserId": user_id, "text": text}
        )
        message_id = result.get("id", "unknown")
        logger.debug(f"Misskey 聊天发送成功，message_id: {message_id}")
        return result

    async def get_mentions(
        self, limit: int = 10, since_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """获取提及通知（包括回复和引用）"""
        data: dict[str, Any] = {"limit": limit}
        if since_id:
            data["sinceId"] = since_id
        data["includeTypes"] = ["mention", "reply", "quote"]

        result = await self._make_request("i/notifications", data)
        # Misskey API 返回通知列表
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and "notifications" in result:
            return result["notifications"]
        else:
            logger.warning(
                f"获取提及通知响应格式异常: {type(result)}, 响应内容: {result}"
            )
            return []
