import asyncio
import threading
import typing as T
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, desc, func, or_, select, text, update

from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import (
    Attachment,
    ChatUIProject,
    CommandConfig,
    CommandConflict,
    ConversationV2,
    Persona,
    PlatformMessageHistory,
    PlatformSession,
    PlatformStat,
    Preference,
    SessionProjectRelation,
    SQLModel,
)
from astrbot.core.db.po import (
    Platform as DeprecatedPlatformStat,
)
from astrbot.core.db.po import (
    Stats as DeprecatedStats,
)

NOT_GIVEN = T.TypeVar("NOT_GIVEN")
TxResult = T.TypeVar("TxResult")


class SQLiteDatabase(BaseDatabase):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
        self.inited = False
        super().__init__()

    async def initialize(self) -> None:
        """Initialize the database by creating tables if they do not exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=20000"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
            await conn.execute(text("PRAGMA mmap_size=134217728"))
            await conn.execute(text("PRAGMA optimize"))
            await conn.commit()

    # ====
    # Platform Statistics
    # ====

    async def insert_platform_stats(
        self,
        platform_id,
        platform_type,
        count=1,
        timestamp=None,
    ) -> None:
        """Insert a new platform statistic record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                if timestamp is None:
                    timestamp = datetime.now().replace(
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
                current_hour = timestamp
                await session.execute(
                    text("""
                    INSERT INTO platform_stats (timestamp, platform_id, platform_type, count)
                    VALUES (:timestamp, :platform_id, :platform_type, :count)
                    ON CONFLICT(timestamp, platform_id, platform_type) DO UPDATE SET
                        count = platform_stats.count + EXCLUDED.count
                    """),
                    {
                        "timestamp": current_hour,
                        "platform_id": platform_id,
                        "platform_type": platform_type,
                        "count": count,
                    },
                )

    async def count_platform_stats(self) -> int:
        """Count the number of platform statistics records."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(func.count(col(PlatformStat.platform_id))).select_from(
                    PlatformStat,
                ),
            )
            count = result.scalar_one_or_none()
            return count if count is not None else 0

    async def get_platform_stats(self, offset_sec: int = 86400) -> list[PlatformStat]:
        """Get platform statistics within the specified offset in seconds and group by platform_id."""
        async with self.get_db() as session:
            session: AsyncSession
            now = datetime.now()
            start_time = now - timedelta(seconds=offset_sec)
            result = await session.execute(
                text("""
                SELECT * FROM platform_stats
                WHERE timestamp >= :start_time
                GROUP BY platform_id
                ORDER BY timestamp DESC
                """),
                {"start_time": start_time},
            )
            return list(result.scalars().all())

    # ====
    # Conversation Management
    # ====

    async def get_conversations(self, user_id=None, platform_id=None):
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

            return result.scalars().all()

    async def get_conversation_by_id(self, cid):
        async with self.get_db() as session:
            session: AsyncSession
            query = select(ConversationV2).where(ConversationV2.conversation_id == cid)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_all_conversations(self, page=1, page_size=20):
        async with self.get_db() as session:
            session: AsyncSession
            offset = (page - 1) * page_size
            result = await session.execute(
                select(ConversationV2)
                .order_by(desc(ConversationV2.created_at))
                .offset(offset)
                .limit(page_size),
            )
            return result.scalars().all()

    async def get_filtered_conversations(
        self,
        page=1,
        page_size=20,
        platform_ids=None,
        search_query="",
        **kwargs,
    ):
        async with self.get_db() as session:
            session: AsyncSession
            # Build the base query with filters
            base_query = select(ConversationV2)

            if platform_ids:
                base_query = base_query.where(
                    col(ConversationV2.platform_id).in_(platform_ids),
                )
            if search_query:
                search_query = search_query.encode("unicode_escape").decode("utf-8")
                base_query = base_query.where(
                    or_(
                        col(ConversationV2.title).ilike(f"%{search_query}%"),
                        col(ConversationV2.content).ilike(f"%{search_query}%"),
                        col(ConversationV2.user_id).ilike(f"%{search_query}%"),
                        col(ConversationV2.conversation_id).ilike(f"%{search_query}%"),
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
            conversations = result.scalars().all()

            return conversations, total

    async def create_conversation(
        self,
        user_id,
        platform_id,
        content=None,
        title=None,
        persona_id=None,
        cid=None,
        created_at=None,
        updated_at=None,
    ):
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
        self, cid, title=None, persona_id=None, content=None, token_usage=None
    ):
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

    async def delete_conversation(self, cid):
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

    async def insert_platform_message_history(
        self,
        platform_id,
        user_id,
        content,
        sender_id=None,
        sender_name=None,
    ):
        """Insert a new platform message history record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_history = PlatformMessageHistory(
                    platform_id=platform_id,
                    user_id=user_id,
                    content=content,
                    sender_id=sender_id,
                    sender_name=sender_name,
                )
                session.add(new_history)
                return new_history

    async def delete_platform_message_offset(
        self,
        platform_id,
        user_id,
        offset_sec=86400,
    ):
        """Delete platform message history records newer than the specified offset."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                now = datetime.now()
                cutoff_time = now - timedelta(seconds=offset_sec)
                await session.execute(
                    delete(PlatformMessageHistory).where(
                        col(PlatformMessageHistory.platform_id) == platform_id,
                        col(PlatformMessageHistory.user_id) == user_id,
                        col(PlatformMessageHistory.created_at) >= cutoff_time,
                    ),
                )

    async def get_platform_message_history(
        self,
        platform_id,
        user_id,
        page=1,
        page_size=20,
    ):
        """Get platform message history records."""
        async with self.get_db() as session:
            session: AsyncSession
            offset = (page - 1) * page_size
            query = (
                select(PlatformMessageHistory)
                .where(
                    PlatformMessageHistory.platform_id == platform_id,
                    PlatformMessageHistory.user_id == user_id,
                )
                .order_by(desc(PlatformMessageHistory.created_at))
            )
            result = await session.execute(query.offset(offset).limit(page_size))
            return result.scalars().all()

    async def get_platform_message_history_by_id(
        self, message_id: int
    ) -> PlatformMessageHistory | None:
        """Get a platform message history record by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(PlatformMessageHistory).where(
                PlatformMessageHistory.id == message_id
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def insert_attachment(self, path, type, mime_type):
        """Insert a new attachment record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_attachment = Attachment(
                    path=path,
                    type=type,
                    mime_type=mime_type,
                )
                session.add(new_attachment)
                return new_attachment

    async def get_attachment_by_id(self, attachment_id):
        """Get an attachment by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Attachment).where(Attachment.attachment_id == attachment_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_attachments(self, attachment_ids: list[str]) -> list:
        """Get multiple attachments by their IDs."""
        if not attachment_ids:
            return []
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Attachment).where(
                col(Attachment.attachment_id).in_(attachment_ids)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def delete_attachment(self, attachment_id: str) -> bool:
        """Delete an attachment by its ID.

        Returns True if the attachment was deleted, False if it was not found.
        """
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = delete(Attachment).where(
                    col(Attachment.attachment_id) == attachment_id
                )
                result = T.cast(CursorResult, await session.execute(query))
                return result.rowcount > 0

    async def delete_attachments(self, attachment_ids: list[str]) -> int:
        """Delete multiple attachments by their IDs.

        Returns the number of attachments deleted.
        """
        if not attachment_ids:
            return 0
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = delete(Attachment).where(
                    col(Attachment.attachment_id).in_(attachment_ids)
                )
                result = T.cast(CursorResult, await session.execute(query))
                return result.rowcount

    async def insert_persona(
        self,
        persona_id,
        system_prompt,
        begin_dialogs=None,
        tools=None,
    ):
        """Insert a new persona record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_persona = Persona(
                    persona_id=persona_id,
                    system_prompt=system_prompt,
                    begin_dialogs=begin_dialogs or [],
                    tools=tools,
                )
                session.add(new_persona)
                return new_persona

    async def get_persona_by_id(self, persona_id):
        """Get a persona by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Persona).where(Persona.persona_id == persona_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_personas(self):
        """Get all personas for a specific bot."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Persona)
            result = await session.execute(query)
            return result.scalars().all()

    async def update_persona(
        self,
        persona_id,
        system_prompt=None,
        begin_dialogs=None,
        tools=NOT_GIVEN,
    ):
        """Update a persona's system prompt or begin dialogs."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = update(Persona).where(col(Persona.persona_id) == persona_id)
                values = {}
                if system_prompt is not None:
                    values["system_prompt"] = system_prompt
                if begin_dialogs is not None:
                    values["begin_dialogs"] = begin_dialogs
                if tools is not NOT_GIVEN:
                    values["tools"] = tools
                if not values:
                    return None
                query = query.values(**values)
                await session.execute(query)
        return await self.get_persona_by_id(persona_id)

    async def delete_persona(self, persona_id):
        """Delete a persona by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(Persona).where(col(Persona.persona_id) == persona_id),
                )

    async def insert_preference_or_update(self, scope, scope_id, key, value):
        """Insert a new preference record or update if it exists."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = select(Preference).where(
                    Preference.scope == scope,
                    Preference.scope_id == scope_id,
                    Preference.key == key,
                )
                result = await session.execute(query)
                existing_preference = result.scalar_one_or_none()
                if existing_preference:
                    existing_preference.value = value
                else:
                    new_preference = Preference(
                        scope=scope,
                        scope_id=scope_id,
                        key=key,
                        value=value,
                    )
                    session.add(new_preference)
                return existing_preference or new_preference

    async def get_preference(self, scope, scope_id, key):
        """Get a preference by key."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Preference).where(
                Preference.scope == scope,
                Preference.scope_id == scope_id,
                Preference.key == key,
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_preferences(self, scope, scope_id=None, key=None):
        """Get all preferences for a specific scope ID or key."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Preference).where(Preference.scope == scope)
            if scope_id is not None:
                query = query.where(Preference.scope_id == scope_id)
            if key is not None:
                query = query.where(Preference.key == key)
            result = await session.execute(query)
            return result.scalars().all()

    async def remove_preference(self, scope, scope_id, key):
        """Remove a preference by scope ID and key."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(Preference).where(
                        col(Preference.scope) == scope,
                        col(Preference.scope_id) == scope_id,
                        col(Preference.key) == key,
                    ),
                )
            await session.commit()

    async def clear_preferences(self, scope, scope_id):
        """Clear all preferences for a specific scope ID."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(Preference).where(
                        col(Preference.scope) == scope,
                        col(Preference.scope_id) == scope_id,
                    ),
                )
            await session.commit()

    # ====
    # Command Configuration & Conflict Tracking
    # ====

    async def _run_in_tx(
        self,
        fn: Callable[[AsyncSession], Awaitable[TxResult]],
    ) -> TxResult:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                return await fn(session)

    @staticmethod
    def _apply_updates(model, **updates) -> None:
        for field, value in updates.items():
            if value is not None:
                setattr(model, field, value)

    @staticmethod
    def _new_command_config(
        handler_full_name: str,
        plugin_name: str,
        module_path: str,
        original_command: str,
        *,
        resolved_command: str | None = None,
        enabled: bool | None = None,
        keep_original_alias: bool | None = None,
        conflict_key: str | None = None,
        resolution_strategy: str | None = None,
        note: str | None = None,
        extra_data: dict | None = None,
        auto_managed: bool | None = None,
    ) -> CommandConfig:
        return CommandConfig(
            handler_full_name=handler_full_name,
            plugin_name=plugin_name,
            module_path=module_path,
            original_command=original_command,
            resolved_command=resolved_command,
            enabled=True if enabled is None else enabled,
            keep_original_alias=False
            if keep_original_alias is None
            else keep_original_alias,
            conflict_key=conflict_key or original_command,
            resolution_strategy=resolution_strategy,
            note=note,
            extra_data=extra_data,
            auto_managed=bool(auto_managed),
        )

    @staticmethod
    def _new_command_conflict(
        conflict_key: str,
        handler_full_name: str,
        plugin_name: str,
        *,
        status: str | None = None,
        resolution: str | None = None,
        resolved_command: str | None = None,
        note: str | None = None,
        extra_data: dict | None = None,
        auto_generated: bool | None = None,
    ) -> CommandConflict:
        return CommandConflict(
            conflict_key=conflict_key,
            handler_full_name=handler_full_name,
            plugin_name=plugin_name,
            status=status or "pending",
            resolution=resolution,
            resolved_command=resolved_command,
            note=note,
            extra_data=extra_data,
            auto_generated=bool(auto_generated),
        )

    async def get_command_configs(self) -> list[CommandConfig]:
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(select(CommandConfig))
            return list(result.scalars().all())

    async def get_command_config(
        self,
        handler_full_name: str,
    ) -> CommandConfig | None:
        async with self.get_db() as session:
            session: AsyncSession
            return await session.get(CommandConfig, handler_full_name)

    async def upsert_command_config(
        self,
        handler_full_name: str,
        plugin_name: str,
        module_path: str,
        original_command: str,
        *,
        resolved_command: str | None = None,
        enabled: bool | None = None,
        keep_original_alias: bool | None = None,
        conflict_key: str | None = None,
        resolution_strategy: str | None = None,
        note: str | None = None,
        extra_data: dict | None = None,
        auto_managed: bool | None = None,
    ) -> CommandConfig:
        async def _op(session: AsyncSession) -> CommandConfig:
            config = await session.get(CommandConfig, handler_full_name)
            if not config:
                config = self._new_command_config(
                    handler_full_name,
                    plugin_name,
                    module_path,
                    original_command,
                    resolved_command=resolved_command,
                    enabled=enabled,
                    keep_original_alias=keep_original_alias,
                    conflict_key=conflict_key,
                    resolution_strategy=resolution_strategy,
                    note=note,
                    extra_data=extra_data,
                    auto_managed=auto_managed,
                )
                session.add(config)
            else:
                self._apply_updates(
                    config,
                    plugin_name=plugin_name,
                    module_path=module_path,
                    original_command=original_command,
                    resolved_command=resolved_command,
                    enabled=enabled,
                    keep_original_alias=keep_original_alias,
                    conflict_key=conflict_key,
                    resolution_strategy=resolution_strategy,
                    note=note,
                    extra_data=extra_data,
                    auto_managed=auto_managed,
                )
            await session.flush()
            await session.refresh(config)
            return config

        return await self._run_in_tx(_op)

    async def delete_command_config(self, handler_full_name: str) -> None:
        await self.delete_command_configs([handler_full_name])

    async def delete_command_configs(self, handler_full_names: list[str]) -> None:
        if not handler_full_names:
            return

        async def _op(session: AsyncSession) -> None:
            await session.execute(
                delete(CommandConfig).where(
                    col(CommandConfig.handler_full_name).in_(handler_full_names),
                ),
            )

        await self._run_in_tx(_op)

    async def list_command_conflicts(
        self,
        status: str | None = None,
    ) -> list[CommandConflict]:
        async with self.get_db() as session:
            session: AsyncSession
            query = select(CommandConflict)
            if status:
                query = query.where(CommandConflict.status == status)
            result = await session.execute(query)
            return list(result.scalars().all())

    async def upsert_command_conflict(
        self,
        conflict_key: str,
        handler_full_name: str,
        plugin_name: str,
        *,
        status: str | None = None,
        resolution: str | None = None,
        resolved_command: str | None = None,
        note: str | None = None,
        extra_data: dict | None = None,
        auto_generated: bool | None = None,
    ) -> CommandConflict:
        async def _op(session: AsyncSession) -> CommandConflict:
            result = await session.execute(
                select(CommandConflict).where(
                    CommandConflict.conflict_key == conflict_key,
                    CommandConflict.handler_full_name == handler_full_name,
                ),
            )
            record = result.scalar_one_or_none()
            if not record:
                record = self._new_command_conflict(
                    conflict_key,
                    handler_full_name,
                    plugin_name,
                    status=status,
                    resolution=resolution,
                    resolved_command=resolved_command,
                    note=note,
                    extra_data=extra_data,
                    auto_generated=auto_generated,
                )
                session.add(record)
            else:
                self._apply_updates(
                    record,
                    plugin_name=plugin_name,
                    status=status,
                    resolution=resolution,
                    resolved_command=resolved_command,
                    note=note,
                    extra_data=extra_data,
                    auto_generated=auto_generated,
                )
            await session.flush()
            await session.refresh(record)
            return record

        return await self._run_in_tx(_op)

    async def delete_command_conflicts(self, ids: list[int]) -> None:
        if not ids:
            return

        async def _op(session: AsyncSession) -> None:
            await session.execute(
                delete(CommandConflict).where(col(CommandConflict.id).in_(ids)),
            )

        await self._run_in_tx(_op)

    # ====
    # Deprecated Methods
    # ====

    def get_base_stats(self, offset_sec=86400):
        """Get base statistics within the specified offset in seconds."""

        async def _inner():
            async with self.get_db() as session:
                session: AsyncSession
                now = datetime.now()
                start_time = now - timedelta(seconds=offset_sec)
                result = await session.execute(
                    select(PlatformStat).where(PlatformStat.timestamp >= start_time),
                )
                all_datas = result.scalars().all()
                deprecated_stats = DeprecatedStats()
                for data in all_datas:
                    deprecated_stats.platform.append(
                        DeprecatedPlatformStat(
                            name=data.platform_id,
                            count=data.count,
                            timestamp=int(data.timestamp.timestamp()),
                        ),
                    )
                return deprecated_stats

        result = None

        def runner():
            nonlocal result
            result = asyncio.run(_inner())

        t = threading.Thread(target=runner)
        t.start()
        t.join()
        return result

    def get_total_message_count(self):
        """Get the total message count from platform statistics."""

        async def _inner():
            async with self.get_db() as session:
                session: AsyncSession
                result = await session.execute(
                    select(func.sum(PlatformStat.count)).select_from(PlatformStat),
                )
                total_count = result.scalar_one_or_none()
                return total_count if total_count is not None else 0

        result = None

        def runner():
            nonlocal result
            result = asyncio.run(_inner())

        t = threading.Thread(target=runner)
        t.start()
        t.join()
        return result

    def get_grouped_base_stats(self, offset_sec=86400):
        # group by platform_id
        async def _inner():
            async with self.get_db() as session:
                session: AsyncSession
                now = datetime.now()
                start_time = now - timedelta(seconds=offset_sec)
                result = await session.execute(
                    select(PlatformStat.platform_id, func.sum(PlatformStat.count))
                    .where(PlatformStat.timestamp >= start_time)
                    .group_by(PlatformStat.platform_id),
                )
                grouped_stats = result.all()
                deprecated_stats = DeprecatedStats()
                for platform_id, count in grouped_stats:
                    deprecated_stats.platform.append(
                        DeprecatedPlatformStat(
                            name=platform_id,
                            count=count,
                            timestamp=int(start_time.timestamp()),
                        ),
                    )
                return deprecated_stats

        result = None

        def runner():
            nonlocal result
            result = asyncio.run(_inner())

        t = threading.Thread(target=runner)
        t.start()
        t.join()
        return result

    # ====
    # Platform Session Management
    # ====

    async def create_platform_session(
        self,
        creator: str,
        platform_id: str = "webchat",
        session_id: str | None = None,
        display_name: str | None = None,
        is_group: int = 0,
    ) -> PlatformSession:
        """Create a new Platform session."""
        kwargs = {}
        if session_id:
            kwargs["session_id"] = session_id

        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_session = PlatformSession(
                    creator=creator,
                    platform_id=platform_id,
                    display_name=display_name,
                    is_group=is_group,
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
        async with self.get_db() as session:
            session: AsyncSession
            query = select(PlatformSession).where(
                PlatformSession.session_id == session_id,
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

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
        async with self.get_db() as session:
            session: AsyncSession
            offset = (page - 1) * page_size

            # LEFT JOIN with SessionProjectRelation and ChatUIProject to get project info
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
                    col(SessionProjectRelation.project_id)
                    == col(ChatUIProject.project_id),
                )
                .where(col(PlatformSession.creator) == creator)
            )

            if platform_id:
                query = query.where(PlatformSession.platform_id == platform_id)

            query = (
                query.order_by(desc(PlatformSession.updated_at))
                .offset(offset)
                .limit(page_size)
            )
            result = await session.execute(query)

            # Convert to list of dicts with session and project info
            sessions_with_projects = []
            for row in result.all():
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

    async def update_platform_session(
        self,
        session_id: str,
        display_name: str | None = None,
    ) -> None:
        """Update a Platform session's updated_at timestamp and optionally display_name."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                values: dict[str, T.Any] = {"updated_at": datetime.now(timezone.utc)}
                if display_name is not None:
                    values["display_name"] = display_name

                await session.execute(
                    update(PlatformSession)
                    .where(col(PlatformSession.session_id) == session_id)
                    .values(**values),
                )

    async def delete_platform_session(self, session_id: str) -> None:
        """Delete a Platform session by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(PlatformSession).where(
                        col(PlatformSession.session_id) == session_id,
                    ),
                )

    # ====
    # ChatUI Project Management
    # ====

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
                values: dict[str, T.Any] = {"updated_at": datetime.now(timezone.utc)}
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
