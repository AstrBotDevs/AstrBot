import typing as T
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, desc, func, or_, select, update

from astrbot.core.db.po import ConversationV2, Persona, Preference


class ConversationStoreMixin:
    async def get_conversations(
        self,
        user_id: str | None = None,
        platform_id: str | None = None,
    ) -> list[ConversationV2]:
        async with self.get_db() as session:
            session: AsyncSession
            query = select(ConversationV2)

            if user_id:
                query = query.where(ConversationV2.user_id == user_id)
            if platform_id:
                query = query.where(ConversationV2.platform_id == platform_id)
            # order by
            query = query.order_by(desc(ConversationV2.created_at))
            result = await session.execute(query)

            return list(result.scalars().all())

    async def get_conversation_by_id(self, cid: str) -> ConversationV2 | None:
        async with self.get_db() as session:
            session: AsyncSession
            query = select(ConversationV2).where(ConversationV2.conversation_id == cid)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_all_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> list[ConversationV2]:
        async with self.get_db() as session:
            session: AsyncSession
            offset = (page - 1) * page_size
            result = await session.execute(
                select(ConversationV2)
                .order_by(desc(ConversationV2.created_at))
                .offset(offset)
                .limit(page_size),
            )
            return list(result.scalars().all())

    async def get_filtered_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
        platform_ids: list[str] | None = None,
        search_query: str = "",
        **kwargs: T.Any,
    ) -> tuple[list[ConversationV2], int]:
        async with self.get_db() as session:
            session: AsyncSession
            # Build the base query with filters
            base_query = select(ConversationV2)

            if platform_ids:
                base_query = base_query.where(
                    col(ConversationV2.platform_id).in_(platform_ids),
                )
            if search_query:
                escaped_search_query = (
                    search_query.replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                search_pattern = f"%{escaped_search_query}%"
                base_query = base_query.where(
                    or_(
                        col(ConversationV2.title).ilike(search_pattern, escape="\\"),
                        col(ConversationV2.content).ilike(search_pattern, escape="\\"),
                        col(ConversationV2.user_id).ilike(search_pattern, escape="\\"),
                        col(ConversationV2.conversation_id).ilike(
                            search_pattern,
                            escape="\\",
                        ),
                    ),
                )
            if "message_types" in kwargs and len(kwargs["message_types"]) > 0:
                for msg_type in kwargs["message_types"]:
                    base_query = base_query.where(
                        col(ConversationV2.user_id).ilike(f"%:{msg_type}:%"),
                    )
            if "platforms" in kwargs and len(kwargs["platforms"]) > 0:
                base_query = base_query.where(
                    col(ConversationV2.platform_id).in_(kwargs["platforms"]),
                )

            # Get total count matching the filters
            count_query = select(func.count()).select_from(base_query.subquery())
            total_count = await session.execute(count_query)
            total = total_count.scalar_one()

            # Get paginated results
            offset = (page - 1) * page_size
            result_query = (
                base_query.order_by(desc(ConversationV2.created_at))
                .offset(offset)
                .limit(page_size)
            )
            result = await session.execute(result_query)
            conversations = list(result.scalars().all())

            return conversations, total

    async def create_conversation(
        self,
        user_id: str,
        platform_id: str,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
        cid: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> ConversationV2:
        kwargs = {}
        if cid:
            kwargs["conversation_id"] = cid
        if created_at:
            kwargs["created_at"] = created_at
        if updated_at:
            kwargs["updated_at"] = updated_at
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_conversation = ConversationV2(
                    user_id=user_id,
                    content=content or [],
                    platform_id=platform_id,
                    title=title,
                    persona_id=persona_id,
                    **kwargs,
                )
                session.add(new_conversation)
                return new_conversation

    async def update_conversation(
        self,
        cid: str,
        title: str | None = None,
        persona_id: str | None = None,
        content: list[dict] | None = None,
        token_usage: int | None = None,
    ) -> ConversationV2 | None:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = update(ConversationV2).where(
                    col(ConversationV2.conversation_id) == cid,
                )
                values = {}
                if title is not None:
                    values["title"] = title
                if persona_id is not None:
                    values["persona_id"] = persona_id
                if content is not None:
                    values["content"] = content
                if token_usage is not None:
                    values["token_usage"] = token_usage
                if not values:
                    return None
                query = query.values(**values)
                await session.execute(query)
        return await self.get_conversation_by_id(cid)

    async def delete_conversation(self, cid: str) -> None:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(ConversationV2).where(
                        col(ConversationV2.conversation_id) == cid,
                    ),
                )

    async def delete_conversations_by_user_id(self, user_id: str) -> None:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(ConversationV2).where(
                        col(ConversationV2.user_id) == user_id
                    ),
                )

    async def get_session_conversations(
        self,
        page=1,
        page_size=20,
        search_query=None,
        platform=None,
    ) -> tuple[list[dict], int]:
        """Get paginated session conversations with joined conversation and persona details."""
        async with self.get_db() as session:
            session: AsyncSession
            offset = (page - 1) * page_size

            base_query = (
                select(
                    col(Preference.scope_id).label("session_id"),
                    func.json_extract(Preference.value, "$.val").label(
                        "conversation_id",
                    ),  # type: ignore
                    col(ConversationV2.persona_id).label("persona_id"),
                    col(ConversationV2.title).label("title"),
                    col(Persona.persona_id).label("persona_name"),
                )
                .select_from(Preference)
                .outerjoin(
                    ConversationV2,
                    func.json_extract(Preference.value, "$.val")
                    == ConversationV2.conversation_id,
                )
                .outerjoin(
                    Persona,
                    col(ConversationV2.persona_id) == Persona.persona_id,
                )
                .where(Preference.scope == "umo", Preference.key == "sel_conv_id")
            )

            # 搜索筛选
            if search_query:
                search_pattern = f"%{search_query}%"
                base_query = base_query.where(
                    or_(
                        col(Preference.scope_id).ilike(search_pattern),
                        col(ConversationV2.title).ilike(search_pattern),
                        col(Persona.persona_id).ilike(search_pattern),
                    ),
                )

            # 平台筛选
            if platform:
                platform_pattern = f"{platform}:%"
                base_query = base_query.where(
                    col(Preference.scope_id).like(platform_pattern),
                )

            # 排序
            base_query = base_query.order_by(Preference.scope_id)

            # 分页结果
            result_query = base_query.offset(offset).limit(page_size)
            result = await session.execute(result_query)
            rows = result.fetchall()

            # 查询总数（应用相同的筛选条件）
            count_base_query = (
                select(func.count(col(Preference.scope_id)))
                .select_from(Preference)
                .outerjoin(
                    ConversationV2,
                    func.json_extract(Preference.value, "$.val")
                    == ConversationV2.conversation_id,
                )
                .outerjoin(
                    Persona,
                    col(ConversationV2.persona_id) == Persona.persona_id,
                )
                .where(Preference.scope == "umo", Preference.key == "sel_conv_id")
            )

            # 应用相同的搜索和平台筛选条件到计数查询
            if search_query:
                search_pattern = f"%{search_query}%"
                count_base_query = count_base_query.where(
                    or_(
                        col(Preference.scope_id).ilike(search_pattern),
                        col(ConversationV2.title).ilike(search_pattern),
                        col(Persona.persona_id).ilike(search_pattern),
                    ),
                )

            if platform:
                platform_pattern = f"{platform}:%"
                count_base_query = count_base_query.where(
                    col(Preference.scope_id).like(platform_pattern),
                )

            total_result = await session.execute(count_base_query)
            total = total_result.scalar() or 0

            sessions_data = [
                {
                    "session_id": row.session_id,
                    "conversation_id": row.conversation_id,
                    "persona_id": row.persona_id,
                    "title": row.title,
                    "persona_name": row.persona_name,
                }
                for row in rows
            ]
            return sessions_data, total
