from .route import Route, RouteContext
from astrbot import logger
from quart import abort, send_file
from astrbot.core import file_token_service


class FileRoute(Route):
    def __init__(
        self,
        context: RouteContext,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/file/<file_token>": ("GET", self.serve_file),
        }
        self.register_routes()

    async def serve_file(self, file_token: str):
        try:
            file_path = await file_token_service.handle_file(file_token)
            return await send_file(file_path)
        except (FileNotFoundError, KeyError) as e:
            logger.warning(str(e))
            return abort(404)
