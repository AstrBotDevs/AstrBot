from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from astrbot.core.desktop_runtime import is_desktop_managed_backend
from astrbot.dashboard.services.static_file_service import StaticFileService

router = APIRouter(include_in_schema=False)
service = StaticFileService()


def _static_folder(request: Request) -> str | None:
    return getattr(request.app.state, "dashboard_static_folder", None)


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
    return FileResponse(index_file, headers=headers)


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
    return FileResponse(file_path, headers=headers)


for index_route in service.list_index_routes():
    router.add_api_route(index_route, serve_index, methods=["GET"])

router.add_api_route("/{static_path:path}", serve_static_file, methods=["GET"])
