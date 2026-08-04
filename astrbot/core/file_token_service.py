"""Runtime-owned file download tokens and temporary artifact leases."""

import asyncio
import os
import time
import uuid
from collections.abc import MutableMapping
from typing import Any


class FileTokenService:
    """Issue short-lived file tokens without taking ownership by default.

    ``register_file`` is a non-owning API for caller-managed files.  Pipeline
    generated artifacts use ``register_owned_file`` and transfer ownership from
    the originating event; those files are deleted only after the response is
    fully sent, on token expiry, or during service shutdown.
    """

    def __init__(self, default_timeout: float = 300) -> None:
        self.lock = asyncio.Lock()
        self.staged_files: MutableMapping[str, tuple[str, float]] = {}
        self._owned_tokens: dict[str, str] = {}
        self._claimed_owned_tokens: dict[str, str] = {}
        self._owned_artifacts: dict[str, int] = {}
        self.default_timeout = default_timeout

    @staticmethod
    def _local_path(file_path: str) -> str:
        try:
            from astrbot.core.utils.media_utils import file_uri_to_path, is_file_uri

            return file_uri_to_path(file_path) if is_file_uri(file_path) else file_path
        except Exception:
            return file_path

    async def _cleanup_expired_tokens(self) -> None:
        now = time.time()
        expired = [
            token for token, (_, expire) in self.staged_files.items() if expire < now
        ]
        for token in expired:
            self.staged_files.pop(token, None)
            owned_path = self._owned_tokens.pop(token, None)
            if owned_path is not None:
                self._release_owned_path(owned_path)

    def _release_owned_path(self, file_path: str) -> None:
        count = self._owned_artifacts.get(file_path, 0)
        if count <= 1:
            self._owned_artifacts.pop(file_path, None)
            try:
                os.remove(file_path)
            except FileNotFoundError:
                pass
            except OSError:
                # Cleanup is best effort; the next lifecycle shutdown may retry.
                pass
        else:
            self._owned_artifacts[file_path] = count - 1

    async def check_token_expired(self, file_token: str) -> bool:
        async with self.lock:
            await self._cleanup_expired_tokens()
            return file_token not in self.staged_files

    async def _register(
        self,
        file_path: str,
        ttl_seconds: float | None,
        *,
        owned_path: str | None = None,
    ) -> str:
        async with self.lock:
            await self._cleanup_expired_tokens()
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")

            file_token = str(uuid.uuid4())
            expire_time = time.time() + (
                ttl_seconds if ttl_seconds is not None else self.default_timeout
            )
            self.staged_files[file_token] = (file_path, expire_time)
            if owned_path is not None:
                self._owned_tokens[file_token] = owned_path
                self._owned_artifacts[owned_path] = (
                    self._owned_artifacts.get(owned_path, 0) + 1
                )
            return file_token

    async def register_file(
        self, file_path: str, ttl_seconds: float | None = None
    ) -> str:
        """Register a caller-managed file without deleting it later."""
        local_path = self._local_path(file_path)
        return await self._register(local_path, ttl_seconds)

    async def register_owned_file(
        self,
        file_path: str,
        event: Any,
        ttl_seconds: float | None = None,
    ) -> str:
        """Transfer an event-owned temporary artifact to a download token.

        The event must explicitly expose the tracked path and a transfer method;
        arbitrary paths cannot be registered as service-owned artifacts.
        """
        local_path = self._local_path(file_path)
        has_file = getattr(event, "has_temporary_local_file", None)
        transfer = getattr(event, "transfer_temporary_local_file", None)
        if not callable(has_file) or not callable(transfer) or not has_file(file_path):
            raise ValueError("File is not an event-owned temporary artifact")

        async with self.lock:
            await self._cleanup_expired_tokens()
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"文件不存在: {local_path}")
            token = str(uuid.uuid4())
            expire_time = time.time() + (
                ttl_seconds if ttl_seconds is not None else self.default_timeout
            )
            if not transfer(file_path):
                raise ValueError("File ownership transfer was rejected")
            self.staged_files[token] = (local_path, expire_time)
            self._owned_tokens[token] = local_path
            self._owned_artifacts[local_path] = (
                self._owned_artifacts.get(local_path, 0) + 1
            )
            return token

    async def claim_file(self, file_token: str) -> tuple[str, bool]:
        """Consume a token and return its path plus its ownership status."""
        async with self.lock:
            await self._cleanup_expired_tokens()
            if file_token not in self.staged_files:
                raise KeyError(f"无效或过期的文件 token: {file_token}")

            file_path, _ = self.staged_files.pop(file_token)
            owned_path = self._owned_tokens.pop(file_token, None)
            if not os.path.exists(file_path):
                if owned_path is not None:
                    self._release_owned_path(owned_path)
                raise FileNotFoundError(f"文件不存在: {file_path}")
            if owned_path is not None:
                self._claimed_owned_tokens[file_token] = owned_path
            return file_path, owned_path is not None

    async def release_token(self, file_token: str) -> None:
        """Release a claimed owned artifact after its response completes."""
        async with self.lock:
            owned_path = self._claimed_owned_tokens.pop(file_token, None)
            if owned_path is not None:
                self._release_owned_path(owned_path)

    async def handle_file(self, file_token: str) -> str:
        """Consume a token and return its file path.

        This compatibility-neutral non-owning API leaves caller-managed files
        untouched.  Download routes that need artifact cleanup should use
        ``claim_file`` and attach ``release_token`` to the response background.
        """
        file_path, _owned = await self.claim_file(file_token)
        return file_path

    async def shutdown(self) -> None:
        """Delete all remaining service-owned artifacts during runtime teardown."""
        async with self.lock:
            owned_paths = list(self._owned_artifacts)
            self.staged_files.clear()
            self._owned_tokens.clear()
            self._claimed_owned_tokens.clear()
            self._owned_artifacts.clear()
            for file_path in owned_paths:
                try:
                    os.remove(file_path)
                except FileNotFoundError, OSError:
                    pass
