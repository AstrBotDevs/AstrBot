from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from astrbot.dashboard.services.static_file_service import StaticFileService

router = APIRouter(include_in_schema=False)
service = StaticFileService()


def _static_folder(request: Request) -> str | None:
    return getattr(request.app.state, "dashboard_static_folder", None)


def _not_found_response() -> PlainTextResponse:
    return PlainTextResponse(service.get_not_found_message(), status_code=404)


async def serve_index(request: Request):
    index_file = service.resolve_index_file(_static_folder(request))
    if index_file is None:
        return _not_found_response()
    return FileResponse(index_file)


async def serve_static_file(request: Request, static_path: str):
    if request.url.path.startswith("/api"):
        raise HTTPException(status_code=404)

    file_path = service.resolve_static_file(_static_folder(request), static_path)
    if file_path is None:
        return _not_found_response()
    return FileResponse(file_path)


for index_route in service.list_index_routes():
    router.add_api_route(index_route, serve_index, methods=["GET"])

router.add_api_route("/{static_path:path}", serve_static_file, methods=["GET"])
