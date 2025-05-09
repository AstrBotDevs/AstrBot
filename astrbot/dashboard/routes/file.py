from .route import Route, RouteContext
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle


class FileRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/file/<file_token>": ("GET", self.serve_file),
        }
        self.register_routes()

    async def serve_file(file_token: str):
        try:
            file_path = await service.get_file_path(file_token)
            return await send_file(file_path)
        except FileNotFoundError as e:
            logger.warning(str(e))
            return abort(404)
        except KeyError as e:
            logger.warning(str(e))
            return abort(404)