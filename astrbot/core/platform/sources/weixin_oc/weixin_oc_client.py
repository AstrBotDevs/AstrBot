from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import random
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import aiohttp
from Crypto.Cipher import AES

from astrbot import logger


class WeixinOCClient:
    def __init__(
        self,
        *,
        adapter_id: str,
        base_url: str,
        cdn_base_url: str,
        api_timeout_ms: int,
        token: str | None = None,
    ) -> None:
        self.adapter_id = adapter_id
        self.base_url = base_url
        self.cdn_base_url = cdn_base_url
        self.api_timeout_ms = api_timeout_ms
        self.token = token
        self._http_session: aiohttp.ClientSession | None = None

    async def ensure_http_session(self) -> None:
        if self._http_session is None or self._http_session.closed:
            timeout = aiohttp.ClientTimeout(total=self.api_timeout_ms / 1000)
            self._http_session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._http_session is not None and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None

    def _build_base_headers(self, token_required: bool = False) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": base64.b64encode(
                str(random.getrandbits(32)).encode("utf-8")
            ).decode("utf-8"),
        }
        if token_required and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _resolve_url(self, endpoint: str) -> str:
        return f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    def _build_cdn_upload_url(self, upload_param: str, file_key: str) -> str:
        return (
            f"{self.cdn_base_url}/upload?"
            f"encrypted_query_param={quote(upload_param)}&filekey={quote(file_key)}"
        )

    def _build_cdn_download_url(self, encrypted_query_param: str) -> str:
        return (
            f"{self.cdn_base_url}/download?"
            f"encrypted_query_param={quote(encrypted_query_param)}"
        )

    @staticmethod
    def aes_padded_size(size: int) -> int:
        return size + (16 - (size % 16) or 16)

    @staticmethod
    def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
        pad_len = block_size - (len(data) % block_size)
        if pad_len == 0:
            pad_len = block_size
        return data + bytes([pad_len]) * pad_len

    @staticmethod
    def pkcs7_unpad(data: bytes, block_size: int = 16) -> bytes:
        if not data:
            return data
        pad_len = data[-1]
        if pad_len <= 0 or pad_len > block_size:
            return data
        if data[-pad_len:] != bytes([pad_len]) * pad_len:
            return data
        return data[:-pad_len]

    @staticmethod
    def parse_media_aes_key(aes_key_value: str) -> bytes:
        normalized = aes_key_value.strip()
        if not normalized:
            raise ValueError("empty media aes key")
        padded = normalized + "=" * (-len(normalized) % 4)
        decoded = base64.b64decode(padded)
        if len(decoded) == 16:
            return decoded
        decoded_text = decoded.decode("ascii", errors="ignore")
        if len(decoded) == 32 and all(
            c in "0123456789abcdefABCDEF" for c in decoded_text
        ):
            return bytes.fromhex(decoded_text)
        raise ValueError("unsupported media aes key format")

    async def upload_to_cdn(
        self,
        upload_param: str,
        file_key: str,
        aes_key_hex: str,
        media_path: Path,
    ) -> str:
        raw_data = await asyncio.to_thread(media_path.read_bytes)
        logger.debug(
            "weixin_oc(%s): prepare CDN upload file=%s size=%s md5=%s filekey=%s",
            self.adapter_id,
            media_path.name,
            len(raw_data),
            hashlib.md5(raw_data).hexdigest(),
            file_key,
        )
        cipher = AES.new(bytes.fromhex(aes_key_hex), AES.MODE_ECB)
        encrypted = cipher.encrypt(self.pkcs7_pad(raw_data))
        logger.debug(
            "weixin_oc(%s): encrypt done aes_key_len=%s plain_size=%s cipher_size=%s",
            self.adapter_id,
            len(bytes.fromhex(aes_key_hex)),
            len(raw_data),
            len(encrypted),
        )

        await self.ensure_http_session()
        assert self._http_session is not None
        timeout = aiohttp.ClientTimeout(total=self.api_timeout_ms / 1000)
        cdn_url = self._build_cdn_upload_url(upload_param, file_key)

        async with self._http_session.post(
            cdn_url,
            data=encrypted,
            headers={"Content-Type": "application/octet-stream"},
            timeout=timeout,
        ) as resp:
            detail = await resp.text()
            logger.debug(
                "weixin_oc(%s): CDN upload response status=%s url=%s x-error-message=%s x-encrypted-param=%s body=%s",
                self.adapter_id,
                resp.status,
                cdn_url,
                resp.headers.get("x-error-message"),
                resp.headers.get("x-encrypted-param"),
                detail[:512],
            )
            if resp.status >= 400 and resp.status < 500:
                raise RuntimeError(
                    f"upload media to cdn failed: {resp.status} {detail}"
                )
            if resp.status != 200:
                raise RuntimeError(
                    f"upload media to cdn failed: {resp.status} {detail}"
                )
            download_param = resp.headers.get("x-encrypted-param")
            if not download_param:
                raise RuntimeError(
                    "upload media to cdn failed: missing x-encrypted-param"
                )
            return download_param

    async def download_cdn_bytes(self, encrypted_query_param: str) -> bytes:
        await self.ensure_http_session()
        assert self._http_session is not None
        timeout = aiohttp.ClientTimeout(total=self.api_timeout_ms / 1000)
        async with self._http_session.get(
            self._build_cdn_download_url(encrypted_query_param),
            timeout=timeout,
        ) as resp:
            if resp.status >= 400:
                detail = await resp.text()
                raise RuntimeError(
                    f"download media from cdn failed: {resp.status} {detail}"
                )
            return await resp.read()

    async def download_and_decrypt_media(
        self,
        encrypted_query_param: str,
        aes_key_value: str,
    ) -> bytes:
        encrypted = await self.download_cdn_bytes(encrypted_query_param)
        key = self.parse_media_aes_key(aes_key_value)
        cipher = AES.new(key, AES.MODE_ECB)
        return self.pkcs7_unpad(cipher.decrypt(encrypted))

    async def request_json(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        token_required: bool = False,
        timeout_ms: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        await self.ensure_http_session()
        assert self._http_session is not None
        req_timeout = timeout_ms if timeout_ms is not None else self.api_timeout_ms
        timeout = aiohttp.ClientTimeout(total=req_timeout / 1000)
        merged_headers = self._build_base_headers(token_required=token_required)
        if headers:
            merged_headers.update(headers)

        async with self._http_session.request(
            method,
            self._resolve_url(endpoint),
            params=params,
            json=payload,
            headers=merged_headers,
            timeout=timeout,
        ) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"{method} {endpoint} failed: {resp.status} {text}")
            if not text:
                return {}
            return cast(dict[str, Any], json.loads(text))

    async def get_typing_config(
        self,
        user_id: str,
        context_token: str,
    ) -> dict[str, Any]:
        return await self.request_json(
            "POST",
            "ilink/bot/getconfig",
            payload={
                "ilink_user_id": user_id,
                "context_token": context_token,
                "base_info": {
                    "channel_version": "astrbot",
                },
            },
            token_required=True,
            timeout_ms=self.api_timeout_ms,
        )

    async def send_typing_state(
        self,
        user_id: str,
        typing_ticket: str,
        *,
        cancel: bool,
    ) -> dict[str, Any]:
        return await self.request_json(
            "POST",
            "ilink/bot/sendtyping",
            payload={
                "ilink_user_id": user_id,
                "typing_ticket": typing_ticket,
                "status": 2 if cancel else 1,
                "base_info": {
                    "channel_version": "astrbot",
                },
            },
            token_required=True,
            timeout_ms=self.api_timeout_ms,
        )
