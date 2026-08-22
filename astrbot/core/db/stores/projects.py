import typing as T
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, desc, select, update

from astrbot.core.db.po import ChatUIProject, PlatformSession, SessionProjectRelation


class ChatProjectStoreMixin:
    async def create_chatui_project(
        self,
        creator: str,
        title: str,
        emoji: str | None = "📁",
        description: str | None = None,
    ) -> ChatUIProject:
        """Create a new ChatUI project."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                project = ChatUIProject(
                    creator=creator,
                    title=title,
                    emoji=emoji,
                    description=description,
                )
                session.add(project)
                await session.flush()
                await session.refresh(project)
                return project

    async def get_chatui_project_by_id(self, project_id: str) -> ChatUIProject | None:
        """Get a ChatUI project by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(ChatUIProject).where(
                    col(ChatUIProject.project_id) == project_id,
                ),
            )
            return result.scalar_one_or_none()

    async def get_chatui_projects_by_creator(
        self,
        creator: str,
        page: int = 1,
        page_size: int = 100,
    ) -> list[ChatUIProject]:
        """Get all ChatUI projects for a specific creator."""
        async with self.get_db() as session:
            session: AsyncSession
            offset = (page - 1) * page_size
            result = await session.execute(
                select(ChatUIProject)
                .where(col(ChatUIProject.creator) == creator)
                .order_by(desc(ChatUIProject.updated_at))
                .limit(page_size)
                .offset(offset),
            )
            return list(result.scalars().all())

    async def update_chatui_project(
        self,
        project_id: str,
        title: str | None = None,
        emoji: str | None = None,
        description: str | None = None,
    ) -> None:
        """Update a ChatUI project."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                values: dict[str, T.Any] = {"updated_at": datetime.now(UTC)}
                if title is not None:
                    values["title"] = title
                if emoji is not None:
                    values["emoji"] = emoji
                if description is not None:
                    values["description"] = description

                await session.execute(
                    update(ChatUIProject)
                    .where(col(ChatUIProject.project_id) == project_id)
                    .values(**values),
                )

    async def delete_chatui_project(self, project_id: str) -> None:
        """Delete a ChatUI project by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                # First remove all session relations
                await session.execute(
                    delete(SessionProjectRelation).where(
                        col(SessionProjectRelation.project_id) == project_id,
                    ),
                )
                # Then delete the project
                await session.execute(
                    delete(ChatUIProject).where(
                        col(ChatUIProject.project_id) == project_id,
                    ),
                )

    async def add_session_to_project(
        self,
        session_id: str,
        project_id: str,
    ) -> SessionProjectRelation:
        """Add a session to a project."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                # First remove existing relation if any
                await session.execute(
                    delete(SessionProjectRelation).where(
                        col(SessionProjectRelation.session_id) == session_id,
                    ),
                )
                # Then create new relation
                relation = SessionProjectRelation(
                    session_id=session_id,
                    project_id=project_id,
                )
                session.add(relation)
                await session.flush()
                await session.refresh(relation)
                return relation

    async def remove_session_from_project(self, session_id: str) -> None:
        """Remove a session from its project."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(SessionProjectRelation).where(
                        col(SessionProjectRelation.session_id) == session_id,
                    ),
                )

    async def get_project_sessions(
        self,
        project_id: str,
        page: int = 1,
        page_size: int = 100,
    ) -> list[PlatformSession]:
        """Get all sessions in a project."""
        async with self.get_db() as session:
            session: AsyncSession
            offset = (page - 1) * page_size
            result = await session.execute(
                select(PlatformSession)
                .join(
                    SessionProjectRelation,
                    col(PlatformSession.session_id)
                    == col(SessionProjectRelation.session_id),
                )
                .where(col(SessionProjectRelation.project_id) == project_id)
                .order_by(desc(PlatformSession.updated_at))
                .limit(page_size)
                .offset(offset),
            )
            return list(result.scalars().all())

    async def get_project_by_session(
        self, session_id: str, creator: str
    ) -> ChatUIProject | None:
        """Get the project that a session belongs to."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(ChatUIProject)
                .join(
                    SessionProjectRelation,
                    col(ChatUIProject.project_id)
                    == col(SessionProjectRelation.project_id),
                )
                .where(
                    col(SessionProjectRelation.session_id) == session_id,
                    col(ChatUIProject.creator) == creator,
                ),
            )
            return result.scalar_one_or_none()
