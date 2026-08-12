"""Chunked file uploads for QQ Official C2C and group messages."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import aiohttp
from botpy.http import BotHttp, Route
from botpy.types.message import Media

from astrbot import logger

QQOFFICIAL_CHUNKED_UPLOAD_THRESHOLD = 10 * 1024 * 1024

_MD5_10M_BYTES = 10_002_432
_API_TIMEOUT_SECONDS = 300
_API_TRANSPORT_ATTEMPTS = 3
_UPLOAD_API_ATTEMPTS = 3
_MAX_CONCURRENCY = 4
_PART_PUT_ATTEMPTS = 3
_DEFAULT_RETRY_TIMEOUT_SECONDS = 300.0
_MAX_RETRY_TIMEOUT_SECONDS = 600.0
_DEFAULT_RETRY_DELAY_SECONDS = 1.0
_RETRYABLE_UPLOAD_CODE = 40093001
_DAILY_QUOTA_CODE = 40093002


class QQOfficialChunkedUploadError(RuntimeError):
    """Raised when a QQ Official chunked upload cannot be completed."""


class _QQOfficialAPIError(RuntimeError):
    """Represent a structured error returned by the QQ Official API.

    Args:
        code: QQ business error code, when present.
        message: Human-readable error message.
        status: HTTP response status.
    """

    def __init__(self, code: int | str | None, message: str, status: int) -> None:
        self.code = code
        self.status = status
        super().__init__(f"{message} (code={code}, http={status})")


@dataclass(frozen=True, slots=True)
class _UploadSession:
    """Store state shared by all parts of one upload."""

    base_path: str
    upload_id: str
    block_size: int
    part_index_base: int
    file_path: Path
    file_size: int
    retry_timeout: float
    retry_delay: float
    total_parts: int


def _compute_file_hashes(file_path: Path) -> dict[str, str]:
    """Compute the hashes required by QQ in one pass over a file.

    Args:
        file_path: Local file to hash.

    Returns:
        MD5, SHA1, and first-10,002,432-byte MD5 hex digests.

    Raises:
        OSError: If the file cannot be read.
    """
    full_md5 = hashlib.md5(usedforsecurity=False)
    full_sha1 = hashlib.sha1(usedforsecurity=False)
    prefix_md5 = hashlib.md5(usedforsecurity=False)
    prefix_remaining = _MD5_10M_BYTES

    with file_path.open("rb") as file:
        while chunk := file.read(64 * 1024):
            full_md5.update(chunk)
            full_sha1.update(chunk)
            if prefix_remaining > 0:
                prefix_chunk = chunk[:prefix_remaining]
                prefix_md5.update(prefix_chunk)
                prefix_remaining -= len(prefix_chunk)

    return {
        "md5": full_md5.hexdigest(),
        "sha1": full_sha1.hexdigest(),
        "md5_10m": prefix_md5.hexdigest(),
    }


def _read_file_part(file_path: Path, offset: int, length: int) -> bytes:
    """Read exactly one requested file part.

    Args:
        file_path: Local file to read.
        offset: Zero-based byte offset.
        length: Number of bytes to read.

    Returns:
        The requested bytes.

    Raises:
        OSError: If the file cannot be read or is shorter than expected.
    """
    with file_path.open("rb") as file:
        file.seek(offset)
        data = file.read(length)
    if len(data) != length:
        raise OSError(
            f"Short read from {file_path}: expected {length} bytes at offset "
            f"{offset}, got {len(data)}"
        )
    return data


def _coerce_int(value: object, *, default: int = 0) -> int:
    """Convert an untyped API value to an integer with a safe default."""
    if value is None:
        return default
    try:
        return int(str(value))
    except TypeError, ValueError:
        return default


def _coerce_float(value: object, *, default: float) -> float:
    """Convert an untyped API value to a float with a safe default."""
    if value is None:
        return default
    try:
        return float(str(value))
    except TypeError, ValueError:
        return default


class QQOfficialChunkedUploader:
    """Upload one local file with the QQ Official multipart protocol."""

    def __init__(self, http: BotHttp) -> None:
        """Initialize the uploader with qq-botpy's authenticated HTTP client.

        Args:
            http: Authenticated qq-botpy HTTP client.
        """
        self._http = http

    async def upload_c2c(
        self,
        file_path: Path,
        file_type: int,
        file_name: str,
        user_openid: str,
        srv_send_msg: bool = False,
    ) -> Media:
        """Upload a file for one C2C user.

        Args:
            file_path: Local file to upload.
            file_type: QQ media type (1=image, 2=video, 3=voice, 4=file).
            file_name: File name exposed to QQ.
            user_openid: C2C user OpenID.
            srv_send_msg: Whether QQ should send the media immediately.

        Returns:
            QQ media metadata for a subsequent message send.

        Raises:
            QQOfficialChunkedUploadError: If validation or an upload step fails.
        """
        if not user_openid:
            raise QQOfficialChunkedUploadError("user_openid is required")
        return await self._upload(
            file_path=file_path,
            file_type=file_type,
            file_name=file_name,
            srv_send_msg=srv_send_msg,
            base_path=f"/v2/users/{user_openid}",
        )

    async def upload_group(
        self,
        file_path: Path,
        file_type: int,
        file_name: str,
        group_openid: str,
        srv_send_msg: bool = False,
    ) -> Media:
        """Upload a file for one QQ group.

        Args:
            file_path: Local file to upload.
            file_type: QQ media type (1=image, 2=video, 3=voice, 4=file).
            file_name: File name exposed to QQ.
            group_openid: Group OpenID.
            srv_send_msg: Whether QQ should send the media immediately.

        Returns:
            QQ media metadata for a subsequent group message send.

        Raises:
            QQOfficialChunkedUploadError: If validation or an upload step fails.
        """
        if not group_openid:
            raise QQOfficialChunkedUploadError("group_openid is required")
        return await self._upload(
            file_path=file_path,
            file_type=file_type,
            file_name=file_name,
            srv_send_msg=srv_send_msg,
            base_path=f"/v2/groups/{group_openid}",
        )

    async def _upload(
        self,
        file_path: Path,
        file_type: int,
        file_name: str,
        srv_send_msg: bool,
        base_path: str,
    ) -> Media:
        """Run the shared QQ chunk transfer flow for one destination path.

        Args:
            file_path: Local file to upload.
            file_type: QQ media type.
            file_name: File name exposed to QQ.
            srv_send_msg: Whether QQ should send the media immediately.
            base_path: Destination-specific C2C or group API base path.

        Returns:
            QQ media metadata for a subsequent message send.

        Raises:
            QQOfficialChunkedUploadError: If validation or an upload step fails.
        """
        if not file_path.is_file():
            raise QQOfficialChunkedUploadError(f"File does not exist: {file_path}")
        try:
            file_size = file_path.stat().st_size
            hashes = await asyncio.to_thread(_compute_file_hashes, file_path)
        except OSError as exc:
            raise QQOfficialChunkedUploadError(
                f"Failed to read file {file_path}: {exc}"
            ) from exc

        prepare_body: dict[str, Any] = {
            "file_type": file_type,
            "file_size": str(file_size),
            "file_name": file_name,
            **hashes,
        }
        logger.info(
            "[QQOfficial] Starting chunked upload: file=%s size=%d type=%d",
            file_name,
            file_size,
            file_type,
        )

        prepare_response: dict[str, Any] | None = None
        for attempt in range(_UPLOAD_API_ATTEMPTS):
            try:
                prepare_response = await self._request_json(
                    "POST", f"{base_path}/upload_prepare", prepare_body
                )
                break
            except _QQOfficialAPIError as exc:
                if exc.code == _DAILY_QUOTA_CODE:
                    raise QQOfficialChunkedUploadError(
                        "QQ daily file upload quota has been reached (40093002)"
                    ) from exc
                if (
                    exc.code == _RETRYABLE_UPLOAD_CODE
                    and attempt < _UPLOAD_API_ATTEMPTS - 1
                ):
                    await asyncio.sleep(_DEFAULT_RETRY_DELAY_SECONDS)
                    continue
                raise QQOfficialChunkedUploadError(
                    f"QQ upload_prepare failed: {exc}"
                ) from exc

        if prepare_response is None:
            raise QQOfficialChunkedUploadError("QQ upload_prepare returned no response")

        prepare = prepare_response.get("data", prepare_response)
        if not isinstance(prepare, Mapping):
            raise QQOfficialChunkedUploadError(
                f"Invalid upload_prepare response: {prepare_response!r}"
            )
        upload_id = str(prepare.get("upload_id") or "")
        parts = prepare.get("parts")
        block_size = _coerce_int(prepare.get("block_size"))
        if not upload_id or block_size <= 0 or not isinstance(parts, list) or not parts:
            raise QQOfficialChunkedUploadError(
                f"Incomplete upload_prepare response: {prepare_response!r}"
            )

        part_indexes: list[int] = []
        for part in parts:
            if not isinstance(part, Mapping):
                raise QQOfficialChunkedUploadError(f"Invalid upload part: {part!r}")
            raw_index = part.get("index") if "index" in part else part.get("part_index")
            try:
                part_index = _coerce_int(raw_index, default=-1)
                if part_index < 0:
                    raise ValueError
                part_indexes.append(part_index)
            except ValueError as exc:
                raise QQOfficialChunkedUploadError(
                    f"Invalid upload part index: {part!r}"
                ) from exc
        lowest_part_index = min(part_indexes)
        if lowest_part_index not in (0, 1):
            raise QQOfficialChunkedUploadError(
                f"Unsupported upload part index base: {lowest_part_index}"
            )

        upload_config = prepare.get("upload_config")
        if not isinstance(upload_config, Mapping):
            upload_config = {}
        try:
            concurrency = max(
                1,
                min(
                    _coerce_int(upload_config.get("concurrency"), default=1),
                    _MAX_CONCURRENCY,
                ),
            )
            retry_timeout = min(
                max(
                    _coerce_float(
                        upload_config.get("retry_timeout"),
                        default=_DEFAULT_RETRY_TIMEOUT_SECONDS,
                    ),
                    0.0,
                ),
                _MAX_RETRY_TIMEOUT_SECONDS,
            )
            retry_delay = max(
                _coerce_float(
                    upload_config.get("retry_delay"),
                    default=_DEFAULT_RETRY_DELAY_SECONDS,
                ),
                0.0,
            )
        except (TypeError, ValueError) as exc:
            raise QQOfficialChunkedUploadError(
                f"Invalid upload_config: {upload_config!r}"
            ) from exc

        session = _UploadSession(
            base_path=base_path,
            upload_id=upload_id,
            block_size=block_size,
            part_index_base=lowest_part_index,
            file_path=file_path,
            file_size=file_size,
            retry_timeout=retry_timeout,
            retry_delay=retry_delay,
            total_parts=len(parts),
        )
        logger.info("[QQOfficial] Prepared %d upload parts.", len(parts))
        semaphore = asyncio.Semaphore(concurrency)

        async def upload_part(part: object) -> None:
            async with semaphore:
                if not isinstance(part, Mapping):
                    raise QQOfficialChunkedUploadError(f"Invalid upload part: {part!r}")
                await self._upload_part(session, part)

        await asyncio.gather(*(upload_part(part) for part in parts))

        merge_body = {
            "file_type": file_type,
            "srv_send_msg": srv_send_msg,
            "file_name": file_name,
            "upload_id": upload_id,
        }
        merge_response: dict[str, Any] | None = None
        for attempt in range(_UPLOAD_API_ATTEMPTS):
            try:
                merge_response = await self._request_json(
                    "POST", f"{base_path}/files", merge_body
                )
                break
            except _QQOfficialAPIError as exc:
                if exc.code == _DAILY_QUOTA_CODE:
                    raise QQOfficialChunkedUploadError(
                        "QQ daily file upload quota has been reached (40093002)"
                    ) from exc
                if (
                    exc.code == _RETRYABLE_UPLOAD_CODE
                    and attempt < _UPLOAD_API_ATTEMPTS - 1
                ):
                    await asyncio.sleep(session.retry_delay)
                    continue
                raise QQOfficialChunkedUploadError(
                    f"QQ file merge failed: {exc}"
                ) from exc

        if merge_response is None:
            raise QQOfficialChunkedUploadError("QQ file merge returned no response")

        merge = merge_response.get("data", merge_response)
        if not isinstance(merge, Mapping):
            raise QQOfficialChunkedUploadError(
                f"Invalid file merge response: {merge_response!r}"
            )
        file_uuid = str(merge.get("file_uuid") or "")
        file_info = str(merge.get("file_info") or "")
        if not file_uuid or not file_info:
            raise QQOfficialChunkedUploadError(
                f"Incomplete file merge response: {merge_response!r}"
            )

        logger.info("[QQOfficial] Chunked upload completed: %s", file_name)
        return Media(
            file_uuid=file_uuid,
            file_info=file_info,
            ttl=int(merge.get("ttl") or 0),
        )

    async def _upload_part(
        self, session: _UploadSession, part: Mapping[str, Any]
    ) -> None:
        """Upload and acknowledge one server-indexed part from upload_prepare.

        Args:
            session: Shared upload session state.
            part: One entry from the upload_prepare parts list.

        Raises:
            QQOfficialChunkedUploadError: If the part is invalid or upload fails.
        """
        raw_index = part.get("index") if "index" in part else part.get("part_index")
        try:
            part_index = _coerce_int(raw_index, default=-1)
            part_size = _coerce_int(part.get("block_size"), default=session.block_size)
        except ValueError as exc:
            raise QQOfficialChunkedUploadError(
                f"Invalid upload part metadata: {part!r}"
            ) from exc
        if part_index < session.part_index_base or part_size <= 0:
            raise QQOfficialChunkedUploadError(
                f"Invalid upload part metadata: {part!r}"
            )

        presigned_url = str(part.get("presigned_url") or "")
        if not presigned_url:
            raise QQOfficialChunkedUploadError(
                f"Upload part is missing presigned_url: {part!r}"
            )
        offset = (part_index - session.part_index_base) * session.block_size
        length = min(part_size, session.file_size - offset)
        if length <= 0:
            raise QQOfficialChunkedUploadError(
                f"Upload part {part_index} is outside the file"
            )

        try:
            data = await asyncio.to_thread(
                _read_file_part, session.file_path, offset, length
            )
        except OSError as exc:
            raise QQOfficialChunkedUploadError(
                f"Failed to read upload part {part_index}: {exc}"
            ) from exc
        part_md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()

        await self._put_part(session, presigned_url, part_index, data)
        await self._finish_part(session, part_index, length, part_md5)

    async def _put_part(
        self,
        session: _UploadSession,
        url: str,
        part_index: int,
        data: bytes,
    ) -> None:
        """PUT one part to its presigned URL with bounded retries.

        Args:
            session: Shared upload session state.
            url: QQ-provided COS presigned URL.
            part_index: Zero-based part index.
            data: Part bytes.

        Raises:
            QQOfficialChunkedUploadError: If all PUT attempts fail.
        """
        await self._http.check_session()
        http_session = self._http._session
        if http_session is None:
            raise QQOfficialChunkedUploadError("QQ HTTP session is unavailable")

        last_error: Exception | None = None
        for attempt in range(_PART_PUT_ATTEMPTS):
            try:
                async with http_session.request(
                    "PUT",
                    url,
                    data=data,
                    headers={"Content-Length": str(len(data))},
                    timeout=aiohttp.ClientTimeout(total=_API_TIMEOUT_SECONDS),
                ) as response:
                    if 200 <= response.status < 300:
                        return
                    response_text = (await response.text(errors="replace"))[:200]
                    last_error = RuntimeError(
                        f"COS returned HTTP {response.status}: {response_text}"
                    )
            except (TimeoutError, aiohttp.ClientError, OSError) as exc:
                last_error = exc
            if attempt < _PART_PUT_ATTEMPTS - 1:
                await asyncio.sleep(session.retry_delay)

        raise QQOfficialChunkedUploadError(
            f"Failed to PUT part {part_index + 1}/{session.total_parts}: {last_error}"
        )

    async def _finish_part(
        self,
        session: _UploadSession,
        part_index: int,
        part_size: int,
        part_md5: str,
    ) -> None:
        """Acknowledge one part and retry QQ's transient BDH error.

        Args:
            session: Shared upload session state.
            part_index: Zero-based part index.
            part_size: Actual number of bytes in the part.
            part_md5: Part MD5 checksum.

        Raises:
            QQOfficialChunkedUploadError: If QQ rejects the part permanently.
        """
        body = {
            "upload_id": session.upload_id,
            "part_index": part_index,
            "block_size": str(part_size),
            "md5": part_md5,
        }
        loop = asyncio.get_running_loop()
        deadline = loop.time() + session.retry_timeout

        while True:
            try:
                await self._request_json(
                    "POST", f"{session.base_path}/upload_part_finish", body
                )
                return
            except _QQOfficialAPIError as exc:
                if exc.code == _DAILY_QUOTA_CODE:
                    raise QQOfficialChunkedUploadError(
                        "QQ daily file upload quota has been reached (40093002)"
                    ) from exc
                if exc.code != _RETRYABLE_UPLOAD_CODE or loop.time() >= deadline:
                    raise QQOfficialChunkedUploadError(
                        f"QQ upload_part_finish failed for part {part_index}: {exc}"
                    ) from exc
                await asyncio.sleep(session.retry_delay)

    async def _request_json(
        self, method: str, path: str, body: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Call QQ directly so business error codes remain available.

        qq-botpy's response handler discards the structured QQ error code. The
        multipart protocol needs that code to retry 40093001 and report the
        daily quota error 40093002 correctly.

        Args:
            method: HTTP method.
            path: Fully substituted QQ API path.
            body: JSON request body.

        Returns:
            Parsed JSON object, or an empty object for a successful empty body.

        Raises:
            _QQOfficialAPIError: If QQ returns a business or HTTP error.
            QQOfficialChunkedUploadError: If the response or transport fails.
        """
        last_error: Exception | None = None
        for attempt in range(_API_TRANSPORT_ATTEMPTS):
            try:
                await self._http.check_session()
                http_session = self._http._session
                if http_session is None:
                    raise QQOfficialChunkedUploadError("QQ HTTP session is unavailable")
                route = Route(
                    method,
                    path,
                    is_sandbox=cast(Any, self._http.is_sandbox),
                )
                async with http_session.request(
                    method,
                    route.url,
                    headers=self._http._headers,
                    json=dict(body),
                    timeout=aiohttp.ClientTimeout(total=_API_TIMEOUT_SECONDS),
                ) as response:
                    try:
                        raw: object = await response.json(content_type=None)
                    except ValueError:
                        response_text = await response.text(errors="replace")
                        if response.status < 400 and not response_text.strip():
                            return {}
                        raw = {"message": response_text[:300]}

                    if not isinstance(raw, dict):
                        raise QQOfficialChunkedUploadError(
                            f"QQ API {path} returned non-object JSON: {raw!r}"
                        )
                    raw_code = raw.get("code", raw.get("biz_code"))
                    try:
                        code: int | str | None = (
                            int(raw_code) if raw_code is not None else None
                        )
                    except TypeError, ValueError:
                        code = str(raw_code)
                    if response.status >= 400 or code not in (None, 0):
                        raise _QQOfficialAPIError(
                            code,
                            str(raw.get("message") or raw.get("msg") or "QQ API error"),
                            response.status,
                        )
                    return raw
            except _QQOfficialAPIError:
                raise
            except QQOfficialChunkedUploadError:
                raise
            except (TimeoutError, aiohttp.ClientError, OSError) as exc:
                last_error = exc
                if attempt < _API_TRANSPORT_ATTEMPTS - 1:
                    await asyncio.sleep(min(2**attempt, 8))

        raise QQOfficialChunkedUploadError(
            f"QQ API {method} {path} transport failure: {last_error}"
        )
