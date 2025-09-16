import json
from typing import Any, Optional, Dict, List

try:
    import aiohttp
except ImportError as e:
    raise ImportError(
        "aiohttp is required for Misskey API. Please install it with: pip install aiohttp"
    ) from e

from astrbot.api import logger

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

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
        logger.debug("Misskey API 客户端已关闭")

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    def _handle_response_status(self, status: int, endpoint: str):
        if status == HTTP_BAD_REQUEST:
            logger.error(f"API 请求错误: {endpoint} (状态码: {status})")
            raise APIBadRequestError(f"Bad request for {endpoint}")
        elif status in (HTTP_UNAUTHORIZED, HTTP_FORBIDDEN):
            logger.error(f"API 认证失败: {endpoint} (状态码: {status})")
            raise AuthenticationError(f"Authentication failed for {endpoint}")
        elif status == HTTP_TOO_MANY_REQUESTS:
            logger.warning(f"API 频率限制: {endpoint} (状态码: {status})")
            raise APIRateLimitError(f"Rate limit exceeded for {endpoint}")
        else:
            logger.error(f"API 请求失败: {endpoint} (状态码: {status})")
            raise APIConnectionError(f"HTTP {status} for {endpoint}")

    async def _process_response(
        self, response: aiohttp.ClientResponse, endpoint: str
    ) -> Dict[str, Any]:
        if response.status == HTTP_OK:
            try:
                result = await response.json()
                logger.debug(f"Misskey API 请求成功: {endpoint}")
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
                logger.error(
                    f"API 请求失败: {endpoint} - 状态码: {response.status}, 无法读取错误响应"
                )

            self._handle_response_status(response.status, endpoint)
            raise APIConnectionError(f"Request failed for {endpoint}")

    @retry_async(
        max_retries=API_MAX_RETRIES,
        retryable_exceptions=(APIConnectionError, APIRateLimitError),
    )
    async def _make_request(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {"text": text, "visibility": visibility}
        if reply_id:
            data["replyId"] = reply_id
        if visible_user_ids and visibility == "specified":
            data["visibleUserIds"] = visible_user_ids

        result = await self._make_request("notes/create", data)
        note_id = result.get("createdNote", {}).get("id", "unknown")
        logger.debug(f"Misskey 发帖成功，note_id: {note_id}")
        return result

    async def get_current_user(self) -> Dict[str, Any]:
        return await self._make_request("i", {})

    async def send_message(self, user_id: str, text: str) -> Dict[str, Any]:
        result = await self._make_request(
            "chat/messages/create-to-user", {"toUserId": user_id, "text": text}
        )
        message_id = result.get("id", "unknown")
        logger.debug(f"Misskey 聊天发送成功，message_id: {message_id}")
        return result

    async def get_mentions(
        self, limit: int = 10, since_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
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
            logger.warning(
                f"获取提及通知响应格式异常: {type(result)}, 响应内容: {result}"
            )
            return []
