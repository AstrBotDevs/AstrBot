from quart import g, request
from astrbot.core.db import BaseDatabase
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

from .route import Response, Route, RouteContext
from .chat import ChatRoute
from .open_api import OpenApiRoute
class ChatWidget(Route):
    def __init__(
            self,
            context: RouteContext,
            db: BaseDatabase,
            core_lifecycle: AstrBotCoreLifecycle,
            chat_route: ChatRoute,
            open_api: OpenApiRoute,
    ) -> None:
        super().__init__(context)
        self.db = db
        self.core_lifecycle = core_lifecycle
        self.chat_route = chat_route
        self.open_api = open_api
        self.routes = {
            "/widget/send": ("POST", self.send),
            "/widget/history": ("POST", self.history),
            "/widget/file": ("GET", self.file_get),
            "/widget/filename": ("GET", self.filename_get),
            "/widget/upload": ("POST", self.file_upload),
            "/widget/stop": ("POST", self.stop),
        }
        self.register_routes()

    async def send(self):
        post_data = await request.get_json(silent=True) or {}
        api_package = g.api_package
        api_package['message'] = post_data.get("message")
        api_package['enable_streaming'] = post_data.get("enable_streaming", True)
        return await self.open_api.chat_send(api_package)

    async def history(self):
        api_package = g.api_package
        if not api_package.get('session_id'):
            return Response().error("Missing key: session_id").__dict__
        return await self.chat_route.get_session(api_package['session_id'])

    async def file_upload(self):
        api_package = g.api_package
        if api_package.get('file_upload'):
            return await self.chat_route.post_file()
        else:
            return Response().error("attachment not enabled").__dict__

    async def file_get(self):
        api_package = g.api_package
        if api_package.get('file_upload'):
            return await self.chat_route.get_attachment()
        else:
            return Response().error("attachment not enabled").__dict__

    async def filename_get(self):
        api_package = g.api_package
        if api_package.get('file_upload'):
            return await self.chat_route.get_file()
        else:
            return Response().error("attachment not enabled").__dict__

    async def stop(self):
        api_package = g.api_package
        print(g.username)
        return await self.chat_route.stop_session(api_package)
