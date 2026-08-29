import typing as T
from datetime import UTC, datetime

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, desc, func, select, update

from astrbot.core.db.po import ChatUIProject, PlatformSession, SessionProjectRelation
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session


class PlatformSessionStoreMixin(DatabaseStoreMixin):
    async def create_platform_session(
        self,
        creator: str,
        platform_id: str = "webchat",
        session_id: str | None = None,
        display_name: str | None = None,
    ) -> PlatformSession:
        """Create a new Platform session."""
        kwargs = {}
        if session_id:
            kwargs["session_id"] = session_id

        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                new_session = PlatformSession(
                    creator=creator,
                    platform_id=platform_id,
                    display_name=display_name,
                    **kwargs,
                )
                session.add(new_session)
                await session.flush()
                await session.refresh(new_session)
                return new_session

    async def get_platform_session_by_id(
        self, session_id: str
    ) -> PlatformSession | None:
        """Get a Platform session by its ID."""
        async with store_session(self) as session:
            session: AsyncSession
            query = select(PlatformSession).where(
                PlatformSession.session_id == session_id,
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_platform_sessions_by_ids(
        self, session_ids: list[str]
    ) -> list[PlatformSession]:
        """Get platform sessions by IDs."""
        if not session_ids:
            return []

        async with store_session(self) as session:
            session: AsyncSession
            query = select(PlatformSession).where(
                col(PlatformSession.session_id).in_(session_ids)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_platform_sessions_by_creator(
        self,
        creator: str,
        platform_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict]:
        """Get all Platform sessions for a specific creator (username) and optionally platform.

        Returns a list of dicts containing session info and project info (if session belongs to a project).
        """
        (
            sessions_with_projects,
            _,
        ) = await self.get_platform_sessions_by_creator_paginated(
            creator=creator,
            platform_id=platform_id,
            page=page,
            page_size=page_size,
            exclude_project_sessions=False,
        )
        return sessions_with_projects

    @staticmethod
    def _build_platform_sessions_query(
        creator: str,
        platform_id: str | None = None,
        exclude_project_sessions: bool = False,
    ):
        query = (
            select(
                PlatformSession,
                col(ChatUIProject.project_id),
                col(ChatUIProject.title).label("project_title"),
                col(ChatUIProject.emoji).label("project_emoji"),
            )
            .outerjoin(
                SessionProjectRelation,
                col(PlatformSession.session_id)
                == col(SessionProjectRelation.session_id),
            )
            .outerjoin(
                ChatUIProject,
                col(SessionProjectRelation.project_id) == col(ChatUIProject.project_id),
            )
            .where(col(PlatformSession.creator) == creator)
        )

        if platform_id:
            query = query.where(PlatformSession.platform_id == platform_id)
        if exclude_project_sessions:
            query = query.where(col(ChatUIProject.project_id).is_(None))

        return query

    @staticmethod
    def _rows_to_session_dicts(rows: T.Sequence[Row[tuple]]) -> list[dict]:
        sessions_with_projects = []
        for row in rows:
            platform_session = row[0]
            project_id = row[1]
            project_title = row[2]
            project_emoji = row[3]

            session_dict = {
                "session": platform_session,
                "project_id": project_id,
                "project_title": project_title,
                "project_emoji": project_emoji,
            }
            sessions_with_projects.append(session_dict)

        return sessions_with_projects

    async def get_platform_sessions_by_creator_paginated(
        self,
        creator: str,
        platform_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
        exclude_project_sessions: bool = False,
    ) -> tuple[list[dict], int]:
        """Get paginated Platform sessions for a creator with total count."""
        async with store_session(self) as session:
            session: AsyncSession
            offset = (page - 1) * page_size

            base_query = self._build_platform_sessions_query(
                creator=creator,
                platform_id=platform_id,
                exclude_project_sessions=exclude_project_sessions,
            )

            total_result = await session.execute(
                select(func.count()).select_from(base_query.subquery())
            )
            total = int(total_result.scalar_one() or 0)

            result_query = (
                base_query.order_by(desc(PlatformSession.updated_at))
                .offset(offset)
                .limit(page_size)
            )
            result = await session.execute(result_query)

            sessions_with_projects = self._rows_to_session_dicts(result.all())
            return sessions_with_projects, total

    async def update_platform_session(
        self,
        session_id: str,
        display_name: str | None = None,
    ) -> None:
        """Update a Platform session's updated_at timestamp and optionally display_name."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                values: dict[str, T.Any] = {"updated_at": datetime.now(UTC)}
                if display_name is not None:
                    values["display_name"] = display_name

                await session.execute(
                    update(PlatformSession)
                    .where(col(PlatformSession.session_id) == session_id)
                    .values(**values),
                )

    async def delete_platform_session(self, session_id: str) -> None:
        """Delete a Platform session by its ID."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(PlatformSession).where(
                        col(PlatformSession.session_id) == session_id,
                    ),
                )
