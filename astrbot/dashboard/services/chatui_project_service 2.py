from __future__ import annotations

import os

from astrbot.core.db import BaseDatabase
from astrbot.core.utils.datetime_utils import to_utc_isoformat
from astrbot.core.workspace import (
    WORKSPACE_TYPE_CUSTOM,
    WORKSPACE_TYPE_SESSION,
    normalize_project_workspace_type,
    normalize_workspace_path,
    resolve_project_workspace_root,
    workspace_path_to_root,
)


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
        workspace_type, workspace_path = self._normalize_workspace_config(payload)

        if not title:
            raise ChatUIProjectServiceError("Missing key: title")

        project = await self.db.create_chatui_project(
            creator=username,
            title=title,
            emoji=emoji,
            description=description,
            workspace_type=workspace_type,
            workspace_path=workspace_path,
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

        project = await self._get_owned_project(username, project_id)
        workspace_type = None
        workspace_path = None
        if "workspace_type" in payload or "workspace_path" in payload:
            workspace_type, workspace_path = self._normalize_workspace_config(
                payload,
                fallback_type=project.workspace_type,
                fallback_path=project.workspace_path,
            )
        await self.db.update_chatui_project(
            project_id=project_id,
            title=payload.get("title"),
            emoji=payload.get("emoji"),
            description=payload.get("description"),
            workspace_type=workspace_type,
            workspace_path=workspace_path,
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
        workspace_type = normalize_project_workspace_type(
            getattr(project, "workspace_type", WORKSPACE_TYPE_SESSION)
        )
        workspace_path = normalize_workspace_path(
            getattr(project, "workspace_path", None)
        )
        resolved_workspace_path = None
        if workspace_type != WORKSPACE_TYPE_SESSION:
            fallback_umo = f"webchat:FriendMessage:webchat!{project.creator}!default"
            try:
                resolved_workspace_path = str(
                    resolve_project_workspace_root(
                        project,
                        fallback_umo=fallback_umo,
                    )
                )
            except ValueError:
                resolved_workspace_path = None
        return {
            "project_id": project.project_id,
            "title": project.title,
            "emoji": project.emoji,
            "description": project.description,
            "workspace_type": workspace_type,
            "workspace_path": workspace_path,
            "resolved_workspace_path": resolved_workspace_path,
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

    @staticmethod
    def _normalize_workspace_config(
        payload: dict,
        *,
        fallback_type: str | None = None,
        fallback_path: str | None = None,
    ) -> tuple[str, str | None]:
        """Normalize project workspace config from request payload.

        Args:
            payload: Request payload.
            fallback_type: Existing workspace type used when omitted.
            fallback_path: Existing workspace path used when omitted.

        Returns:
            Normalized workspace type and path.

        Raises:
            ChatUIProjectServiceError: If a custom workspace has no usable path.
        """
        workspace_type = normalize_project_workspace_type(
            payload.get("workspace_type", fallback_type or WORKSPACE_TYPE_SESSION)
        )
        raw_path = payload.get("workspace_path", fallback_path)
        workspace_path = normalize_workspace_path(raw_path)
        if workspace_type != WORKSPACE_TYPE_CUSTOM:
            workspace_path = None
            return workspace_type, workspace_path

        if not workspace_path:
            raise ChatUIProjectServiceError("Custom workspace requires a path")

        try:
            workspace_root = workspace_path_to_root(workspace_path)
        except ValueError as exc:
            raise ChatUIProjectServiceError(str(exc)) from exc
        if not workspace_root.exists():
            raise ChatUIProjectServiceError("Custom workspace path does not exist")
        if not workspace_root.is_dir():
            raise ChatUIProjectServiceError("Custom workspace path must be a directory")
        if not os.access(workspace_root, os.R_OK | os.W_OK | os.X_OK):
            raise ChatUIProjectServiceError(
                "Custom workspace path requires read, write, and enter permissions"
            )
        return workspace_type, workspace_path
