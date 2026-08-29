import json
import typing as T
from datetime import datetime

from sqlalchemy import case, not_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from sqlmodel import col, delete, desc, func, or_, select, update

from astrbot.core.db.po import ConversationV2, Persona, Preference
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session


def _ilike_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class ConversationStoreMixin(DatabaseStoreMixin):
    async def get_conversations(
        self,
        user_id: str | None = None,
        platform_id: str | None = None,
    ) -> list[ConversationV2]:
        async with store_session(self) as session:
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
        async with store_session(self) as session:
            session: AsyncSession
            query = select(ConversationV2).where(ConversationV2.conversation_id == cid)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_all_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> list[ConversationV2]:
        async with store_session(self) as session:
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
        include_history: bool = True,
        **kwargs: T.Any,
    ) -> tuple[list[ConversationV2], int]:
        async with store_session(self) as session:
            session: AsyncSession
            base_query = select(ConversationV2)
            conditions = []

            if platform_ids:
                conditions.append(col(ConversationV2.platform_id).in_(platform_ids))
            if search_query:
                search_pattern = _ilike_pattern(search_query)
                conditions.append(
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
            keyword_query = str(kwargs.get("keyword_query") or "").strip()
            if keyword_query:
                keyword_pattern = _ilike_pattern(keyword_query)
                json_keyword_pattern = _ilike_pattern(
                    json.dumps(keyword_query, ensure_ascii=True)[1:-1],
                )
                conditions.append(
                    or_(
                        col(ConversationV2.title).ilike(keyword_pattern, escape="\\"),
                        col(ConversationV2.content).ilike(
                            keyword_pattern,
                            escape="\\",
                        ),
                        col(ConversationV2.content).ilike(
                            json_keyword_pattern,
                            escape="\\",
                        ),
                    ),
                )
            message_types = kwargs.get("message_types") or []
            if message_types:
                conditions.append(
                    or_(
                        *(
                            col(ConversationV2.user_id).ilike(f"%:{msg_type}:%")
                            for msg_type in message_types
                        ),
                    ),
                )
            platforms = kwargs.get("platforms") or []
            if platforms:
                conditions.append(col(ConversationV2.platform_id).in_(platforms))
            for exclude_id in kwargs.get("exclude_ids") or []:
                conditions.append(
                    not_(col(ConversationV2.user_id).like(f"{exclude_id}%")),
                )
            exclude_platforms = kwargs.get("exclude_platforms") or []
            if exclude_platforms:
                conditions.append(
                    not_(col(ConversationV2.platform_id).in_(exclude_platforms)),
                )
            umo_query = str(kwargs.get("umo_query") or "").strip()
            if umo_query:
                conditions.append(
                    col(ConversationV2.user_id).ilike(
                        _ilike_pattern(umo_query),
                        escape="\\",
                    ),
                )

            if conditions:
                base_query = base_query.where(*conditions)

            group_by_session = bool(kwargs.get("group_by_session", False))
            count_query = select(
                func.count(func.distinct(col(ConversationV2.user_id)))
                if group_by_session
                else func.count(col(ConversationV2.inner_conversation_id))
            )
            if conditions:
                count_query = count_query.where(*conditions)
            total = (await session.execute(count_query)).scalar_one()

            offset = (page - 1) * page_size
            sort_by = kwargs.get("sort_by", "created_at")
            sort_order = kwargs.get("sort_order", "desc")
            sort_column = (
                col(ConversationV2.updated_at)
                if sort_by == "updated_at"
                else col(ConversationV2.created_at)
            )
            order = sort_column.asc if sort_order == "asc" else sort_column.desc
            tie_breaker = (
                col(ConversationV2.inner_conversation_id).asc
                if sort_order == "asc"
                else col(ConversationV2.inner_conversation_id).desc
            )
            if group_by_session:
                session_sort = func.max(sort_column).label("session_sort")
                session_tie_breaker = func.max(
                    ConversationV2.inner_conversation_id,
                ).label("session_tie_breaker")
                session_query = select(
                    ConversationV2.user_id,
                    session_sort,
                    session_tie_breaker,
                )
                if conditions:
                    session_query = session_query.where(*conditions)
                session_order = (
                    session_sort.asc if sort_order == "asc" else session_sort.desc
                )
                session_tie_order = (
                    session_tie_breaker.asc
                    if sort_order == "asc"
                    else session_tie_breaker.desc
                )
                session_rows = await session.execute(
                    session_query.group_by(ConversationV2.user_id)
                    .order_by(session_order())
                    .order_by(session_tie_order())
                    .offset(offset)
                    .limit(page_size),
                )
                session_ids = [row[0] for row in session_rows.all()]
                if not session_ids:
                    return [], total
                session_rank = case(
                    {session_id: index for index, session_id in enumerate(session_ids)},
                    value=ConversationV2.user_id,
                    else_=len(session_ids),
                )
                result_query = (
                    base_query.where(col(ConversationV2.user_id).in_(session_ids))
                    .order_by(session_rank)
                    .order_by(order())
                    .order_by(tie_breaker())
                )
            else:
                result_query = (
                    base_query.order_by(order())
                    .order_by(tie_breaker())
                    .offset(offset)
                    .limit(page_size)
                )
            if not include_history:
                result_query = result_query.options(
                    defer(ConversationV2.content)  # type: ignore[arg-type]
                )
            conversations = list((await session.execute(result_query)).scalars().all())
            return conversations, total

    async def get_conversation_platform_ids(self) -> list[str]:
        """Return distinct platform IDs referenced by conversation history.

        Returns:
            Sorted platform IDs that have at least one conversation.
        """
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(ConversationV2.platform_id)
                .distinct()
                .order_by(ConversationV2.platform_id),
            )
            return [platform_id for platform_id in result.scalars() if platform_id]

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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(ConversationV2).where(
                        col(ConversationV2.conversation_id) == cid,
                    ),
                )

    async def delete_conversations_by_user_id(self, user_id: str) -> None:
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
