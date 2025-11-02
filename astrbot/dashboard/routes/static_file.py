import os

from fastapi import HTTPException
from fastapi.responses import FileResponse

from .route import Route, RouteContext


class StaticFileRoute(Route):
    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)

        # In FastAPI, static files are handled differently
        # We register routes for SPA (Single Page Application) paths
        # These should all serve index.html for client-side routing
        index_routes = [
            "/",
            "/auth/login",
            "/config",
            "/logs",
            "/extension",
            "/dashboard/default",
            "/alkaid",
            "/alkaid/knowledge-base",
            "/alkaid/long-term-memory",
            "/alkaid/other",
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

        # Register each route to serve index.html
        for route_path in index_routes:
            self.app.add_api_route(route_path, self.index, methods=["GET"])

        # Add 404 handler using FastAPI exception handler
        @self.app.exception_handler(404)
        async def page_not_found(request, exc):
            return {
                "detail": "404 Not found。如果你初次使用打开面板发现 404, 请参考文档: https://astrbot.app/faq.html。如果你正在测试回调地址可达性，显示这段文字说明测试成功了。"
            }

    async def index(self):
        """Serve the index.html file for SPA routing."""
        # Get the static folder from the app
        # The static files are mounted in server.py
        # We need to return the index.html from the static directory
        try:
            # The static folder path should be available from the app
            static_folder = getattr(self.app, "_static_folder", None)
            if static_folder:
                index_path = os.path.join(static_folder, "index.html")
                if os.path.exists(index_path):
                    return FileResponse(index_path)

            # Fallback: try to find index.html in common locations
            possible_paths = [
                "data/dist/index.html",
                "dashboard/dist/index.html",
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    return FileResponse(path)

            raise HTTPException(status_code=404, detail="index.html not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
