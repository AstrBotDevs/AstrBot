"""Tool image cache module for storing and retrieving images returned by tools.

This module allows LLM to review images before deciding whether to send them to users.
"""

import base64
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from astrbot import logger


@dataclass
class CachedImage:
    """Represents a cached image from a tool call."""

    tool_call_id: str
    """The tool call ID that produced this image."""
    tool_name: str
    """The name of the tool that produced this image."""
    file_path: str
    """The file path where the image is stored."""
    mime_type: str
    """The MIME type of the image."""


class ToolImageCache:
    """Manages cached images from tool calls.

    Images are stored in an explicit runtime-owned directory and can be retrieved
    by file path.
    """

    CACHE_DIR_NAME: ClassVar[str] = "tool_images"
    _SAFE_ID_RE: ClassVar[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]+")

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_tool_call_id(self, tool_call_id: str) -> str:
        sanitized = self._SAFE_ID_RE.sub("_", tool_call_id.strip())
        return sanitized or "tool_call"

    def _resolve_cache_path(self, file_name: str) -> Path:
        cache_root = self._cache_dir.resolve(strict=False)
        file_path = (self._cache_dir / file_name).resolve(strict=False)
        try:
            file_path.relative_to(cache_root)
        except ValueError as exc:
            raise ValueError(
                "Resolved cache path escapes tool image cache directory."
            ) from exc
        return file_path

    def _get_file_extension(self, mime_type: str) -> str:
        """Get file extension from MIME type."""
        mime_to_ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
            "image/svg+xml": ".svg",
        }
        return mime_to_ext.get(mime_type.lower(), ".png")

    def save_image(
        self,
        base64_data: str,
        tool_call_id: str,
        tool_name: str,
        index: int = 0,
        mime_type: str = "image/png",
    ) -> CachedImage:
        """Save an image to cache and return the cached image info.

        Args:
            base64_data: Base64 encoded image data.
            tool_call_id: The tool call ID that produced this image.
            tool_name: The name of the tool that produced this image.
            index: The index of the image (for multiple images from same tool call).
            mime_type: The MIME type of the image.

        Returns:
            CachedImage object with file path.
        """
        ext = self._get_file_extension(mime_type)
        safe_tool_call_id = self._sanitize_tool_call_id(tool_call_id)
        file_name = f"{safe_tool_call_id}_{index}{ext}"
        file_path = self._resolve_cache_path(file_name)

        # Decode before creating a target file. StorageCleaner can remove an
        # empty cache directory at any point, so the write retries directory
        # creation once and publishes only an atomically replaced final file.
        try:
            image_bytes = base64.b64decode(base64_data)
            for attempt in range(2):
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                temp_path = self._resolve_cache_path(
                    f".{file_name}.{uuid.uuid4().hex}.tmp"
                )
                try:
                    with temp_path.open("xb") as file:
                        file.write(image_bytes)
                        file.flush()
                        os.fsync(file.fileno())
                    os.replace(temp_path, file_path)
                    break
                except FileNotFoundError:
                    temp_path.unlink(missing_ok=True)
                    if attempt:
                        raise
                except BaseException:
                    temp_path.unlink(missing_ok=True)
                    raise
            logger.debug(f"Saved tool image to: {file_path}")
        except Exception as e:
            logger.error(f"Failed to save tool image: {e}")
            raise

        return CachedImage(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            file_path=str(file_path),
            mime_type=mime_type,
        )

    def get_image_base64_by_path(
        self, file_path: str, mime_type: str = "image/png"
    ) -> tuple[str, str] | None:
        """Read an image file and return its base64 encoded data.

        Args:
            file_path: The file path of the cached image.
            mime_type: The MIME type of the image.

        Returns:
            Tuple of (base64_data, mime_type) if found, None otherwise.
        """
        cache_root = self._cache_dir.resolve(strict=False)
        resolved_path = Path(file_path).resolve(strict=False)
        try:
            resolved_path.relative_to(cache_root)
        except ValueError:
            logger.warning("Rejected read outside tool image cache: %s", file_path)
            return None

        if not resolved_path.exists():
            return None

        try:
            with resolved_path.open("rb") as f:
                image_bytes = f.read()
            base64_data = base64.b64encode(image_bytes).decode("utf-8")
            return base64_data, mime_type
        except Exception as e:
            logger.error(f"Failed to read cached image {file_path}: {e}")
            return None
