from astrbot.core.db import BaseDatabase
from astrbot.dashboard.fastapi_compat import g, request
from astrbot.dashboard.services.chatui_project_service import (
    ChatUIProjectService,
    ChatUIProjectServiceError,
)

from .route import Response, Route, RouteContext


class ChatUIProjectRoute(Route):
    def __init__(self, context: RouteContext, db: BaseDatabase) -> None:
        super().__init__(context)
        self.routes = {
            "/chatui_project/create": ("POST", self.create_project),
            "/chatui_project/list": ("GET", self.list_projects),
            "/chatui_project/get": ("GET", self.get_project),
            "/chatui_project/update": ("POST", self.update_chatui_project),
            "/chatui_project/delete": ("GET", self.delete_project),
            "/chatui_project/add_session": ("POST", self.add_session_to_project),
            "/chatui_project/remove_session": (
                "POST",
                self.remove_session_from_project,
            ),
            "/chatui_project/get_sessions": ("GET", self.get_project_sessions),
        }
        self.service = ChatUIProjectService(db)
        self.register_routes()

    @staticmethod
    def _username() -> str:
        return g.get("username", "guest")

    @staticmethod
    def _service_error(exc: ChatUIProjectServiceError):
        return Response().error(str(exc)).__dict__

    @staticmethod
    def _ok(data=None):
        return Response().ok(data=data).__dict__

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            return self._ok(result)
        except ChatUIProjectServiceError as exc:
            return self._service_error(exc)

    async def _run_json(self, operation):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke)

    async def create_project(self):
        """Create a new ChatUI project."""
        return await self._run_json(
            lambda data: self.service.create_project(self._username(), data)
        )

    async def list_projects(self):
        """Get all ChatUI projects for the current user."""
        return await self._run(lambda: self.service.list_projects(self._username()))

    async def get_project(self):
        """Get a specific ChatUI project."""
        return await self._run(
            lambda: self.service.get_project_from_legacy_query(
                self._username(),
                request.args.get("project_id"),
            )
        )

    async def update_chatui_project(self):
        """Update a ChatUI project."""
        return await self._run_json(
            lambda data: self.service.update_project(self._username(), data)
        )

    async def delete_project(self):
        """Delete a ChatUI project."""
        return await self._run(
            lambda: self.service.delete_project_from_legacy_query(
                self._username(),
                request.args.get("project_id"),
            )
        )

    async def add_session_to_project(self):
        """Add a session to a project."""
        return await self._run_json(
            lambda data: self.service.add_session_to_project(self._username(), data)
        )

    async def remove_session_from_project(self):
        """Remove a session from its project."""
        return await self._run_json(
            lambda data: self.service.remove_session_from_project(
                self._username(),
                data,
            )
        )

    async def get_project_sessions(self):
        """Get all sessions in a project."""
        return await self._run(
            lambda: self.service.get_project_sessions_from_legacy_query(
                self._username(),
                request.args.get("project_id"),
            )
        )
