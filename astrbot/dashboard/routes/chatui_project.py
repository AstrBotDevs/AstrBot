from quart import g, request

from astrbot.core.db import BaseDatabase

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

    async def create_project(self):
        """Create a new ChatUI project."""
        username = g.get("username", "guest")
        post_data = await request.json

        title = post_data.get("title")
        emoji = post_data.get("emoji", "📁")
        description = post_data.get("description")

        if not title:
            return Response().error("Missing key: title").__dict__

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
                    "created_at": project.created_at.astimezone().isoformat(),
                    "updated_at": project.updated_at.astimezone().isoformat(),
                }
            )
            .__dict__
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
                "created_at": project.created_at.astimezone().isoformat(),
                "updated_at": project.updated_at.astimezone().isoformat(),
            }
            for project in projects
        ]

        return Response().ok(data=projects_data).__dict__

    async def get_project(self):
        """Get a specific ChatUI project."""
        project_id = request.args.get("project_id")
        if not project_id:
            return Response().error("Missing key: project_id").__dict__

        username = g.get("username", "guest")

        project = await self.db.get_chatui_project_by_id(project_id)
        if not project:
            return Response().error(f"Project {project_id} not found").__dict__

        # Verify ownership
        if project.creator != username:
            return Response().error("Permission denied").__dict__

        return (
            Response()
            .ok(
                data={
                    "project_id": project.project_id,
                    "title": project.title,
                    "emoji": project.emoji,
                    "description": project.description,
                    "created_at": project.created_at.astimezone().isoformat(),
                    "updated_at": project.updated_at.astimezone().isoformat(),
                }
            )
            .__dict__
        )

    async def update_chatui_project(self):
        """Update a ChatUI project."""
        post_data = await request.json

        project_id = post_data.get("project_id")
        title = post_data.get("title")
        emoji = post_data.get("emoji")
        description = post_data.get("description")

        if not project_id:
            return Response().error("Missing key: project_id").__dict__

        username = g.get("username", "guest")

        # Verify ownership
        project = await self.db.get_chatui_project_by_id(project_id)
        if not project:
            return Response().error(f"Project {project_id} not found").__dict__
        if project.creator != username:
            return Response().error("Permission denied").__dict__

        await self.db.update_chatui_project(
            project_id=project_id,
            title=title,
            emoji=emoji,
            description=description,
        )

        return Response().ok().__dict__

    async def delete_project(self):
        """Delete a ChatUI project."""
        project_id = request.args.get("project_id")
        if not project_id:
            return Response().error("Missing key: project_id").__dict__

        username = g.get("username", "guest")

        # Verify ownership
        project = await self.db.get_chatui_project_by_id(project_id)
        if not project:
            return Response().error(f"Project {project_id} not found").__dict__
        if project.creator != username:
            return Response().error("Permission denied").__dict__

        await self.db.delete_chatui_project(project_id)

        return Response().ok().__dict__

    async def add_session_to_project(self):
        """Add a session to a project."""
        post_data = await request.json

        session_id = post_data.get("session_id")
        project_id = post_data.get("project_id")

        if not session_id:
            return Response().error("Missing key: session_id").__dict__
        if not project_id:
            return Response().error("Missing key: project_id").__dict__

        username = g.get("username", "guest")

        # Verify project ownership
        project = await self.db.get_chatui_project_by_id(project_id)
        if not project:
            return Response().error(f"Project {project_id} not found").__dict__
        if project.creator != username:
            return Response().error("Permission denied").__dict__

        # Verify session ownership
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").__dict__
        if session.creator != username:
            return Response().error("Permission denied").__dict__

        await self.db.add_session_to_project(session_id, project_id)

        return Response().ok().__dict__

    async def remove_session_from_project(self):
        """Remove a session from its project."""
        post_data = await request.json

        session_id = post_data.get("session_id")

        if not session_id:
            return Response().error("Missing key: session_id").__dict__

        username = g.get("username", "guest")

        # Verify session ownership
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            return Response().error(f"Session {session_id} not found").__dict__
        if session.creator != username:
            return Response().error("Permission denied").__dict__

        await self.db.remove_session_from_project(session_id)

        return Response().ok().__dict__

    async def get_project_sessions(self):
        """Get all sessions in a project."""
        project_id = request.args.get("project_id")
        if not project_id:
            return Response().error("Missing key: project_id").__dict__

        username = g.get("username", "guest")

        # Verify project ownership
        project = await self.db.get_chatui_project_by_id(project_id)
        if not project:
            return Response().error(f"Project {project_id} not found").__dict__
        if project.creator != username:
            return Response().error("Permission denied").__dict__

        sessions = await self.db.get_project_sessions(project_id)

        sessions_data = [
            {
                "session_id": session.session_id,
                "platform_id": session.platform_id,
                "creator": session.creator,
                "display_name": session.display_name,
                "is_group": session.is_group,
                "created_at": session.created_at.astimezone().isoformat(),
                "updated_at": session.updated_at.astimezone().isoformat(),
            }
            for session in sessions
        ]

        return Response().ok(data=sessions_data).__dict__
