from fastapi import HTTPException
from fastapi.responses import FileResponse

from astrbot import logger
from astrbot.core import file_token_service

from .route import Route, RouteContext


class FileRoute(Route):
    def __init__(
        self,
        context: RouteContext,
    ) -> None:
        super().__init__(context)
        # Register route with path parameter
        self.app.add_api_route(
            "/api/file/{file_token}", self.serve_file, methods=["GET"]
        )

    async def serve_file(self, file_token: str):
        try:
            file_path = await file_token_service.handle_file(file_token)
            return FileResponse(file_path)
        except (FileNotFoundError, KeyError) as e:
            logger.warning(str(e))
            raise HTTPException(status_code=404, detail="File not found")
