from __future__ import annotations

from astrbot.core.db import BaseDatabase
from astrbot.core.utils.datetime_utils import to_utc_isoformat


class ChatUIProjectServiceError(Exception):
    pass


class ChatUIProjectService:
    def __init__(self, db: BaseDatabase) -> None:
        self.db = db

    async def create_project(self, username: str, data: object) -> dict:
        payload = self._as_payload(data)
        title = payload.get("title")
        emoji = payload.get("emoji", "📁")
        description = payload.get("description")

        if not title:
            raise ChatUIProjectServiceError("Missing key: title")

        project = await self.db.create_chatui_project(
            creator=username,
            title=title,
            emoji=emoji,
            description=description,
        )
        return self._serialize_project(project)

    async def list_projects(self, username: str) -> list[dict]:
        projects = await self.db.get_chatui_projects_by_creator(creator=username)
        return [self._serialize_project(project) for project in projects]

    async def get_project(self, username: str, project_id: str | None) -> dict:
        if not project_id:
            raise ChatUIProjectServiceError("Missing key: project_id")

        project = await self._get_owned_project(username, project_id)
        return self._serialize_project(project)

    async def get_project_from_query(
        self,
        username: str,
        project_id: str | None,
    ) -> dict:
        return await self.get_project(username, project_id)

    async def update_project(self, username: str, data: object) -> None:
        payload = self._as_payload(data)
        project_id = payload.get("project_id")
        if not project_id:
            raise ChatUIProjectServiceError("Missing key: project_id")

        await self._get_owned_project(username, project_id)
        await self.db.update_chatui_project(
            project_id=project_id,
            title=payload.get("title"),
            emoji=payload.get("emoji"),
            description=payload.get("description"),
        )

    async def delete_project(self, username: str, project_id: str | None) -> None:
        if not project_id:
            raise ChatUIProjectServiceError("Missing key: project_id")

        await self._get_owned_project(username, project_id)
        await self.db.delete_chatui_project(project_id)

    async def delete_project_from_query(
        self,
        username: str,
        project_id: str | None,
    ) -> None:
        await self.delete_project(username, project_id)

    async def add_session_to_project(self, username: str, data: object) -> None:
        payload = self._as_payload(data)
        session_id = payload.get("session_id")
        project_id = payload.get("project_id")

        if not session_id:
            raise ChatUIProjectServiceError("Missing key: session_id")
        if not project_id:
            raise ChatUIProjectServiceError("Missing key: project_id")

        await self._get_owned_project(username, project_id)
        await self._get_owned_session(username, session_id)
        await self.db.add_session_to_project(session_id, project_id)

    async def remove_session_from_project(self, username: str, data: object) -> None:
        payload = self._as_payload(data)
        session_id = payload.get("session_id")

        if not session_id:
            raise ChatUIProjectServiceError("Missing key: session_id")

        await self._get_owned_session(username, session_id)
        await self.db.remove_session_from_project(session_id)

    async def get_project_sessions(
        self,
        username: str,
        project_id: str | None,
    ) -> list[dict]:
        if not project_id:
            raise ChatUIProjectServiceError("Missing key: project_id")

        await self._get_owned_project(username, project_id)
        sessions = await self.db.get_project_sessions(project_id)
        return [self._serialize_session(session) for session in sessions]

    async def get_project_sessions_from_query(
        self,
        username: str,
        project_id: str | None,
    ) -> list[dict]:
        return await self.get_project_sessions(username, project_id)

    async def _get_owned_project(self, username: str, project_id: str):
        project = await self.db.get_chatui_project_by_id(project_id)
        if not project:
            raise ChatUIProjectServiceError(f"Project {project_id} not found")
        if project.creator != username:
            raise ChatUIProjectServiceError("Permission denied")
        return project

    async def _get_owned_session(self, username: str, session_id: str):
        session = await self.db.get_platform_session_by_id(session_id)
        if not session:
            raise ChatUIProjectServiceError(f"Session {session_id} not found")
        if session.creator != username:
            raise ChatUIProjectServiceError("Permission denied")
        return session

    @staticmethod
    def _serialize_project(project) -> dict:
        return {
            "project_id": project.project_id,
            "title": project.title,
            "emoji": project.emoji,
            "description": project.description,
            "created_at": to_utc_isoformat(project.created_at),
            "updated_at": to_utc_isoformat(project.updated_at),
        }

    @staticmethod
    def _serialize_session(session) -> dict:
        return {
            "session_id": session.session_id,
            "platform_id": session.platform_id,
            "creator": session.creator,
            "display_name": session.display_name,
            "is_group": session.is_group,
            "created_at": to_utc_isoformat(session.created_at),
            "updated_at": to_utc_isoformat(session.updated_at),
        }

    @staticmethod
    def _as_payload(data: object) -> dict:
        return data if isinstance(data, dict) else {}
