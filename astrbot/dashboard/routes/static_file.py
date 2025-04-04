from .route import Route, RouteContext


class StaticFileRoute(Route):
    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)

        index_ = [
            "/",
            "/auth/login",
            "/config",
            "/logs",
            "/extension",
            "/dashboard/default",
            "/project-atri",
            "/console",
            "/chat",
            "/settings",
            "/platforms",
            "/providers",
            "/about",
            "/extension-marketplace",
            "/conversation",
            "/tool-use",
        ]
        for i in index_:
            self.app.add_url_rule(i, view_func=self.index)

        @self.app.errorhandler(404)
        async def page_not_found(e):
            return "404 Not found。如果你初次使用打开面板发现 404, 请参考文档: https://astrbot.app/faq.html。"

    async def index(self):
        return await self.app.send_static_file("index.html")
