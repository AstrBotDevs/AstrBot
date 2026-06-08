from astrbot.dashboard.services.static_file_service import StaticFileService

from .route import Route, RouteContext


class StaticFileRoute(Route):
    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.service = StaticFileService()

        for i in self.service.list_index_routes():
            self.app.add_url_rule(i, view_func=self.index)

        @self.app.errorhandler(404)
        async def page_not_found(e) -> str:
            return self.service.get_not_found_message()

    async def index(self):
        return await self.app.send_static_file("index.html")
