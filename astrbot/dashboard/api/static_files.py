from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from astrbot.core.desktop_runtime import is_desktop_managed_backend
from astrbot.dashboard.services.static_file_service import StaticFileService
from astrbot.dashboard.static_encoding import (
    accepts_gzip,
    gzip_static_body,
    is_compressible_media_type,
    with_gzip_headers,
)

router = APIRouter(include_in_schema=False)
service = StaticFileService()


def _static_folder(request: Request) -> str | None:
    return getattr(request.app.state, "dashboard_static_folder", None)


def _media_type(file_path: Path) -> str | None:
    guessed, _encoding = mimetypes.guess_type(file_path.name)
    return guessed


def _read_gzip_body(file_path: Path) -> bytes | None:
    return gzip_static_body(file_path.read_bytes())


async def _file_response(request: Request, file_path: Path, headers: dict[str, str]):
    """Return a static file, gzip-encoded when the client and type allow it.

    Range requests stay on FileResponse. A gzip body cannot satisfy a byte range
    of the original file. Reading and compression run off the event loop.
    """
    media_type = _media_type(file_path)
    accept_encoding = request.headers.get("accept-encoding")
    if request.headers.get("range") or not accepts_gzip(accept_encoding):
        return FileResponse(file_path, headers=headers)
    if not is_compressible_media_type(media_type):
        return FileResponse(file_path, headers=headers)

    compressed = await asyncio.to_thread(_read_gzip_body, file_path)
    if compressed is None:
        return FileResponse(file_path, headers=headers)

    content_type = media_type or "application/octet-stream"
    if content_type.startswith("text/") and "charset=" not in content_type:
        content_type += "; charset=utf-8"
    return Response(
        content=compressed,
        media_type=content_type,
        headers=with_gzip_headers(headers),
    )


def _not_found_response() -> HTMLResponse:
    return HTMLResponse(
        service.get_not_found_message(),
        status_code=404,
        headers={"Cache-Control": "no-store"},
    )


async def serve_index(request: Request):
    index_file = service.resolve_index_file(_static_folder(request))
    if index_file is None:
        return _not_found_response()
    headers = {"Cache-Control": "no-store"}
    if is_desktop_managed_backend() and request.query_params.get("astrbot_bundle"):
        # The desktop app adds a bundle-identity query whenever its packaged
        # resources change. That makes this request bypass an old URL cache
        # entry and evicts legacy subresources without clearing cookies or storage.
        headers["Clear-Site-Data"] = '"cache"'
    return await _file_response(request, index_file, headers)


async def serve_static_file(request: Request, static_path: str):
    if request.url.path.startswith("/api"):
        raise HTTPException(status_code=404)

    file_path = service.resolve_static_file(_static_folder(request), static_path)
    if file_path is None:
        return _not_found_response()

    normalized_path = static_path.replace("\\", "/").strip("/")
    is_entry_document = file_path.suffix.lower() == ".html"
    headers = {
        "Cache-Control": (
            "no-store"
            if is_entry_document or normalized_path == "assets/version"
            else "no-cache"
        )
    }
    if (
        is_entry_document
        and is_desktop_managed_backend()
        and request.query_params.get("astrbot_bundle")
    ):
        headers["Clear-Site-Data"] = '"cache"'
    return await _file_response(request, file_path, headers)


for index_route in service.list_index_routes():
    router.add_api_route(index_route, serve_index, methods=["GET"])

router.add_api_route("/{static_path:path}", serve_static_file, methods=["GET"])
