from __future__ import annotations

from typing import Any

from fastapi import Request
from starlette.datastructures import UploadFile as StarletteUploadFile

from astrbot.core.utils.web import MultiDict as BaseMultiDict
from astrbot.core.utils.web import UploadFileAdapter as BaseUploadFileAdapter


class UploadFileAdapter(BaseUploadFileAdapter):
    """Compatibility name for streamed upload handling."""


class MultiDict(BaseMultiDict[Any]):
    """Compatibility name for shared multipart request values."""


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
