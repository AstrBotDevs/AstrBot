from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import Request
from starlette.datastructures import UploadFile as StarletteUploadFile


class UploadFileAdapter:
    def __init__(self, upload_file: StarletteUploadFile) -> None:
        self._upload_file = upload_file
        self.filename = upload_file.filename
        self.content_type = upload_file.content_type
        self.headers = upload_file.headers
        self.content_length = self._resolve_content_length()

    def _resolve_content_length(self) -> int | None:
        try:
            raw = self.headers.get("content-length")
            return int(raw) if raw else None
        except (TypeError, ValueError):
            return None

    async def save(self, destination: str | Path) -> None:
        path = Path(destination)
        try:
            await self._upload_file.seek(0)
        except Exception:
            pass
        with path.open("wb") as output:
            while True:
                chunk = await self._upload_file.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)


class MultiDict:
    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        self._pairs = pairs

    def get(self, key: str, default: Any = None, type: Callable | None = None):
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

    def getlist(self, key: str) -> list[Any]:
        return [item_value for item_key, item_value in self._pairs if item_key == key]

    def keys(self):
        return dict.fromkeys(item_key for item_key, _ in self._pairs).keys()

    def values(self):
        return [self[key] for key in self.keys()]

    def __contains__(self, key: str) -> bool:
        return any(item_key == key for item_key, _ in self._pairs)

    def __getitem__(self, key: str):
        value = self.get(key)
        if value is None and key not in self:
            raise KeyError(key)
        return value

    def __bool__(self) -> bool:
        return bool(self._pairs)


async def multipart_parts(
    request: Request,
    *,
    extra_form: dict[str, Any] | None = None,
) -> tuple[MultiDict, MultiDict]:
    form = await request.form()
    form_pairs: list[tuple[str, Any]] = []
    file_pairs: list[tuple[str, Any]] = []
    for key, value in form.multi_items():
        if isinstance(value, StarletteUploadFile):
            file_pairs.append((key, UploadFileAdapter(value)))
        else:
            form_pairs.append((key, value))
    form_data = MultiDict(form_pairs)
    for key, value in (extra_form or {}).items():
        if value is not None and key not in form_data:
            form_pairs.append((key, value))
    return MultiDict(form_pairs), MultiDict(file_pairs)


async def single_upload(
    request: Request,
    *,
    field_name: str = "file",
) -> UploadFileAdapter | None:
    _, files = await multipart_parts(request)
    upload = files.get(field_name)
    if isinstance(upload, UploadFileAdapter):
        return upload
    return None
