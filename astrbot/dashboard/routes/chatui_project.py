from typing import Literal, overload

from quart import g, request

from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import ChatUIProject, PlatformSession
from astrbot.core.utils.datetime_utils import to_utc_isoformat
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
        self.db = db
        self.register_routes()

    @overload
    async def _owned_resource(
        self, kind: Literal["project"], resource_id: str | None
    ) -> tuple[ChatUIProject, None] | tuple[None, dict]: ...

    @overload
    async def _owned_resource(
        self, kind: Literal["session"], resource_id: str | None
    ) -> tuple[PlatformSession, None] | tuple[None, dict]: ...

    async def _owned_resource(self, kind: str, resource_id: str | None):
        """Use the common ownership checks while retaining legacy error envelopes."""
        if not resource_id:
            return None, Response().error(f"Missing key: {kind}_id").to_json()
        service = ChatUIProjectService(self.db)
        getter = (
            service._get_owned_project
            if kind == "project"
            else service._get_owned_session
        )
        try:
            resource = await getter(g.get("username", "guest"), resource_id)
        except ChatUIProjectServiceError as exc:
            return None, Response().error(str(exc)).to_json()
        return resource, None

    async def create_project(self):
        """Create a new ChatUI project."""
        username = g.get("username", "guest")
        post_data = await request.json

        title = post_data.get("title")
        emoji = post_data.get("emoji", "📁")
        description = post_data.get("description")

        if not title:
            return Response().error("Missing key: title").to_json()

        project = await self.db.create_chatui_project(
            creator=username,
            title=title,
            emoji=emoji,
            description=description,
        )

        return (
            Response()
            .ok(
                data={
                    "project_id": project.project_id,
                    "title": project.title,
                    "emoji": project.emoji,
                    "description": project.description,
                    "created_at": to_utc_isoformat(project.created_at),
                    "updated_at": to_utc_isoformat(project.updated_at),
                },
            )
            .to_json()
        )

    async def list_projects(self):
        """Get all ChatUI projects for the current user."""
        username = g.get("username", "guest")

        projects = await self.db.get_chatui_projects_by_creator(creator=username)

        projects_data = [
            {
                "project_id": project.project_id,
                "title": project.title,
                "emoji": project.emoji,
                "description": project.description,
                "created_at": to_utc_isoformat(project.created_at),
                "updated_at": to_utc_isoformat(project.updated_at),
            }
            for project in projects
        ]

        return Response().ok(data=projects_data).to_json()

    async def get_project(self):
        """Get a specific ChatUI project."""
        project_id = request.args.get("project_id")
        project, access_error = await self._owned_resource("project", project_id)
        if project is None:
            return access_error

        return (
            Response()
            .ok(
                data={
                    "project_id": project.project_id,
                    "title": project.title,
                    "emoji": project.emoji,
                    "description": project.description,
                    "created_at": to_utc_isoformat(project.created_at),
                    "updated_at": to_utc_isoformat(project.updated_at),
                },
            )
            .to_json()
        )

    async def update_chatui_project(self):
        """Update a ChatUI project."""
        post_data = await request.json

        project_id = post_data.get("project_id")
        title = post_data.get("title")
        emoji = post_data.get("emoji")
        description = post_data.get("description")

        _, access_error = await self._owned_resource("project", project_id)
        if access_error is not None:
            return access_error

        await self.db.update_chatui_project(
            project_id=project_id,
            title=title,
            emoji=emoji,
            description=description,
        )

        return Response().ok().to_json()

    async def delete_project(self):
        """Delete a ChatUI project."""
        project_id = request.args.get("project_id", "")
        _, access_error = await self._owned_resource("project", project_id)
        if access_error is not None:
            return access_error

        await self.db.delete_chatui_project(project_id)

        return Response().ok().to_json()

    async def add_session_to_project(self):
        """Add a session to a project."""
        post_data = await request.json

        session_id = post_data.get("session_id")
        project_id = post_data.get("project_id")

        if not session_id:
            return Response().error("Missing key: session_id").to_json()
        _, access_error = await self._owned_resource("project", project_id)
        if access_error is not None:
            return access_error

        # Verify session ownership
        _, access_error = await self._owned_resource("session", session_id)
        if access_error is not None:
            return access_error

        await self.db.add_session_to_project(session_id, project_id)

        return Response().ok().to_json()

    async def remove_session_from_project(self):
        """Remove a session from its project."""
        post_data = await request.json

        session_id = post_data.get("session_id")

        _, access_error = await self._owned_resource("session", session_id)
        if access_error is not None:
            return access_error

        await self.db.remove_session_from_project(session_id)

        return Response().ok().to_json()

    async def get_project_sessions(self):
        """Get all sessions in a project."""
        project_id = request.args.get("project_id", "")
        _, access_error = await self._owned_resource("project", project_id)
        if access_error is not None:
            return access_error

        sessions = await self.db.get_project_sessions(project_id)

        sessions_data = [
            {
                "session_id": session.session_id,
                "platform_id": session.platform_id,
                "creator": session.creator,
                "display_name": session.display_name,
                "is_group": session.is_group,
                "created_at": to_utc_isoformat(session.created_at),
                "updated_at": to_utc_isoformat(session.updated_at),
            }
            for session in sessions
        ]

        return Response().ok(data=sessions_data).to_json()
