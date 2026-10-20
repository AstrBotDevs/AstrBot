import asyncio
import time
import uuid
from pathlib import Path


class FileTokenService:
    """Serve token-authorized file downloads with expiration and lazy cleanup."""

    def __init__(self, default_timeout: float = 300) -> None:
        self.lock = asyncio.Lock()
        self.staged_files = {}  # token: (file_path, expire_time, single_use)
        self.default_timeout = default_timeout

    async def _cleanup_expired_tokens(self) -> None:
        """Remove expired tokens."""
        now = time.time()
        expired_tokens = [
            token for token, (_, expire, _) in self.staged_files.items() if expire < now
        ]
        for token in expired_tokens:
            self.staged_files.pop(token, None)

    async def check_token_expired(self, file_token: str) -> bool:
        """Check whether a token is expired, consumed, or missing.

        Args:
            file_token: The token returned when registering a file.

        Returns:
            Whether the token is unavailable for file access.
        """
        async with self.lock:
            await self._cleanup_expired_tokens()
            return file_token not in self.staged_files

    async def register_file(
        self,
        file_path: str,
        timeout: float | None = None,
        *,
        single_use: bool = True,
    ) -> str:
        """Register a file for token-authorized access.

        Args:
            file_path: The local file path or file URI.
            timeout: The token lifetime in seconds, or the default lifetime.
            single_use: Whether to consume the token on its first file access.
                Set to False for resources that need repeated access until expiry.

        Returns:
            The token used to access the file.

        Raises:
            FileNotFoundError: If the file path does not exist.
        """
        try:
            from astrbot.core.utils.media_utils import file_uri_to_path, is_file_uri

            local_path = (
                file_uri_to_path(file_path) if is_file_uri(file_path) else file_path
            )
        except Exception:
            # Fall back to the original path if URL parsing fails.
            local_path = file_path

        async with self.lock:
            await self._cleanup_expired_tokens()

            if not Path(local_path).exists():
                raise FileNotFoundError(
                    f"File does not exist: {local_path} (original input: {file_path})",
                )

            file_token = str(uuid.uuid4())
            expire_time = time.time() + (
                timeout if timeout is not None else self.default_timeout
            )
            self.staged_files[file_token] = (local_path, expire_time, single_use)
            return file_token

    async def handle_file(self, file_token: str) -> str:
        """Resolve a file path, consuming the token only when it is single-use.

        Args:
            file_token: The token returned when registering a file.

        Returns:
            The registered local file path.

        Raises:
            KeyError: If the token is missing, consumed, or expired.
            FileNotFoundError: If the registered file has been deleted.
        """
        async with self.lock:
            await self._cleanup_expired_tokens()

            if file_token not in self.staged_files:
                raise KeyError(f"Invalid or expired file token: {file_token}")

            file_path, _, single_use = self.staged_files[file_token]
            if single_use:
                self.staged_files.pop(file_token)
            if not Path(file_path).exists():
                raise FileNotFoundError(f"File does not exist: {file_path}")
            return file_path
