from __future__ import annotations

import os
from pathlib import Path

from astrbot.core.db import BaseDatabase
from astrbot.core.utils.datetime_utils import to_utc_isoformat
from astrbot.core.workspace import (
    API_KEY_USERNAME_PREFIX,
    WORKSPACE_TYPE_CUSTOM,
    WORKSPACE_TYPE_PROJECT,
    WORKSPACE_TYPE_SESSION,
    normalize_project_workspace_type,
    normalize_workspace_path,
    resolve_project_workspace_root,
    workspace_path_to_root,
)

_WORKSPACE_FILE_MAX_BYTES = 512 * 1024


class ChatUIProjectServiceError(Exception):
    pass


class ChatUIProjectService:
    def __init__(self, db: BaseDatabase) -> None:
        self.db = db

    async def create_project(self, username: str, data: object) -> dict:
        payload = self._as_payload(data)
        if username.startswith(API_KEY_USERNAME_PREFIX):
            requested_workspace_type = normalize_project_workspace_type(
                payload.get("workspace_type", WORKSPACE_TYPE_PROJECT)
            )
            if (
                requested_workspace_type == WORKSPACE_TYPE_CUSTOM
                or "workspace_path" in payload
            ):
                raise ChatUIProjectServiceError(
                    "API key projects cannot use custom workspaces"
                )
            payload = {**payload, "workspace_type": requested_workspace_type}
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
        if username.startswith(API_KEY_USERNAME_PREFIX):
            requested_workspace_type = normalize_project_workspace_type(
                payload.get("workspace_type", project.workspace_type)
            )
            if (
                "workspace_type" in payload
                and requested_workspace_type == WORKSPACE_TYPE_CUSTOM
            ) or "workspace_path" in payload:
                raise ChatUIProjectServiceError(
                    "API key projects cannot use custom workspaces"
                )
            if normalize_project_workspace_type(project.workspace_type) == (
                WORKSPACE_TYPE_CUSTOM
            ):
                payload = {**payload, "workspace_type": WORKSPACE_TYPE_PROJECT}
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

    async def list_workspace_files(
        self,
        username: str,
        project_id: str,
        relative_path: str = "",
    ) -> dict:
        """List one directory inside an owned project's workspace.

        Args:
            username: Dashboard username.
            project_id: ChatUI project ID.
            relative_path: Directory path relative to the workspace root.

        Returns:
            Directory metadata and its direct child entries.

        Raises:
            ChatUIProjectServiceError: If the path is invalid or unreadable.
        """
        project = await self._get_owned_project(username, project_id)
        fallback_umo = f"webchat:FriendMessage:webchat!{project.creator}!default"
        try:
            resolved_workspace_root = resolve_project_workspace_root(
                project,
                fallback_umo=fallback_umo,
            )
        except ValueError as exc:
            raise ChatUIProjectServiceError(str(exc)) from exc
        workspace_root_path = os.path.normcase(
            os.path.realpath(resolved_workspace_root)
        )
        workspace_root = Path(workspace_root_path)
        raw_path = str(relative_path or "").strip()
        normalized_path = Path(raw_path.replace("\\", "/") or ".")
        if normalized_path.is_absolute() or ".." in normalized_path.parts:
            raise ChatUIProjectServiceError("Invalid workspace path")

        target_dir_path = os.path.normcase(
            os.path.realpath(os.path.join(workspace_root_path, normalized_path))
        )
        # Keep the separator to reject sibling paths with the same name prefix.
        workspace_root_prefix = os.path.join(workspace_root_path, "")
        if target_dir_path != workspace_root_path and not target_dir_path.startswith(
            workspace_root_prefix
        ):
            raise ChatUIProjectServiceError("Workspace path escapes project directory")
        target_dir = Path(target_dir_path)
        if not workspace_root.exists() and normalized_path == Path("."):
            return {"path": "", "entries": []}
        if not target_dir.is_dir():
            raise ChatUIProjectServiceError("Workspace directory not found")

        try:
            children = sorted(
                target_dir.iterdir(),
                key=lambda item: (not item.is_dir(), item.name.lower()),
            )
        except OSError as exc:
            raise ChatUIProjectServiceError(
                "Workspace directory cannot be read"
            ) from exc

        entries = []
        for entry in children:
            if entry.is_symlink():
                continue
            try:
                if not entry.is_dir() and not entry.is_file():
                    continue
                stat = entry.stat()
            except OSError:
                continue
            is_directory = entry.is_dir()
            entries.append(
                {
                    "name": entry.name,
                    "path": entry.relative_to(workspace_root).as_posix(),
                    "type": "directory" if is_directory else "file",
                    "size": 0 if is_directory else stat.st_size,
                    "readable": (
                        not is_directory and stat.st_size <= _WORKSPACE_FILE_MAX_BYTES
                    ),
                }
            )

        current_path = target_dir.relative_to(workspace_root).as_posix()
        return {
            "path": "" if current_path == "." else current_path,
            "entries": entries,
        }

    async def get_workspace_file(
        self,
        username: str,
        project_id: str,
        relative_path: str,
    ) -> dict:
        """Read a UTF-8 text file inside an owned project's workspace.

        Args:
            username: Dashboard username.
            project_id: ChatUI project ID.
            relative_path: File path relative to the workspace root.

        Returns:
            Relative path, UTF-8 content, and byte size.

        Raises:
            ChatUIProjectServiceError: If the file is invalid or cannot be previewed.
        """
        _, target_file = await self.get_workspace_file_location(
            username,
            project_id,
            relative_path,
        )

        try:
            with target_file.open("rb") as file:
                content_bytes = file.read(_WORKSPACE_FILE_MAX_BYTES + 1)
        except OSError as exc:
            raise ChatUIProjectServiceError("Workspace file cannot be read") from exc
        if len(content_bytes) > _WORKSPACE_FILE_MAX_BYTES:
            raise ChatUIProjectServiceError("Workspace file is too large to preview")
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ChatUIProjectServiceError(
                "Workspace file is not valid UTF-8 text"
            ) from exc

        return {
            "path": relative_path,
            "content": content,
            "size": len(content_bytes),
        }

    async def get_workspace_file_location(
        self,
        username: str,
        project_id: str,
        relative_path: str,
    ) -> tuple[Path, Path]:
        """Resolve a file inside an owned project's workspace.

        Args:
            username: Dashboard username.
            project_id: ChatUI project ID.
            relative_path: File path relative to the workspace root.

        Returns:
            Validated workspace root and absolute path to the workspace file.

        Raises:
            ChatUIProjectServiceError: If the file path is invalid or missing.
        """
        project = await self._get_owned_project(username, project_id)
        fallback_umo = f"webchat:FriendMessage:webchat!{project.creator}!default"
        try:
            resolved_workspace_root = resolve_project_workspace_root(
                project,
                fallback_umo=fallback_umo,
            )
        except ValueError as exc:
            raise ChatUIProjectServiceError(str(exc)) from exc
        workspace_root_path = os.path.normcase(
            os.path.realpath(resolved_workspace_root)
        )
        raw_path = str(relative_path or "").strip()
        normalized_path = Path(raw_path.replace("\\", "/"))
        if (
            not raw_path
            or normalized_path.is_absolute()
            or ".." in normalized_path.parts
        ):
            raise ChatUIProjectServiceError("Invalid workspace path")

        # Match server-enumerated entries so request values never form a file path.
        target_file = Path(workspace_root_path)
        path_parts = normalized_path.parts
        for index, part in enumerate(path_parts):
            try:
                children = {entry.name: entry for entry in target_file.iterdir()}
            except OSError as exc:
                raise ChatUIProjectServiceError(
                    "Workspace file cannot be read"
                ) from exc
            child = children.get(part)
            if child is None:
                raise ChatUIProjectServiceError("Workspace file not found")
            if child.is_symlink():
                if not child.resolve(strict=False).is_relative_to(
                    Path(workspace_root_path)
                ):
                    raise ChatUIProjectServiceError(
                        "Workspace path escapes project directory"
                    )
                raise ChatUIProjectServiceError("Workspace file not found")
            if index < len(path_parts) - 1 and not child.is_dir():
                raise ChatUIProjectServiceError("Workspace file not found")
            target_file = child
        if not path_parts or not target_file.is_file():
            raise ChatUIProjectServiceError("Workspace file not found")

        return Path(workspace_root_path), target_file

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
