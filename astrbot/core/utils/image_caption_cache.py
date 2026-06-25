from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from astrbot.core import logger

DEFAULT_IMAGE_CAPTION_CACHE_TTL = 600


def resolve_image_caption_cache_ttl(config: dict | None) -> int:
    raw = (config or {}).get(
        "image_caption_cache_ttl",
        DEFAULT_IMAGE_CAPTION_CACHE_TTL,
    )
    if isinstance(raw, bool):
        return DEFAULT_IMAGE_CAPTION_CACHE_TTL
    try:
        return max(int(raw), 0)
    except (TypeError, ValueError):
        return DEFAULT_IMAGE_CAPTION_CACHE_TTL


@dataclass(slots=True)
class _ImageCaptionCacheEntry:
    caption: str
    expires_at: float


class ImageCaptionCache:
    def __init__(self) -> None:
        self._entries: dict[str, _ImageCaptionCacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def clear(self) -> None:
        self._entries.clear()
        self._locks.clear()

    async def get_or_create(
        self,
        *,
        provider_id: str,
        prompt: str,
        image_urls: list[str],
        ttl_seconds: int,
        caption_factory: Callable[[], Awaitable[str]],
    ) -> str:
        if ttl_seconds <= 0:
            return await caption_factory()

        cache_key = await self._build_cache_key(
            provider_id=provider_id,
            prompt=prompt,
            image_urls=image_urls,
        )
        cached_caption = self._get(cache_key)
        if cached_caption is not None:
            logger.debug(
                "Using cached image caption. provider=%s",
                provider_id or "<default>",
            )
            return cached_caption

        lock = self._get_lock(cache_key)
        async with lock:
            cached_caption = self._get(cache_key)
            if cached_caption is not None:
                logger.debug(
                    "Using cached image caption after lock wait. provider=%s",
                    provider_id or "<default>",
                )
                return cached_caption

        try:
            caption = await caption_factory()
            self._entries[cache_key] = _ImageCaptionCacheEntry(
                caption=caption,
                expires_at=time.monotonic() + ttl_seconds,
            )
            self._cleanup_expired_entries()
            return caption
        finally:
            self._locks.pop(cache_key, None)

    def _get(self, cache_key: str) -> str | None:
        entry = self._entries.get(cache_key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            self._entries.pop(cache_key, None)
            return None
        return entry.caption

    def _cleanup_expired_entries(self) -> None:
        now = time.monotonic()
        expired_keys = [
            key for key, entry in self._entries.items() if entry.expires_at <= now
        ]
        for key in expired_keys:
            self._entries.pop(key, None)
            self._locks.pop(key, None)

    def _get_lock(self, cache_key: str) -> asyncio.Lock:
        lock = self._locks.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[cache_key] = lock
        return lock

    async def _build_cache_key(
        self,
        *,
        provider_id: str,
        prompt: str,
        image_urls: list[str],
    ) -> str:
        image_fingerprints = []
        for image_url in image_urls:
            image_fingerprints.append(await self._fingerprint_image(image_url))

        joined = "\n".join([provider_id, prompt, *image_fingerprints])
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    async def _fingerprint_image(self, image_url: str) -> str:
        if image_url.startswith("base64://"):
            return self._fingerprint_base64_image(image_url)

        if image_url.startswith("data:image"):
            return self._fingerprint_data_uri_image(image_url)

        if image_url.startswith(("http://", "https://")):
            return self._fingerprint_remote_image(image_url)

        return await self._fingerprint_local_image(image_url)

    def _fingerprint_base64_image(self, image_url: str) -> str:
        raw_base64 = image_url.removeprefix("base64://")
        try:
            image_bytes = base64.b64decode(raw_base64)
        except Exception:
            return self._reference_fingerprint(image_url)
        return self._hash_bytes(image_bytes)

    def _fingerprint_data_uri_image(self, image_url: str) -> str:
        try:
            _, encoded = image_url.split(",", 1)
            image_bytes = base64.b64decode(encoded)
        except Exception:
            return self._reference_fingerprint(image_url)
        return self._hash_bytes(image_bytes)

    def _fingerprint_remote_image(self, image_url: str) -> str:
        return f"url:{image_url}"

    async def _fingerprint_local_image(self, image_url: str) -> str:
        local_path = self._to_local_path(image_url)
        if local_path and local_path.is_file():
            image_bytes = await asyncio.to_thread(local_path.read_bytes)
            return self._hash_bytes(image_bytes)

        return self._reference_fingerprint(image_url)

    def _to_local_path(self, image_url: str) -> Path | None:
        if image_url.startswith("file://"):
            parsed = urlparse(image_url)
            parsed_path = unquote(parsed.path)
            if (
                parsed_path.startswith("/")
                and len(parsed_path) >= 3
                and parsed_path[2] == ":"
            ):
                parsed_path = parsed_path[1:]
            return Path(parsed_path)

        if image_url.startswith(("http://", "https://", "base64://", "data:image")):
            return None

        return Path(image_url)

    def _hash_bytes(self, payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def _reference_fingerprint(self, image_url: str) -> str:
        return f"ref:{image_url}"


image_caption_cache = ImageCaptionCache()
