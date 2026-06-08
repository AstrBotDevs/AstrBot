from astrbot.dashboard.fastapi_compat import abort, send_file
from astrbot.dashboard.services.file_service import FileService, FileServiceError

from .route import Route, RouteContext


class FileRoute(Route):
    def __init__(
        self,
        context: RouteContext,
    ) -> None:
        super().__init__(context)
        self.service = FileService()
        self.routes = {
            "/file/<file_token>": ("GET", self.serve_file),
        }
        self.register_routes()

    async def serve_file(self, file_token: str):
        try:
            file_path = await self.service.resolve_token_file(file_token)
            return await send_file(file_path)
        except FileServiceError:
            return abort(404)
