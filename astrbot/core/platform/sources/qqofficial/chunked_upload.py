"""
分片上传模块
参照 openclaw-qqbot 的 chunked-upload.ts 实现

流程：
1. 申请上传 (upload_prepare) → 获取 upload_id + block_size + 分片预签名链接
2. 并行上传所有分片
3. 所有分片完成后，调用完成文件上传接口 → 获取 file_info

特性：
- 完善的重试机制（分片上传、分片完成、文件完成）
- 上传缓存（相同文件不重复上传）
- 用户友好的错误提示
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Tuple

import aiohttp

from astrbot import logger


# ============ 常量 ============

DEFAULT_CONCURRENT_PARTS = 1
MAX_CONCURRENT_PARTS = 10
PART_UPLOAD_TIMEOUT = 300  # 5分钟
PART_UPLOAD_MAX_RETRIES = 3
MAX_PART_FINISH_RETRY_TIMEOUT_MS = 10 * 60 * 1000  # 10分钟
MD5_10M_SIZE = 10002432  # 用于计算 md5_10m

# 每日上传限额错误码
UPLOAD_PREPARE_FALLBACK_CODE = 40093002
PART_FINISH_RETRYABLE_CODES = {40093001}

# 完成上传重试配置
COMPLETE_UPLOAD_MAX_RETRIES = 3
COMPLETE_UPLOAD_BASE_DELAY_MS = 2000

# 分片完成重试配置
PART_FINISH_MAX_RETRIES = 2
PART_FINISH_BASE_DELAY_MS = 1000
PART_FINISH_RETRYABLE_DEFAULT_TIMEOUT_MS = 2 * 60 * 1000
PART_FINISH_RETRYABLE_INTERVAL_MS = 1000


# ============ 异常定义 ============


class UploadDailyLimitExceededError(Exception):
    """每日上传限额超限"""

    def __init__(self, file_path: str, file_size: int, message: str):
        self.file_path = file_path
        self.file_size = file_size
        super().__init__(message)


class ApiError(Exception):
    """API 错误"""

    def __init__(
        self, message: str, status: int, path: str, biz_code: Optional[int] = None
    ):
        self.status = status
        self.path = path
        self.biz_code = biz_code
        super().__init__(message)


class ChunkedUploadError(Exception):
    """分片上传错误"""

    def __init__(
        self,
        message: str,
        file_path: str,
        file_size: int,
        cause: Optional[Exception] = None,
    ):
        self.file_path = file_path
        self.file_size = file_size
        self.cause = cause
        super().__init__(message)


# ============ 全局 HTTP 客户端管理器（按 appId 隔离）============

import threading


class QQBotHttpClientManager:
    """
    HTTP 客户端全局管理器

    按 appId 隔离客户端实例，实现多机器人共享 Token 缓存。
    - 同一 appId 的多个实例共享同一个 QQBotHttpClient
    - Singleflight 模式避免并发重复获取 Token

    注意：由于客户端创建是轻量操作，使用简单的同步锁即可，
    避免 asyncio.Lock 在非事件循环上下文中的问题。
    """

    _instance: Optional["QQBotHttpClientManager"] = None
    _clients: Dict[str, QQBotHttpClient] = {}
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "QQBotHttpClientManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    async def get_client(cls, appid: str, secret: str) -> QQBotHttpClient:
        """
        获取指定 appId 的 HTTP 客户端（按需创建，按 appId 隔离）

        Args:
            appid: QQ Bot AppID
            secret: QQ Bot Secret

        Returns:
            QQBotHttpClient: 该 appId 对应的 HTTP 客户端
        """
        # 使用同步锁保护客户端创建
        with cls._lock:
            if appid not in cls._clients:
                logger.debug(
                    f"[QQBotHttpClientManager] Creating new client for appId={appid[:8]}..."
                )
                cls._clients[appid] = QQBotHttpClient(appid, secret)
            return cls._clients[appid]

    @classmethod
    def clear(cls) -> None:
        """清除所有客户端实例（用于测试或重置）"""
        with cls._lock:
            cls._clients.clear()
        logger.debug("[QQBotHttpClientManager] All clients cleared")

    @classmethod
    def get_stats(cls) -> Dict[str, Dict]:
        """获取各客户端状态统计"""
        with cls._lock:
            return {
                appid: {
                    "has_token": client._token is not None,
                    "token_expires_in": max(
                        0, int(client._token_expires_at - time.time())
                    )
                    if client._token_expires_at
                    else None,
                }
                for appid, client in cls._clients.items()
            }


# ============ 数据类 ============


@dataclass
class UploadPrepareHashes:
    md5: str
    sha1: str
    md5_10m: str


@dataclass
class UploadPart:
    index: int
    presigned_url: str


@dataclass
class UploadPrepareResponse:
    upload_id: str
    block_size: int
    parts: list[UploadPart]
    concurrency: int = 1
    retry_timeout: int = 0


@dataclass
class MediaUploadResponse:
    file_uuid: str
    file_info: str
    ttl: int


@dataclass
class ChunkedUploadProgress:
    completed_parts: int
    total_parts: int
    uploaded_bytes: int
    total_bytes: int


# ============ 文件哈希计算 ============


async def compute_file_hashes(file_path: str, file_size: int) -> UploadPrepareHashes:
    """
    计算文件的 MD5、SHA1、md5_10m

    Args:
        file_path: 文件路径
        file_size: 文件大小

    Returns:
        UploadPrepareHashes: 文件哈希信息
    """
    md5_hash = hashlib.md5()
    sha1_hash = hashlib.sha1()
    md5_10m_hash = hashlib.md5()

    need_10m = file_size > MD5_10M_SIZE
    bytes_read = 0

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)  # 64KB
            if not chunk:
                break

            md5_hash.update(chunk)
            sha1_hash.update(chunk)

            if need_10m:
                remaining = MD5_10M_SIZE - bytes_read
                if remaining > 0:
                    md5_10m_hash.update(
                        chunk[:remaining] if len(chunk) > remaining else chunk
                    )

            bytes_read += len(chunk)

    return UploadPrepareHashes(
        md5=md5_hash.hexdigest(),
        sha1=sha1_hash.hexdigest(),
        md5_10m=md5_10m_hash.hexdigest() if need_10m else md5_hash.hexdigest(),
    )


def read_file_chunk(file_path: str, offset: int, length: int) -> bytes:
    """读取文件的指定区间"""
    with open(file_path, "rb") as f:
        f.seek(offset)
        return f.read(length)


# ============ API 请求封装 ============


class QQBotHttpClient:
    """QQ Bot HTTP 客户端，直接调用 API"""

    API_BASE = "https://api.sgroup.qq.com"
    TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"

    # User-Agent 标识
    PLUGIN_USER_AGENT = "AstrBot-QQOfficial/1.0 (Python/3.x)"

    def __init__(self, appid: str, secret: str):
        self.appid = appid
        self.secret = secret
        self._token: Optional[str] = None
        self._token_expires_at: float = 0
        self._token_fetch_lock = asyncio.Lock()
        self._token_fetch_promise: Optional[asyncio.Future[str]] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建共享的 ClientSession"""
        if self._session is None or self._session.closed:
            async with self._session_lock:
                if self._session is None or self._session.closed:
                    connector = aiohttp.TCPConnector(
                        limit=100,
                        keepalive_timeout=30,
                    )
                    self._session = aiohttp.ClientSession(
                        connector=connector,
                    )
        return self._session

    async def close(self):
        """关闭 ClientSession"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def get_access_token(self) -> str:
        """
        获取 AccessToken（带缓存 + singleflight 并发安全）

        使用 singleflight 模式：当多个请求同时发现 Token 过期时，
        只有第一个请求会真正去获取新 Token，其他请求复用同一个 Promise。
        """
        # 提前5分钟刷新
        if self._token and time.time() < self._token_expires_at - 300:
            return self._token

        # Singleflight: 避免并发重复获取
        async with self._token_fetch_lock:
            # 双重检查
            if self._token and time.time() < self._token_expires_at - 300:
                return self._token

            # 如果已有进行中的获取请求，复用它
            if self._token_fetch_promise is not None:
                return await self._token_fetch_promise

            # 创建新的获取请求
            self._token_fetch_promise = asyncio.create_task(self._do_fetch_token())
            try:
                token = await self._token_fetch_promise
                return token
            finally:
                self._token_fetch_promise = None

    async def _do_fetch_token(self) -> str:
        """实际执行 Token 获取"""
        logger.debug(f"[QQBotHttpClient:{self.appid}] Fetching access token...")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.TOKEN_URL,
                json={"appId": self.appid, "clientSecret": self.secret},
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": self.PLUGIN_USER_AGENT,
                },
            ) as resp:
                data = await resp.json()
                if "access_token" not in data:
                    error_msg = data.get("message", str(data))
                    logger.error(
                        f"[QQBotHttpClient:{self.appid}] Token fetch failed: {error_msg}"
                    )
                    raise RuntimeError(f"获取 access_token 失败: {error_msg}")

                self._token = data["access_token"]
                expires_in = int(data.get("expires_in", 7200))
                self._token_expires_at = time.time() + expires_in

                logger.debug(
                    f"[QQBotHttpClient:{self.appid}] Token cached, expires in {expires_in}s"
                )
                return self._token

    async def api_request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        timeout: float = 300.0,
    ) -> dict:
        """API 请求封装（带详细日志）"""
        token = await self.get_access_token()
        url = f"{self.API_BASE}{path}"
        headers = {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json",
            "User-Agent": self.PLUGIN_USER_AGENT,
        }

        # 打印请求信息（隐藏敏感数据）
        log_body = dict(body) if body else None
        if log_body and "file_data" in log_body:
            log_body["file_data"] = f"<base64 {len(log_body['file_data'])} chars>"
        logger.debug(f"[QQBotHttpClient] >>> {method} {path}")
        if log_body:
            logger.debug(f"[QQBotHttpClient] >>> Body: {log_body}")

        session = await self._get_session()
        async with session.request(
            method,
            url,
            json=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            # 打印响应信息
            trace_id = resp.headers.get("x-tps-trace-id", "")
            logger.debug(
                f"[QQBotHttpClient] <<< Status: {resp.status} {resp.reason}"
                + (f" | TraceId: {trace_id}" if trace_id else "")
            )

            raw = await resp.text()
            logger.debug(f"[QQBotHttpClient] <<< Body: {raw[:500]}")

            if not resp.ok:
                try:
                    import json

                    err_data = json.loads(raw) if raw else {}
                    biz_code = err_data.get("code") or err_data.get("err_code")
                    error_msg = err_data.get("message", "Unknown error")

                    logger.error(
                        f"[QQBotHttpClient] API Error [{path}]: {error_msg} (bizCode={biz_code})"
                    )
                    raise ApiError(
                        f"API Error [{path}]: {error_msg}", resp.status, path, biz_code
                    )
                except Exception as e:
                    if isinstance(e, ApiError):
                        raise
                    logger.error(
                        f"[QQBotHttpClient] API Error [{path}] HTTP {resp.status}: {raw[:200]}"
                    )
                    raise ApiError(
                        f"API Error [{path}] HTTP {resp.status}: {raw[:200]}",
                        resp.status,
                        path,
                    )

            import json

            return json.loads(raw)

    async def base64_upload(
        self,
        file_type: int,
        file_data: str,
        file_name: Optional[str] = None,
        srv_send_msg: bool = False,
        target_type: str = "c2c",
        target_id: str = "",
    ) -> MediaUploadResponse:
        """
        Base64 格式上传文件（小文件专用，带长超时）

        与分片上传不同，Base64 上传直接将文件内容放在请求体中，
        适用于 5MB 以下的文件。超时设置为 300 秒（5分钟）以适应慢速网络。

        Args:
            file_type: 文件类型（1=图片, 2=视频, 3=语音, 4=文件）
            file_data: Base64 编码的文件内容
            file_name: 文件名（可选）
            srv_send_msg: 是否作为机器人发送
            target_type: 目标类型 ("c2c" 或 "group")
            target_id: 用户 openid 或群 openid

        Returns:
            MediaUploadResponse: 包含 file_uuid, file_info, ttl
        """
        if target_type == "c2c":
            path = f"/v2/users/{target_id}/files"
        else:
            path = f"/v2/groups/{target_id}/files"

        payload = {
            "file_type": file_type,
            "file_data": file_data,
            "srv_send_msg": srv_send_msg,
        }
        if file_name:
            payload["file_name"] = file_name

        logger.info(
            f"[QQBotHttpClient] Base64 upload: target={target_type}:{target_id[:16]}, file_type={file_type}, size={len(file_data)} chars"
        )

        data = await self.api_request("POST", path, body=payload, timeout=300.0)

        return MediaUploadResponse(
            file_uuid=data["file_uuid"],
            file_info=data["file_info"],
            ttl=data.get("ttl", 0),
        )

    async def c2c_upload_prepare(
        self,
        user_id: str,
        file_type: int,
        file_name: str,
        file_size: int,
        hashes: UploadPrepareHashes,
    ) -> UploadPrepareResponse:
        """C2C 申请上传"""
        logger.info(
            f"[QQBotHttpClient] C2C upload_prepare: user={user_id[:16]}, file={file_name}, size={file_size}"
        )

        data = await self.api_request(
            "POST",
            f"/v2/users/{user_id}/upload_prepare",
            {
                "file_type": file_type,
                "file_name": file_name,
                "file_size": file_size,
                "md5": hashes.md5,
                "sha1": hashes.sha1,
                "md5_10m": hashes.md5_10m,
            },
            timeout=60.0,
        )

        logger.info(
            f"[QQBotHttpClient] C2C upload_prepare success: upload_id={data['upload_id']}, parts={len(data['parts'])}"
        )

        return UploadPrepareResponse(
            upload_id=data["upload_id"],
            block_size=int(data["block_size"]),
            parts=[
                UploadPart(index=p["index"], presigned_url=p["presigned_url"])
                for p in data["parts"]
            ],
            concurrency=int(data.get("concurrency", 1)),
            retry_timeout=int(data.get("retry_timeout", 0)),
        )

    async def c2c_upload_part_finish(
        self,
        user_id: str,
        upload_id: str,
        part_index: int,
        block_size: int,
        md5: str,
        retry_timeout_ms: Optional[int] = None,
    ) -> None:
        """C2C 完成分片上传（带持续重试）"""
        logger.debug(f"[QQBotHttpClient] C2C upload_part_finish: part={part_index}")
        await self._part_finish_with_retry(
            "POST",
            f"/v2/users/{user_id}/upload_part_finish",
            {
                "upload_id": upload_id,
                "part_index": part_index,
                "block_size": block_size,
                "md5": md5,
            },
            retry_timeout_ms,
        )

    async def c2c_complete_upload(
        self, user_id: str, upload_id: str
    ) -> MediaUploadResponse:
        """C2C 完成文件上传（带重试）"""
        result = await self._complete_upload_with_retry(
            "POST", f"/v2/users/{user_id}/files", {"upload_id": upload_id}
        )
        logger.info(
            f"[QQBotHttpClient] c2c complete_upload success: upload_id={upload_id}, file_uuid={result.file_uuid}"
        )
        return result

    async def group_upload_prepare(
        self,
        group_id: str,
        file_type: int,
        file_name: str,
        file_size: int,
        hashes: UploadPrepareHashes,
    ) -> UploadPrepareResponse:
        """Group 申请上传"""
        logger.info(
            f"[QQBotHttpClient] Group upload_prepare: group={group_id[:16]}, file={file_name}, size={file_size}"
        )

        data = await self.api_request(
            "POST",
            f"/v2/groups/{group_id}/upload_prepare",
            {
                "file_type": file_type,
                "file_name": file_name,
                "file_size": file_size,
                "md5": hashes.md5,
                "sha1": hashes.sha1,
                "md5_10m": hashes.md5_10m,
            },
            timeout=60.0,
        )

        logger.info(
            f"[QQBotHttpClient] Group upload_prepare success: upload_id={data['upload_id']}, parts={len(data['parts'])}"
        )

        return UploadPrepareResponse(
            upload_id=data["upload_id"],
            block_size=int(data["block_size"]),
            parts=[
                UploadPart(index=p["index"], presigned_url=p["presigned_url"])
                for p in data["parts"]
            ],
            concurrency=int(data.get("concurrency", 1)),
            retry_timeout=int(data.get("retry_timeout", 0)),
        )

    async def group_upload_part_finish(
        self,
        group_id: str,
        upload_id: str,
        part_index: int,
        block_size: int,
        md5: str,
        retry_timeout_ms: Optional[int] = None,
    ) -> None:
        """Group 完成分片上传（带持续重试）"""
        await self._part_finish_with_retry(
            "POST",
            f"/v2/groups/{group_id}/upload_part_finish",
            {
                "upload_id": upload_id,
                "part_index": part_index,
                "block_size": block_size,
                "md5": md5,
            },
            retry_timeout_ms,
        )

    async def group_complete_upload(
        self, group_id: str, upload_id: str
    ) -> MediaUploadResponse:
        """Group 完成文件上传（带重试）"""
        return await self._complete_upload_with_retry(
            "POST", f"/v2/groups/{group_id}/files", {"upload_id": upload_id}
        )

    # ============ 内部重试逻辑 ============

    async def _part_finish_with_retry(
        self, method: str, path: str, body: dict, retry_timeout_ms: Optional[int] = None
    ) -> None:
        """分片完成接口重试策略"""
        PART_FINISH_MAX_RETRIES = 2
        PART_FINISH_BASE_DELAY_MS = 1000
        PART_FINISH_RETRYABLE_DEFAULT_TIMEOUT_MS = 2 * 60 * 1000
        PART_FINISH_RETRYABLE_INTERVAL_MS = 1000

        last_error: Optional[Exception] = None

        for attempt in range(PART_FINISH_MAX_RETRIES + 1):
            try:
                await self.api_request(method, path, body, timeout=60.0)
                return
            except Exception as err:
                last_error = err

                # 命中特定错误码 → 进入持续重试模式
                if (
                    isinstance(err, ApiError)
                    and err.biz_code in PART_FINISH_RETRYABLE_CODES
                ):
                    timeout_ms = (
                        retry_timeout_ms or PART_FINISH_RETRYABLE_DEFAULT_TIMEOUT_MS
                    )
                    logger.warning(
                        f"[chunked] PartFinish hit retryable bizCode={err.biz_code}, entering persistent retry (timeout={timeout_ms / 1000}s)"
                    )
                    await self._part_finish_persistent_retry(
                        method, path, body, timeout_ms
                    )
                    return

                if attempt < PART_FINISH_MAX_RETRIES:
                    delay = PART_FINISH_BASE_DELAY_MS * (2**attempt) / 1000
                    logger.warning(
                        f"[chunked] PartFinish attempt {attempt + 1} failed, retrying in {delay}s: {str(err)[:200]}"
                    )
                    await asyncio.sleep(delay)

        raise last_error or RuntimeError("PartFinish failed")

    async def _part_finish_persistent_retry(
        self, method: str, path: str, body: dict, timeout_ms: int
    ) -> None:
        """特定错误码的持续重试模式"""
        PART_FINISH_RETRYABLE_INTERVAL_MS = 1000
        deadline = time.time() + timeout_ms / 1000
        attempt = 0

        while time.time() < deadline:
            try:
                await self.api_request(method, path, body, timeout=60.0)
                logger.info(
                    f"[chunked] PartFinish persistent retry succeeded after {attempt} retries"
                )
                return
            except Exception as err:
                # 如果不再是可重试的错误码，直接抛出
                if not (
                    isinstance(err, ApiError)
                    and err.biz_code in PART_FINISH_RETRYABLE_CODES
                ):
                    logger.error(
                        f"[chunked] PartFinish persistent retry: error is no longer retryable"
                    )
                    raise

                attempt += 1
                remaining = deadline - time.time()
                if remaining <= 0:
                    break

                logger.warning(
                    f"[chunked] PartFinish persistent retry #{attempt}: bizCode={err.biz_code}, retrying (remaining={int(remaining)}s)"
                )
                await asyncio.sleep(PART_FINISH_RETRYABLE_INTERVAL_MS / 1000)

        raise RuntimeError(
            f"upload_part_finish 持续重试超时（{timeout_ms / 1000}s, {attempt} 次重试）"
        )

    async def _complete_upload_with_retry(
        self, method: str, path: str, body: dict
    ) -> MediaUploadResponse:
        """完成上传接口重试（无条件重试）"""
        COMPLETE_UPLOAD_MAX_RETRIES = 2
        COMPLETE_UPLOAD_BASE_DELAY_MS = 2000

        last_error: Optional[Exception] = None

        for attempt in range(COMPLETE_UPLOAD_MAX_RETRIES + 1):
            try:
                data = await self.api_request(method, path, body, timeout=120.0)
                return MediaUploadResponse(
                    file_uuid=data["file_uuid"],
                    file_info=data["file_info"],
                    ttl=data.get("ttl", 0),
                )
            except Exception as err:
                last_error = err

                if attempt < COMPLETE_UPLOAD_MAX_RETRIES:
                    delay = COMPLETE_UPLOAD_BASE_DELAY_MS * (2**attempt) / 1000
                    logger.warning(
                        f"[chunked] CompleteUpload attempt {attempt + 1} failed, retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)

        raise last_error or RuntimeError("CompleteUpload failed")


# ============ 分片上传核心逻辑 ============


async def put_to_presigned_url(
    presigned_url: str,
    data: bytes,
    prefix: str = "[chunked]",
    part_index: int = 0,
    total_parts: int = 0,
) -> None:
    """PUT 分片数据到预签名 URL（带重试）"""
    last_error: Optional[Exception] = None

    for attempt in range(PART_UPLOAD_MAX_RETRIES + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=PART_UPLOAD_TIMEOUT, connect=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.put(
                    presigned_url, data=data, headers={"Content-Length": str(len(data))}
                ) as resp:
                    if not resp.ok:
                        body = await resp.text()
                        raise RuntimeError(
                            f"COS PUT failed: {resp.status} {body[:200]}"
                        )

                    logger.debug(
                        f"{prefix} Part {part_index}/{total_parts}: uploaded {len(data)} bytes"
                    )
                    return
        except Exception as e:
            last_error = e
            if attempt < PART_UPLOAD_MAX_RETRIES:
                delay = 1000 * (2**attempt) / 1000  # 1s, 2s
                logger.warning(
                    f"{prefix} Part {part_index}/{total_parts}: attempt {attempt + 1} failed, retrying in {delay}s: {str(e)[:100]}"
                )
                await asyncio.sleep(delay)

    raise last_error or RuntimeError("Upload failed")


async def chunked_upload_c2c(
    http_client: QQBotHttpClient,
    user_id: str,
    file_path: str,
    file_type: int,
    on_progress: Optional[Callable[[ChunkedUploadProgress], None]] = None,
    log_prefix: str = "[chunked]",
) -> MediaUploadResponse:
    """C2C 大文件分片上传"""
    prefix = log_prefix

    # 1. 读取文件信息
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    logger.info(
        f"{prefix} Starting chunked upload: file={file_name}, size={file_size}, type={file_type}"
    )

    # 2. 计算文件哈希
    logger.debug(f"{prefix} Computing file hashes...")
    hashes = await compute_file_hashes(file_path, file_size)
    logger.debug(f"{prefix} File hashes: md5={hashes.md5[:16]}...")

    # 3. 申请上传
    try:
        prepare_resp = await http_client.c2c_upload_prepare(
            user_id, file_type, file_name, file_size, hashes
        )
    except ApiError as e:
        if e.biz_code == UPLOAD_PREPARE_FALLBACK_CODE:
            raise UploadDailyLimitExceededError(file_path, file_size, str(e))
        raise

    upload_id = prepare_resp.upload_id
    block_size = prepare_resp.block_size
    parts = prepare_resp.parts
    concurrency = min(
        prepare_resp.concurrency or DEFAULT_CONCURRENT_PARTS, MAX_CONCURRENT_PARTS
    )
    retry_timeout_ms = (
        prepare_resp.retry_timeout * 1000 if prepare_resp.retry_timeout else None
    )

    logger.info(
        f"{prefix} Upload prepared: upload_id={upload_id}, block_size={block_size}, parts={len(parts)}, concurrency={concurrency}"
    )

    # 4. 并行上传所有分片
    completed_parts = 0
    uploaded_bytes = 0

    async def upload_part(part: UploadPart) -> None:
        nonlocal completed_parts, uploaded_bytes

        part_index = part.index
        offset = (part_index - 1) * block_size
        length = min(block_size, file_size - offset)

        # 读取分片数据
        part_data = read_file_chunk(file_path, offset, length)
        part_md5 = hashlib.md5(part_data).hexdigest()

        logger.debug(
            f"{prefix} Part {part_index}/{len(parts)}: uploading {length} bytes"
        )

        # PUT 到预签名 URL
        await put_to_presigned_url(
            part.presigned_url, part_data, prefix, part_index, len(parts)
        )

        # 通知平台分片完成（带重试）
        await http_client.c2c_upload_part_finish(
            user_id, upload_id, part_index, length, part_md5, retry_timeout_ms
        )

        # 更新进度
        completed_parts += 1
        uploaded_bytes += length

        if on_progress:
            on_progress(
                ChunkedUploadProgress(
                    completed_parts=completed_parts,
                    total_parts=len(parts),
                    uploaded_bytes=uploaded_bytes,
                    total_bytes=file_size,
                )
            )

    # 按并发数分批执行
    for i in range(0, len(parts), concurrency):
        batch = parts[i : i + concurrency]
        await asyncio.gather(*[upload_part(p) for p in batch])

    logger.info(f"{prefix} All {len(parts)} parts uploaded, completing...")

    # 5. 完成文件上传
    result = await http_client.c2c_complete_upload(user_id, upload_id)
    logger.info(
        f"{prefix} Upload completed: file_uuid={result.file_uuid}, ttl={result.ttl}s"
    )

    return result


async def chunked_upload_group(
    http_client: QQBotHttpClient,
    group_id: str,
    file_path: str,
    file_type: int,
    on_progress: Optional[Callable[[ChunkedUploadProgress], None]] = None,
    log_prefix: str = "[chunked]",
) -> MediaUploadResponse:
    """Group 大文件分片上传"""
    prefix = log_prefix

    # 1. 读取文件信息
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    logger.info(
        f"{prefix} Starting chunked upload (group): file={file_name}, size={file_size}, type={file_type}"
    )

    # 2. 计算文件哈希
    logger.debug(f"{prefix} Computing file hashes...")
    hashes = await compute_file_hashes(file_path, file_size)

    # 3. 申请上传
    try:
        prepare_resp = await http_client.group_upload_prepare(
            group_id, file_type, file_name, file_size, hashes
        )
    except ApiError as e:
        if e.biz_code == UPLOAD_PREPARE_FALLBACK_CODE:
            raise UploadDailyLimitExceededError(file_path, file_size, str(e))
        raise

    upload_id = prepare_resp.upload_id
    block_size = prepare_resp.block_size
    parts = prepare_resp.parts
    concurrency = min(
        prepare_resp.concurrency or DEFAULT_CONCURRENT_PARTS, MAX_CONCURRENT_PARTS
    )
    retry_timeout_ms = (
        prepare_resp.retry_timeout * 1000 if prepare_resp.retry_timeout else None
    )

    logger.info(
        f"{prefix} Upload prepared: upload_id={upload_id}, block_size={block_size}, parts={len(parts)}"
    )

    # 4. 并行上传所有分片
    completed_parts = 0
    uploaded_bytes = 0

    async def upload_part(part: UploadPart) -> None:
        nonlocal completed_parts, uploaded_bytes

        part_index = part.index
        offset = (part_index - 1) * block_size
        length = min(block_size, file_size - offset)

        part_data = read_file_chunk(file_path, offset, length)
        part_md5 = hashlib.md5(part_data).hexdigest()

        await put_to_presigned_url(
            part.presigned_url, part_data, prefix, part_index, len(parts)
        )
        await http_client.group_upload_part_finish(
            group_id, upload_id, part_index, length, part_md5, retry_timeout_ms
        )

        completed_parts += 1
        uploaded_bytes += length

        if on_progress:
            on_progress(
                ChunkedUploadProgress(
                    completed_parts=completed_parts,
                    total_parts=len(parts),
                    uploaded_bytes=uploaded_bytes,
                    total_bytes=file_size,
                )
            )

    for i in range(0, len(parts), concurrency):
        batch = parts[i : i + concurrency]
        await asyncio.gather(*[upload_part(p) for p in batch])

    logger.info(f"{prefix} All {len(parts)} parts uploaded, completing...")

    # 5. 完成文件上传
    result = await http_client.group_complete_upload(group_id, upload_id)
    logger.info(
        f"{prefix} Upload completed: file_uuid={result.file_uuid}, ttl={result.ttl}s"
    )

    return result
