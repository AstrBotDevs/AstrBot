from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from astrbot.dashboard.services.static_file_service import StaticFileService

router = APIRouter(include_in_schema=False)
service = StaticFileService()


async def serve_index(request: Request):
    static_folder = getattr(request.app.state, "dashboard_static_folder", None)
    if not static_folder:
        raise HTTPException(status_code=404)
    return FileResponse(Path(static_folder) / "index.html")


for index_route in service.list_index_routes():
    router.add_api_route(index_route, serve_index, methods=["GET"])
