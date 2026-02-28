"""Tool image cache module for storing and retrieving images returned by tools.

This module allows LLM to review images before deciding whether to send them to users.
"""
from astrbot.core.lang import t

import base64
import os
import time
from dataclasses import dataclass, field
from typing import ClassVar

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


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
    created_at: float = field(default_factory=time.time)
    """Timestamp when the image was cached."""


class ToolImageCache:
    """Manages cached images from tool calls.

    Images are stored in data/temp/tool_images/ and can be retrieved by file path.
    """

    _instance: ClassVar["ToolImageCache | None"] = None
    CACHE_DIR_NAME: ClassVar[str] = "tool_images"
    # Cache expiry time in seconds (1 hour)
    CACHE_EXPIRY: ClassVar[int] = 3600

    def __new__(cls) -> "ToolImageCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._cache_dir = os.path.join(get_astrbot_temp_path(), self.CACHE_DIR_NAME)
        os.makedirs(self._cache_dir, exist_ok=True)
        logger.debug(t("msg-45da4af7", res=self._cache_dir))

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
        file_name = f"{tool_call_id}_{index}{ext}"
        file_path = os.path.join(self._cache_dir, file_name)

        # Decode and save the image
        try:
            image_bytes = base64.b64decode(base64_data)
            with open(file_path, "wb") as f:
                f.write(image_bytes)
            logger.debug(t("msg-017bde96", file_path=file_path))
        except Exception as e:
            logger.error(t("msg-29398f55", e=e))
            raise

        return CachedImage(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            file_path=file_path,
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
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            base64_data = base64.b64encode(image_bytes).decode("utf-8")
            return base64_data, mime_type
        except Exception as e:
            logger.error(t("msg-128aa08a", file_path=file_path, e=e))
            return None

    def cleanup_expired(self) -> int:
        """Clean up expired cached images.

        Returns:
            Number of images cleaned up.
        """
        now = time.time()
        cleaned = 0

        try:
            for file_name in os.listdir(self._cache_dir):
                file_path = os.path.join(self._cache_dir, file_name)
                if os.path.isfile(file_path):
                    file_age = now - os.path.getmtime(file_path)
                    if file_age > self.CACHE_EXPIRY:
                        os.remove(file_path)
                        cleaned += 1
        except Exception as e:
            logger.warning(t("msg-3c111d1f", e=e))

        if cleaned:
            logger.info(t("msg-eeb1b849", cleaned=cleaned))

        return cleaned


# Global singleton instance
tool_image_cache = ToolImageCache()
