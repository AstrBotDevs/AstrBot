"""Shared request values and bounded upload adapters for HTTP entry points."""

from collections.abc import Callable, KeysView
from pathlib import Path
from typing import Any, TypeVar, overload

from starlette.datastructures import Headers
from starlette.datastructures import UploadFile as StarletteUploadFile

from astrbot.core.utils.upload import save_upload_stream

DefaultT = TypeVar("DefaultT")
ConvertedT = TypeVar("ConvertedT")


class MultiDict[ValueT]:
    """Dictionary-like request values that preserves duplicate keys."""

    def __init__(self, pairs: list[tuple[str, ValueT]]) -> None:
        self._pairs = pairs

    @overload
    def get(self, key: str) -> ValueT | None: ...

    @overload
    def get(self, key: str, default: DefaultT) -> ValueT | DefaultT: ...

    @overload
    def get(
        self,
        key: str,
        default: DefaultT,
        type: Callable[[ValueT], ConvertedT],
    ) -> ConvertedT | DefaultT: ...

    def get(self, key: str, default: Any = None, type: Callable | None = None):
        """Return the last value for a key.

        Args:
            key: Value key to read.
            default: Value returned when the key is missing or conversion fails.
            type: Optional callable used to convert the value.

        Returns:
            The matching value, converted value, or default.
        """
        for item_key, item_value in reversed(self._pairs):
            if item_key != key:
                continue
            if type is None:
                return item_value
            try:
                return type(item_value)
            except (TypeError, ValueError):
                return default
        return default

    def getlist(self, key: str) -> list[ValueT]:
        """Return all values for a key.

        Args:
            key: Value key to read.

        Returns:
            Values in request order.
        """
        return [item_value for item_key, item_value in self._pairs if item_key == key]

    def keys(self) -> KeysView[str]:
        return dict.fromkeys(item_key for item_key, _ in self._pairs).keys()

    def values(self) -> list[ValueT]:
        return [self[key] for key in self.keys()]

    def items(self) -> list[tuple[str, ValueT]]:
        return [(key, self[key]) for key in self.keys()]

    def __contains__(self, key: str) -> bool:
        return any(item_key == key for item_key, _ in self._pairs)

    def __getitem__(self, key: str) -> ValueT:
        for item_key, item_value in reversed(self._pairs):
            if item_key == key:
                return item_value
        raise KeyError(key)

    def __bool__(self) -> bool:
        return bool(self._pairs)


class UploadFileAdapter:
    """Preserve upload metadata and save streams with a size limit."""

    def __init__(self, upload_file: StarletteUploadFile) -> None:
        self._upload_file: StarletteUploadFile = upload_file
        self.filename: str | None = upload_file.filename
        self.content_type: str | None = upload_file.content_type
        self.headers: Headers = upload_file.headers
        self.content_length: int | None = self._resolve_content_length()

    def _resolve_content_length(self) -> int | None:
        try:
            raw = self.headers.get("content-length")
            return int(raw) if raw else None
        except (TypeError, ValueError):
            return None

    async def save(
        self, destination: str | Path, *, max_bytes: int | None = None
    ) -> int:
        """Save the uploaded file to disk.

        Args:
            destination: Destination file path.
            max_bytes: Optional hard limit; the partial file is removed and
                UploadTooLargeError is raised when the upload exceeds it.

        Returns:
            Number of bytes written.
        """
        return await save_upload_stream(
            self._upload_file, destination, max_bytes=max_bytes
        )
