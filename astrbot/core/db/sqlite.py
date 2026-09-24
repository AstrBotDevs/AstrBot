import asyncio
import json
import sqlite3
import threading
import typing as T
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from deprecated import deprecated
from sqlalchemy import CursorResult, Row, case, literal, not_
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from sqlalchemy.orm.attributes import set_committed_value
from sqlmodel import col, delete, desc, func, or_, select, text, update

from astrbot.core import conversation_history_limits
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import (
    ApiKey,
    Attachment,
    ChatUIProject,
    CommandConfig,
    CommandConflict,
    ConversationImageCheckpoint,
    ConversationImageRef,
    ConversationV2,
    CronJob,
    ImageAsset,
    Persona,
    PersonaFolder,
    PlatformMessageHistory,
    PlatformSession,
    PlatformStat,
    Preference,
    ProviderStat,
    SessionProjectRelation,
    SQLModel,
    UmoAlias,
    WebChatThread,
)
from astrbot.core.db.po import (
    Platform as DeprecatedPlatformStat,
)
from astrbot.core.db.po import (
    Stats as DeprecatedStats,
)
from astrbot.core.sentinels import NOT_GIVEN

TxResult = T.TypeVar("TxResult")
CRON_FIELD_NOT_SET = object()


def _conversation_history_size():
    """Build the SQL expression used for stored JSON byte-limit checks.

    Returns:
        SQL expression measuring the persisted JSON bytes.
    """
    return conversation_history_limits.history_size_bytes(ConversationV2.content)


def _webchat_session_title_match(keyword: str):
    """Build a correlated EXISTS condition matching WebChat session titles.

    WebChat generates its title on the platform session instead of the
    conversation row, so the conversation is matched through the unified
    message origin suffix ``!<session_id>``.

    Args:
        keyword: Search text matched against the session display name.

    Returns:
        A SQLAlchemy EXISTS expression usable inside a conversation query.
    """
    return (
        select(1)
        .where(col(PlatformSession.display_name).ilike(f"%{keyword}%"))
        .where(
            col(ConversationV2.user_id).like(
                literal("%!").concat(col(PlatformSession.session_id)),
            )
        )
        .exists()
    )


def _authorized_image_catalog(conversation_id: str, user_id: str, platform_id: str):
    """Build the shared metadata-only authorization query.

    Args:
        conversation_id: Server-selected conversation.
        user_id: Server-selected owner.
        platform_id: Server-selected platform.

    Returns:
        A query for active references, checkpoint order and asset state.
    """
    return (
        select(
            ConversationImageRef, ConversationImageCheckpoint.sequence, ImageAsset.state
        )
        .join(
            ConversationV2,
            ConversationV2.conversation_id == ConversationImageRef.conversation_id,
        )
        .join(
            ConversationImageCheckpoint,
            (
                ConversationImageCheckpoint.conversation_id
                == ConversationImageRef.conversation_id
            )
            & (
                ConversationImageCheckpoint.checkpoint_id
                == ConversationImageRef.checkpoint_id
            ),
        )
        .join(ImageAsset, ImageAsset.asset_id == ConversationImageRef.asset_id)
        .where(
            ConversationImageRef.conversation_id == conversation_id,
            ConversationV2.user_id == user_id,
            ConversationV2.platform_id == platform_id,
            ConversationImageCheckpoint.active == True,  # noqa: E712
        )
    )


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
            await conn.execute(text("PRAGMA busy_timeout=30000"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=20000"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
            await conn.execute(text("PRAGMA mmap_size=134217728"))
            await conn.execute(text("PRAGMA optimize"))
            # 确保 personas 表有 folder_id、sort_order、skills 列（前向兼容）
            await self._ensure_persona_folder_columns(conn)
            await self._ensure_persona_skills_column(conn)
            await self._ensure_persona_custom_error_message_column(conn)
            await self._ensure_platform_message_history_checkpoint_column(conn)
            await self._ensure_chatui_project_workspace_columns(conn)
            await self._ensure_conversation_indexes(conn)
            columns = await conn.execute(text("PRAGMA table_info(provider_stats)"))
            if "request_details" not in {row[1] for row in columns.fetchall()}:
                await conn.execute(
                    text(
                        "ALTER TABLE provider_stats ADD COLUMN request_details JSON NOT NULL DEFAULT '{}'"
                    )
                )
            # The table-level unique constraint already provides an index for UMO
            # lookups. Older schemas also created this redundant explicit index.
            await conn.execute(text("DROP INDEX IF EXISTS ix_umo_aliases_umo"))
            await conn.commit()

    async def _ensure_conversation_indexes(self, conn) -> None:
        """Create indexes used by the dashboard conversation list.

        Args:
            conn: Active SQLAlchemy connection used during SQLite initialization.
        """
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_conversations_created_at_inner_id "
                "ON conversations (created_at DESC, inner_conversation_id DESC)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_conversations_platform_created_at_inner_id "
                "ON conversations (platform_id, created_at DESC, inner_conversation_id DESC)"
            )
        )

    async def _ensure_persona_folder_columns(self, conn) -> None:
        """确保 personas 表有 folder_id 和 sort_order 列。

        这是为了支持旧版数据库的平滑升级。新版数据库通过 SQLModel
        的 metadata.create_all 自动创建这些列。
        """
        result = await conn.execute(text("PRAGMA table_info(personas)"))
        columns = {row[1] for row in result.fetchall()}

        if "folder_id" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE personas ADD COLUMN folder_id VARCHAR(36) DEFAULT NULL"
                )
            )
        if "sort_order" not in columns:
            await conn.execute(
                text("ALTER TABLE personas ADD COLUMN sort_order INTEGER DEFAULT 0")
            )

    async def _ensure_persona_skills_column(self, conn) -> None:
        """确保 personas 表有 skills 列。

        这是为了支持旧版数据库的平滑升级。新版数据库通过 SQLModel
        的 metadata.create_all 自动创建这些列。
        """
        result = await conn.execute(text("PRAGMA table_info(personas)"))
        columns = {row[1] for row in result.fetchall()}

        if "skills" not in columns:
            await conn.execute(text("ALTER TABLE personas ADD COLUMN skills JSON"))

    async def _ensure_persona_custom_error_message_column(self, conn) -> None:
        """确保 personas 表有 custom_error_message 列。"""
        result = await conn.execute(text("PRAGMA table_info(personas)"))
        columns = {row[1] for row in result.fetchall()}

        if "custom_error_message" not in columns:
            await conn.execute(
                text("ALTER TABLE personas ADD COLUMN custom_error_message TEXT")
            )

    async def _ensure_platform_message_history_checkpoint_column(self, conn) -> None:
        """Ensure platform_message_history has llm_checkpoint_id."""
        result = await conn.execute(text("PRAGMA table_info(platform_message_history)"))
        columns = {row[1] for row in result.fetchall()}

        if "llm_checkpoint_id" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE platform_message_history "
                    "ADD COLUMN llm_checkpoint_id VARCHAR DEFAULT NULL"
                )
            )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_platform_message_history_llm_checkpoint_id "
                "ON platform_message_history (llm_checkpoint_id)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_platform_message_history_platform_user_id "
                "ON platform_message_history (platform_id, user_id, id)"
            )
        )

    async def _ensure_chatui_project_workspace_columns(self, conn) -> None:
        """Ensure chatui_projects has workspace configuration columns."""
        result = await conn.execute(text("PRAGMA table_info(chatui_projects)"))
        columns = {row[1] for row in result.fetchall()}

        if "workspace_type" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE chatui_projects "
                    "ADD COLUMN workspace_type VARCHAR(32) NOT NULL DEFAULT 'session'"
                )
            )
        if "workspace_path" not in columns:
            await conn.execute(
                text("ALTER TABLE chatui_projects ADD COLUMN workspace_path VARCHAR")
            )
        await conn.execute(
            text(
                "UPDATE chatui_projects SET "
                "workspace_type = CASE "
                "WHEN LOWER(workspace_type) = 'custom' THEN 'project' "
                "ELSE workspace_type END, "
                "workspace_path = NULL "
                "WHERE SUBSTR(creator, 1, 8) = 'api_key:' "
                "AND (LOWER(workspace_type) = 'custom' OR workspace_path IS NOT NULL)"
            )
        )

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

    async def insert_provider_stat(
        self,
        *,
        umo: str,
        provider_id: str,
        provider_model: str | None = None,
        conversation_id: str | None = None,
        status: str = "completed",
        stats: dict | None = None,
        agent_type: str = "internal",
    ) -> ProviderStat:
        """Insert a provider stat record for a single agent response."""
        stats = stats or {}
        token_usage = stats.get("token_usage", {})

        token_input_other = int(token_usage.get("input_other", 0) or 0)
        token_input_cached = int(token_usage.get("input_cached", 0) or 0)
        token_output = int(token_usage.get("output", 0) or 0)

        start_time = float(stats.get("start_time", 0.0) or 0.0)
        end_time = float(stats.get("end_time", 0.0) or 0.0)
        time_to_first_token = float(stats.get("time_to_first_token", 0.0) or 0.0)

        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                record = ProviderStat(
                    agent_type=agent_type,
                    status=status,
                    umo=umo,
                    conversation_id=conversation_id,
                    provider_id=provider_id,
                    provider_model=provider_model,
                    token_input_other=token_input_other,
                    token_input_cached=token_input_cached,
                    token_output=token_output,
                    start_time=start_time,
                    end_time=end_time,
                    time_to_first_token=time_to_first_token,
                    request_details=stats.get("image_request", {}),
                )
                session.add(record)
                await session.flush()
                await session.refresh(record)
                return record

    # ====
    # Conversation Management
    # ====

    async def _conversation_with_history(self, session, cid, *conditions):
        """Load one history only when SQLite reports it within the byte limit.

        Args:
            session: Active async database session.
            cid: Conversation identity.
            conditions: Additional SQL predicates for identity authorization.

        Returns:
            The conversation with its history, or None if it does not exist.

        Raises:
            HistoryTooLargeError: The persisted JSON exceeds the online limit.
            ValueError: The row changed repeatedly during the bounded read.
        """
        max_bytes = conversation_history_limits.MAX_ONLINE_HISTORY_BYTES
        history_size = _conversation_history_size()
        byte_size = (
            await session.execute(
                select(history_size)
                .where(ConversationV2.conversation_id == cid)
                .where(*conditions)
            )
        ).scalar_one_or_none()
        if byte_size is None:
            return None
        if byte_size > max_bytes:
            raise conversation_history_limits.HistoryTooLargeError(
                cid, byte_size, max_bytes
            )

        query = (
            select(ConversationV2)
            .where(
                ConversationV2.conversation_id == cid,
                history_size <= max_bytes,
                *conditions,
            )
            .execution_options(populate_existing=True)
        )
        result = await session.execute(query)
        conversation = result.scalar_one_or_none()
        if conversation is not None:
            return conversation

        current_size = (
            await session.execute(
                select(history_size)
                .where(ConversationV2.conversation_id == cid)
                .where(*conditions)
            )
        ).scalar_one_or_none()
        if current_size is None:
            return None
        if current_size > max_bytes:
            raise conversation_history_limits.HistoryTooLargeError(
                cid, current_size, max_bytes
            )
        result = await session.execute(query)
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise ValueError("Conversation history changed while it was being loaded")
        return conversation

    async def _conversation_without_history(self, session, cid):
        """Load conversation metadata without selecting or lazy-loading content.

        Args:
            session: Active async database session.
            cid: Conversation identity.

        Returns:
            A conversation with ``content=None``, or None if it does not exist.
        """
        result = await session.execute(
            select(ConversationV2)
            .options(defer(ConversationV2.content))
            .where(ConversationV2.conversation_id == cid)
        )
        conversation = result.scalar_one_or_none()
        if conversation is not None:
            set_committed_value(conversation, "content", None)
        return conversation

    async def _conversation_rows(self, session, query, *, include_history):
        """Materialize a query while enforcing the SQL-side history limit.

        Args:
            session: Active async database session.
            query: Ordered ConversationV2 query, including its filters and page.
            include_history: Whether to return bounded history bodies.

        Returns:
            Conversation rows; metadata-only rows have ``content=None``.

        Raises:
            HistoryTooLargeError: A selected history exceeds the online byte limit.
            ValueError: A history changed while it was being loaded.
        """
        if not include_history:
            result = await session.execute(query.options(defer(ConversationV2.content)))
            conversations = result.scalars().all()
            for conversation in conversations:
                set_committed_value(conversation, "content", None)
            return conversations

        max_bytes = conversation_history_limits.MAX_ONLINE_HISTORY_BYTES
        history_size = _conversation_history_size()
        size_query = query.with_only_columns(
            ConversationV2.conversation_id,
            history_size.label("history_byte_size"),
            maintain_column_froms=True,
        )
        size_rows = (await session.execute(size_query)).all()
        if not size_rows:
            return []
        for cid, byte_size in size_rows:
            if byte_size > max_bytes:
                raise conversation_history_limits.HistoryTooLargeError(
                    cid, byte_size, max_bytes
                )

        result = await session.execute(
            query.where(history_size <= max_bytes).execution_options(
                populate_existing=True
            )
        )
        conversations = result.scalars().all()
        conversations_by_id = {
            conversation.conversation_id: conversation for conversation in conversations
        }
        missing_ids = [
            cid for cid, _byte_size in size_rows if cid not in conversations_by_id
        ]
        if missing_ids:
            current_sizes = (
                await session.execute(
                    select(
                        ConversationV2.conversation_id,
                        history_size.label("history_byte_size"),
                    ).where(ConversationV2.conversation_id.in_(missing_ids))
                )
            ).all()
            current_size_by_id = dict(current_sizes)
            for cid, byte_size in current_sizes:
                if byte_size > max_bytes:
                    raise conversation_history_limits.HistoryTooLargeError(
                        cid, byte_size, max_bytes
                    )
            still_present = [cid for cid in missing_ids if cid in current_size_by_id]
            if still_present:
                latest = await session.execute(
                    query.where(
                        ConversationV2.conversation_id.in_(still_present),
                        history_size <= max_bytes,
                    ).execution_options(populate_existing=True)
                )
                conversations_by_id.update(
                    {
                        conversation.conversation_id: conversation
                        for conversation in latest.scalars().all()
                    }
                )
                unresolved = set(still_present) - conversations_by_id.keys()
                if unresolved:
                    raise ValueError(
                        "Conversation history changed while it was being loaded"
                    )

        return [
            conversations_by_id[cid]
            for cid, _byte_size in size_rows
            if cid in conversations_by_id
        ]

    async def get_conversations(
        self,
        user_id=None,
        platform_id=None,
        *,
        include_history=True,
    ):
        async with self.get_db() as session:
            session: AsyncSession
            query = select(ConversationV2)

            if user_id:
                query = query.where(ConversationV2.user_id == user_id)
            if platform_id:
                query = query.where(ConversationV2.platform_id == platform_id)
            # order by
            query = query.order_by(desc(ConversationV2.created_at))
            return await self._conversation_rows(
                session,
                query,
                include_history=include_history,
            )

    async def get_conversation_by_id(self, cid, *, include_history=True):
        async with self.get_db() as session:
            if not include_history:
                return await self._conversation_without_history(session, cid)
            return await self._conversation_with_history(session, cid)

    async def get_all_conversations(
        self,
        page=1,
        page_size=20,
        *,
        include_history=True,
    ):
        async with self.get_db() as session:
            session: AsyncSession
            offset = (page - 1) * page_size
            query = (
                select(ConversationV2)
                .order_by(desc(ConversationV2.created_at))
                .offset(offset)
                .limit(page_size)
            )
            return await self._conversation_rows(
                session,
                query,
                include_history=include_history,
            )

    async def get_filtered_conversations(
        self,
        page=1,
        page_size=20,
        platform_ids=None,
        search_query="",
        include_history=True,
        **kwargs,
    ):
        async with self.get_db() as session:
            session: AsyncSession
            # Build the base query with filters
            base_query = select(ConversationV2)
            conditions = []

            if platform_ids:
                conditions.append(col(ConversationV2.platform_id).in_(platform_ids))
            # WebChat titles live on the platform session, not on the
            # conversation row, so the search also matches session titles.
            if search_query:
                escaped_search_query = json.dumps(
                    search_query,
                    ensure_ascii=True,
                )[1:-1]
                conditions.append(
                    or_(
                        col(ConversationV2.title).ilike(f"%{search_query}%"),
                        col(ConversationV2.user_id).ilike(f"%{search_query}%"),
                        col(ConversationV2.conversation_id).ilike(f"%{search_query}%"),
                        col(ConversationV2.content).ilike(f"%{search_query}%"),
                        col(ConversationV2.content).ilike(f"%{escaped_search_query}%"),
                        _webchat_session_title_match(search_query),
                    )
                )
            keyword_query = str(kwargs.get("keyword_query") or "").strip()
            if keyword_query:
                escaped_keyword_query = json.dumps(
                    keyword_query,
                    ensure_ascii=True,
                )[1:-1]
                conditions.append(
                    or_(
                        col(ConversationV2.title).ilike(f"%{keyword_query}%"),
                        col(ConversationV2.content).ilike(f"%{keyword_query}%"),
                        col(ConversationV2.content).ilike(f"%{escaped_keyword_query}%"),
                        _webchat_session_title_match(keyword_query),
                    )
                )
            message_types = kwargs.get("message_types") or []
            if message_types:
                conditions.append(
                    or_(
                        *(
                            col(ConversationV2.user_id).like(f"%:{msg_type}:%")
                            for msg_type in message_types
                        )
                    )
                )
            platforms = kwargs.get("platforms") or []
            if platforms:
                conditions.append(col(ConversationV2.platform_id).in_(platforms))
            exclude_ids = kwargs.get("exclude_ids") or []
            for exclude_id in exclude_ids:
                # Match the whole UMO or its platform segment only, so an id
                # like "astrbot" does not swallow platforms such as
                # "astrbotweb". Escape LIKE wildcards inside the id itself.
                escaped = (
                    exclude_id.replace("\\", "\\\\")
                    .replace("%", r"\%")
                    .replace("_", r"\_")
                )
                conditions.append(
                    not_(
                        or_(
                            col(ConversationV2.user_id) == exclude_id,
                            col(ConversationV2.user_id).like(
                                f"{escaped}:%", escape="\\"
                            ),
                        )
                    )
                )
            exclude_platforms = kwargs.get("exclude_platforms") or []
            if exclude_platforms:
                conditions.append(
                    not_(col(ConversationV2.platform_id).in_(exclude_platforms))
                )
            umo_query = str(kwargs.get("umo_query") or "").strip()
            if umo_query:
                conditions.append(col(ConversationV2.user_id).ilike(f"%{umo_query}%"))

            if conditions:
                base_query = base_query.where(*conditions)

            group_by_session = bool(kwargs.get("group_by_session", False))

            # Get total count matching the filters
            count_target = (
                func.distinct(ConversationV2.user_id)
                if group_by_session
                else ConversationV2.inner_conversation_id
            )
            count_query = select(func.count(count_target))
            if conditions:
                count_query = count_query.where(*conditions)
            total_count = await session.execute(count_query)
            total = total_count.scalar_one()

            # Get paginated results
            offset = (page - 1) * page_size
            sort_by = kwargs.get("sort_by", "created_at")
            sort_order = kwargs.get("sort_order", "desc")
            sort_column = (
                ConversationV2.updated_at
                if sort_by == "updated_at"
                else ConversationV2.created_at
            )
            order = sort_column.asc if sort_order == "asc" else sort_column.desc
            tie_breaker = (
                ConversationV2.inner_conversation_id.asc
                if sort_order == "asc"
                else ConversationV2.inner_conversation_id.desc
            )
            if group_by_session:
                session_sort = func.max(sort_column).label("session_sort")
                session_tie_breaker = func.max(
                    ConversationV2.inner_conversation_id
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
                    .limit(page_size)
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
            history_size = _conversation_history_size()
            selected_history_ids = []
            if include_history:
                max_bytes = conversation_history_limits.MAX_ONLINE_HISTORY_BYTES
                size_rows = (
                    await session.execute(
                        result_query.with_only_columns(
                            ConversationV2.conversation_id,
                            history_size.label("history_byte_size"),
                            maintain_column_froms=True,
                        )
                    )
                ).all()
                selected_history_ids = [cid for cid, _size in size_rows]
                for cid, byte_size in size_rows:
                    if byte_size > max_bytes:
                        raise conversation_history_limits.HistoryTooLargeError(
                            cid, byte_size, max_bytes
                        )
                result_query = result_query.where(history_size <= max_bytes)
            else:
                result_query = result_query.options(defer(ConversationV2.content))
            bounded_result_query = result_query
            if (
                not group_by_session
                and sort_by == "created_at"
                and (len(platforms) > 1 or len(platform_ids or []) > 1)
            ):
                # SQLite may choose the narrow platform index for IN queries and
                # then materialize a temporary sort. Force the global ordering
                # index for multi-platform pages while keeping ORM row mapping.
                compiled = result_query.compile(
                    dialect=sqlite_dialect(paramstyle="named"),
                    compile_kwargs={"render_postcompile": True},
                )
                indexed_sql = compiled.string.replace(
                    "FROM conversations",
                    "FROM conversations INDEXED BY "
                    "ix_conversations_created_at_inner_id",
                    1,
                )
                conversation_columns = [
                    column
                    for column in ConversationV2.__table__.columns
                    if include_history or column.name != "content"
                ]
                result_query = select(ConversationV2).from_statement(
                    text(indexed_sql).columns(*conversation_columns),
                )
                if not include_history:
                    result_query = result_query.options(
                        defer(ConversationV2.content),
                    )
                result = await session.execute(
                    result_query.execution_options(populate_existing=True),
                    compiled.params,
                )
            else:
                result = await session.execute(
                    result_query.execution_options(populate_existing=True)
                    if include_history
                    else result_query
                )
            conversations = result.scalars().all()
            if include_history:
                conversations_by_id = {
                    conversation.conversation_id: conversation
                    for conversation in conversations
                }
                missing_ids = [
                    cid
                    for cid in selected_history_ids
                    if cid not in conversations_by_id
                ]
                if missing_ids:
                    current_sizes = (
                        await session.execute(
                            select(
                                ConversationV2.conversation_id,
                                history_size.label("history_byte_size"),
                            ).where(ConversationV2.conversation_id.in_(missing_ids))
                        )
                    ).all()
                    current_size_by_id = dict(current_sizes)
                    for cid, byte_size in current_sizes:
                        if byte_size > max_bytes:
                            raise conversation_history_limits.HistoryTooLargeError(
                                cid, byte_size, max_bytes
                            )
                    still_present = [
                        cid for cid in missing_ids if cid in current_size_by_id
                    ]
                    if still_present:
                        latest = await session.execute(
                            bounded_result_query.where(
                                ConversationV2.conversation_id.in_(still_present),
                                history_size <= max_bytes,
                            ).execution_options(populate_existing=True)
                        )
                        conversations_by_id.update(
                            {
                                conversation.conversation_id: conversation
                                for conversation in latest.scalars().all()
                            }
                        )
                        if set(still_present) - conversations_by_id.keys():
                            raise ValueError(
                                "Conversation history changed while it was being loaded"
                            )
                conversations = [
                    conversations_by_id[cid]
                    for cid in selected_history_ids
                    if cid in conversations_by_id
                ]
            else:
                for conversation in conversations:
                    set_committed_value(conversation, "content", None)

            return conversations, total

    async def get_conversation_platform_ids(self) -> list[str]:
        """Return distinct platform IDs referenced by conversation history.

        Returns:
            Sorted platform IDs that have at least one conversation.
        """
        async with self.get_db() as session:
            result = await session.execute(
                select(ConversationV2.platform_id)
                .distinct()
                .order_by(ConversationV2.platform_id)
            )
            return [platform_id for platform_id in result.scalars() if platform_id]

    async def list_conversation_images(
        self,
        conversation_id: str,
        *,
        user_id: str,
        platform_id: str,
        limit: int = 20,
        cursor: tuple[int, str] | None = None,
        source_message_id: str | None = None,
        query: str | None = None,
    ) -> tuple[list[dict], tuple[int, str] | None]:
        """List a bounded, authorized metadata page in stable database order.

        Args:
            conversation_id: Server-selected conversation.
            user_id: Server-selected owner.
            platform_id: Server-selected platform.
            limit: Page size, between one and twenty.
            cursor: Exclusive previous checkpoint sequence and occurrence ID.
            source_message_id: Optional exact platform source message.
            query: Optional literal description or annotation substring.

        Returns:
            Metadata rows with bounded text snippets and an optional next cursor.

        Raises:
            ValueError: A pagination or filter input exceeds its bounds.
        """
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Image catalog limit must be between 1 and 20")
        if cursor is not None and (
            not isinstance(cursor, tuple)
            or len(cursor) != 2
            or type(cursor[0]) is not int
            or cursor[0] <= 0
            or not isinstance(cursor[1], str)
            or not 1 <= len(cursor[1]) <= 128
        ):
            raise ValueError("Invalid image catalog cursor")
        if query is not None and (not isinstance(query, str) or len(query) > 256):
            raise ValueError("Image catalog query exceeds 256 characters")
        if source_message_id is not None and (
            not isinstance(source_message_id, str) or len(source_message_id) > 512
        ):
            raise ValueError("Image source message ID exceeds 512 characters")
        statement = _authorized_image_catalog(conversation_id, user_id, platform_id)
        if cursor is not None:
            sequence, occurrence = cursor
            statement = statement.where(
                or_(
                    ConversationImageCheckpoint.sequence > sequence,
                    (ConversationImageCheckpoint.sequence == sequence)
                    & (ConversationImageRef.occurrence_id > occurrence),
                )
            )
        if source_message_id is not None:
            statement = statement.where(
                ConversationImageRef.source_message_id == source_message_id
            )
        if query:
            statement = statement.where(
                or_(
                    col(ConversationImageRef.description).contains(
                        query, autoescape=True
                    ),
                    col(ConversationImageRef.user_annotation).contains(
                        query, autoescape=True
                    ),
                )
            )
        statement = statement.order_by(
            ConversationImageCheckpoint.sequence, ConversationImageRef.occurrence_id
        ).limit(limit + 1)
        async with self.get_db() as session:
            rows = (await session.execute(statement)).all()
        result = []
        for ref, sequence, state in rows[:limit]:
            item = ref.model_dump()
            item.update(checkpoint_sequence=sequence, asset_state=state)
            item["description"] = item["description"][:512]
            item["user_annotation"] = item["user_annotation"][:512]
            result.append(item)
        next_cursor = (
            (rows[limit - 1][1], rows[limit - 1][0].occurrence_id)
            if len(rows) > limit
            else None
        )
        return result, next_cursor

    async def get_conversation_images(
        self,
        conversation_id: str,
        occurrence_ids: list[str],
        *,
        user_id: str,
        platform_id: str,
        available_only: bool = False,
    ) -> list[ConversationImageRef]:
        """Read up to one hundred authorized current description records.

        Args:
            conversation_id: Server-selected conversation.
            occurrence_ids: Bounded IDs to resolve, never authorization grants.
            user_id: Server-selected owner.
            platform_id: Server-selected platform.
            available_only: Require a readable asset for a pending visual submission.

        Returns:
            Matching active records without loading conversation history.

        Raises:
            ValueError: IDs exceed the batch or identifier bounds.
        """
        if (
            not isinstance(occurrence_ids, (list, tuple))
            or len(occurrence_ids) > 100
            or any(
                not isinstance(item, str) or not 1 <= len(item) <= 128
                for item in occurrence_ids
            )
        ):
            raise ValueError("Image lookup requires at most 100 bounded occurrence IDs")
        if not occurrence_ids:
            return []
        statement = _authorized_image_catalog(
            conversation_id, user_id, platform_id
        ).where(col(ConversationImageRef.occurrence_id).in_(occurrence_ids))
        if available_only:
            statement = statement.where(ImageAsset.state == "available")
        async with self.get_db() as session:
            return list((await session.execute(statement)).scalars())

    async def update_image_description(
        self,
        conversation_id: str,
        occurrence_id: str,
        *,
        user_id: str,
        platform_id: str,
        expected_checkpoint_id: str,
        expected_version: int,
        description: str,
        status: str,
        provider: str | None,
        model: str | None,
        representation: str | None,
    ) -> bool:
        """Commit a description only if its authorized turn and version still match.

        Args:
            conversation_id: Server-selected conversation.
            occurrence_id: Existing occurrence to update.
            user_id: Server-selected owner.
            platform_id: Server-selected platform.
            expected_checkpoint_id: Turn observed before the external model call.
            expected_version: Description revision observed before that call.
            description: Validated observation of at most 4096 characters.
            status: Pending, ready or failed observation status.
            provider: Provider identity, at most 256 characters.
            model: Model identity, at most 256 characters.
            representation: Inspected representation, at most 256 characters.

        Returns:
            Whether the conditional update succeeded, without resurrecting rows.

        Raises:
            ValueError: Description or provenance metadata is invalid.
        """
        from astrbot.core.image_asset_store import image_store_lock

        if (
            type(expected_version) is not int
            or expected_version < 0
            or not expected_checkpoint_id
            or status not in {"pending", "ready", "failed"}
            or not isinstance(description, str)
            or len(description) > 4096
            or (status == "ready" and not description.strip())
            or any(
                value is not None and (not isinstance(value, str) or len(value) > 256)
                for value in (provider, model, representation)
            )
        ):
            raise ValueError("Invalid image description metadata")
        async with image_store_lock():
            async with self.get_db() as session, session.begin():
                statement = _authorized_image_catalog(
                    conversation_id, user_id, platform_id
                ).where(
                    ConversationImageRef.occurrence_id == occurrence_id,
                    ConversationImageRef.checkpoint_id == expected_checkpoint_id,
                    ConversationImageRef.description_version == expected_version,
                    ImageAsset.state == "available",
                )
                ref = (await session.execute(statement)).scalar_one_or_none()
                if ref is None or (
                    ref.description_status == "ready" and status != "ready"
                ):
                    return False
                result = await session.execute(
                    update(ConversationImageRef)
                    .where(
                        ConversationImageRef.conversation_id == conversation_id,
                        ConversationImageRef.occurrence_id == occurrence_id,
                        ConversationImageRef.checkpoint_id == expected_checkpoint_id,
                        ConversationImageRef.description_version == expected_version,
                    )
                    .values(
                        description=description,
                        description_status=status,
                        description_version=expected_version + 1,
                        description_provider=provider,
                        description_model=model,
                        description_representation=representation,
                    )
                )
                return result.rowcount == 1

    async def update_image_annotation(
        self,
        conversation_id: str,
        occurrence_id: str,
        *,
        user_id: str,
        platform_id: str,
        expected_checkpoint_id: str,
        expected_annotation: str,
        annotation: str,
    ) -> bool:
        """Conditionally update user corrections independently from observations.

        Args:
            conversation_id: Server-selected conversation.
            occurrence_id: Existing occurrence to update.
            user_id: Server-selected owner.
            platform_id: Server-selected platform.
            expected_checkpoint_id: Expected active turn.
            expected_annotation: Previously read correction text.
            annotation: New user correction, at most 4096 characters.

        Returns:
            Whether the authorized field-level update succeeded.

        Raises:
            ValueError: Annotation text exceeds its bounds.
        """
        from astrbot.core.image_asset_store import image_store_lock

        if not expected_checkpoint_id or any(
            not isinstance(value, str) or len(value) > 4096
            for value in (expected_annotation, annotation)
        ):
            raise ValueError("Invalid image annotation")
        async with image_store_lock():
            async with self.get_db() as session, session.begin():
                statement = _authorized_image_catalog(
                    conversation_id, user_id, platform_id
                ).where(
                    ConversationImageRef.occurrence_id == occurrence_id,
                    ConversationImageRef.checkpoint_id == expected_checkpoint_id,
                    ConversationImageRef.user_annotation == expected_annotation,
                )
                ref = (await session.execute(statement)).scalar_one_or_none()
                if ref is None:
                    return False
                result = await session.execute(
                    update(ConversationImageRef)
                    .where(
                        ConversationImageRef.conversation_id == conversation_id,
                        ConversationImageRef.occurrence_id == occurrence_id,
                        ConversationImageRef.checkpoint_id == expected_checkpoint_id,
                        ConversationImageRef.user_annotation == expected_annotation,
                    )
                    .values(user_annotation=annotation)
                )
                return result.rowcount == 1

    async def _sync_image_history(
        self,
        session,
        conversation,
        content,
        *,
        image_refs=None,
        expected_history=None,
        prune_image_refs=False,
        image_checkpoint_replacement=None,
    ) -> tuple[set[str], set[str]]:
        """Validate and synchronize image metadata within the caller's transaction.

        Args:
            session: Active transaction protected by the image store lock.
            conversation: Conversation being changed.
            content: New history; None leaves it unchanged.
            image_refs: Trusted server-created association records, never JSON grants.
            expected_history: Optional optimistic concurrency snapshot.
            prune_image_refs: Explicit edit removes associations from deleted turns.
            image_checkpoint_replacement: Old/new checkpoint and retained user occurrences.

        Returns:
            Removed occurrences and invalidated checkpoints for post-commit notification.

        Raises:
            ValueError: History or checkpoint order is invalid or stale.
            PermissionError: An image lacks a valid conversation association.
        """
        from astrbot.core.agent.message import ImageRefPart, get_checkpoint_id

        previous = conversation.content or []
        if expected_history is not None and previous != expected_history:
            raise ValueError("Conversation history changed; reload before editing")
        history = previous if content is None else content
        cid = conversation.conversation_id
        checkpoints = list(
            (
                await session.execute(
                    select(ConversationImageCheckpoint).where(
                        ConversationImageCheckpoint.conversation_id == cid
                    )
                )
            ).scalars()
        )
        associations = {
            row.occurrence_id: row
            for row in (
                await session.execute(
                    select(ConversationImageRef).where(
                        ConversationImageRef.conversation_id == cid
                    )
                )
            ).scalars()
        }
        strict_order = bool(associations or image_refs)
        # Text-only history can be edited by legacy callers without image flags.
        # Normalize only when its visible order conflicts with the ledger, avoiding
        # a full ledger rewrite on ordinary appends. There are no image grants to
        # invalidate. Regeneration uses the history before temporary truncation.
        ordered = {row.checkpoint_id: row for row in checkpoints}
        sequence = max((row.sequence for row in checkpoints), default=0)
        normalize_text_order = False
        if not associations:
            last_sequence = 0
            simulated = sequence
            seen = set()
            for message in previous if image_checkpoint_replacement else history:
                checkpoint_id = get_checkpoint_id(message)
                if not checkpoint_id:
                    continue
                row = ordered.get(checkpoint_id)
                if row is None:
                    simulated += 1
                position = row.sequence if row is not None else simulated
                if (
                    checkpoint_id in seen
                    or position <= last_sequence
                    or (row is not None and not row.active)
                ):
                    normalize_text_order = True
                seen.add(checkpoint_id)
                last_sequence = position
        if normalize_text_order:
            for checkpoint in checkpoints:
                await session.delete(checkpoint)
            await session.flush()
            ordered = {}
            sequence = 0
        # A previous text-only ordering cannot veto a newly normalized history.
        histories = (
            (previous, history)
            if associations or image_checkpoint_replacement
            else (history,)
        )
        for messages in histories:
            seen = set()
            last_sequence = 0
            for message in messages:
                checkpoint_id = get_checkpoint_id(message)
                if not checkpoint_id:
                    continue
                if checkpoint_id in seen:
                    if strict_order:
                        raise ValueError("Duplicate conversation checkpoint")
                    # Legacy duplicates have no image grants: the last marker is
                    # the effective boundary for latest-turn operations.
                    sequence += 1
                    ordered[checkpoint_id].sequence = sequence
                    continue
                seen.add(checkpoint_id)
                row = ordered.get(checkpoint_id)
                if row is None:
                    sequence += 1
                    row = ConversationImageCheckpoint(
                        conversation_id=cid,
                        checkpoint_id=checkpoint_id,
                        sequence=sequence,
                    )
                    session.add(row)
                    ordered[checkpoint_id] = row
                if strict_order and (not row.active or row.sequence <= last_sequence):
                    raise ValueError("Conversation checkpoint order is invalid")
                if not strict_order:
                    row.active = True
                last_sequence = row.sequence
        affected_assets = set()
        revoked_occurrences = set()
        revoked_checkpoints = set()
        if image_checkpoint_replacement is not None:
            old_id, new_id, retained = image_checkpoint_replacement
            old = ordered.get(old_id)
            if old is None or not old.active or new_id in ordered:
                raise ValueError("Invalid replacement checkpoint")
            if old.sequence != max(
                row.sequence for row in ordered.values() if row.active
            ):
                raise ValueError("Only the latest checkpoint can be replaced")
            sequence += 1
            replacement = ConversationImageCheckpoint(
                conversation_id=cid,
                checkpoint_id=new_id,
                sequence=sequence,
            )
            session.add(replacement)
            ordered[new_id] = replacement
            old.active = False
            revoked_checkpoints.add(old_id)
            retained_ids = set(retained)
            for occurrence_id in retained_ids:
                ref = associations.get(occurrence_id)
                if ref is None or ref.checkpoint_id != old_id:
                    raise PermissionError(
                        "Retained image does not belong to replaced turn"
                    )
            for occurrence_id, ref in list(associations.items()):
                if ref.checkpoint_id != old_id:
                    continue
                if occurrence_id in retained_ids:
                    ref.checkpoint_id = new_id
                else:
                    affected_assets.add(ref.asset_id)
                    await session.delete(ref)
                    revoked_occurrences.add(occurrence_id)
                    del associations[occurrence_id]
        if prune_image_refs:
            current_cp = {get_checkpoint_id(item) for item in history}
            removed_cp = (
                {get_checkpoint_id(item) for item in previous} - current_cp - {None}
            )
            if image_checkpoint_replacement:
                removed_cp.discard(image_checkpoint_replacement[0])
            old_occurrences = {
                part.get("occurrence_id")
                for item in previous
                if isinstance(item.get("content"), list)
                for part in item["content"]
                if isinstance(part, dict) and part.get("type") == "image_ref"
            }
            new_occurrences = {
                part.get("occurrence_id")
                for item in history
                if isinstance(item.get("content"), list)
                for part in item["content"]
                if isinstance(part, dict) and part.get("type") == "image_ref"
            }
            revoked_checkpoints.update(removed_cp)
            for cp in removed_cp:
                if cp in ordered:
                    ordered[cp].active = False
            for occurrence_id, ref in list(associations.items()):
                if (
                    ref.checkpoint_id in removed_cp
                    or occurrence_id in old_occurrences - new_occurrences
                ):
                    affected_assets.add(ref.asset_id)
                    await session.delete(ref)
                    revoked_occurrences.add(occurrence_id)
                    del associations[occurrence_id]
        for supplied in image_refs or []:
            if (
                not isinstance(supplied, ConversationImageRef)
                or supplied.conversation_id != cid
            ):
                raise PermissionError(
                    "Image association must belong to this conversation"
                )
            checkpoint = ordered.get(supplied.checkpoint_id)
            asset = await session.get(ImageAsset, supplied.asset_id)
            if (
                checkpoint is None
                or not checkpoint.active
                or asset is None
                or asset.state != "available"
            ):
                raise PermissionError(
                    "Image association requires an active turn and available asset"
                )
            existing = associations.get(supplied.occurrence_id)
            if existing is not None:
                if (
                    existing.asset_id != supplied.asset_id
                    or existing.checkpoint_id != supplied.checkpoint_id
                ):
                    raise PermissionError("Image occurrence cannot be reassigned")
                continue
            added = ConversationImageRef.model_validate(supplied.model_dump())
            session.add(added)
            associations[added.occurrence_id] = added
        pending_references = []
        for message in history:
            checkpoint_id = get_checkpoint_id(message)
            if checkpoint_id:
                if any(
                    ref.checkpoint_id != checkpoint_id for ref in pending_references
                ):
                    raise PermissionError("History image cannot move between turns")
                pending_references.clear()
                continue
            if not isinstance(message.get("content"), list):
                continue
            for part in message["content"]:
                if not isinstance(part, dict) or part.get("type") != "image_ref":
                    continue
                parsed = ImageRefPart.model_validate(part)
                ref = associations.get(parsed.occurrence_id)
                if ref is None or ref.asset_id != parsed.asset_id:
                    raise PermissionError(
                        "History image is not authorized in this conversation"
                    )
                checkpoint = ordered.get(ref.checkpoint_id)
                if checkpoint is None or not checkpoint.active:
                    raise PermissionError("History image belongs to an inactive turn")
                pending_references.append(ref)
        if pending_references:
            raise PermissionError("Persisted images require a closing turn checkpoint")
        await session.flush()
        asset_ids = list(affected_assets)
        for offset in range(0, len(asset_ids), 100):
            await session.execute(
                update(ImageAsset)
                .where(
                    col(ImageAsset.asset_id).in_(asset_ids[offset : offset + 100]),
                    ~select(ConversationImageRef.asset_id)
                    .where(ConversationImageRef.asset_id == ImageAsset.asset_id)
                    .exists(),
                )
                .values(state="pending_delete")
            )
        return revoked_occurrences, revoked_checkpoints

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
        *,
        image_branch_source=None,
    ):
        """Create a conversation and optionally inherit an authorized image catalog.

        Args:
            user_id: Destination conversation owner.
            platform_id: Destination platform.
            content: Initial persisted history.
            title: Optional title.
            persona_id: Optional persona.
            cid: Optional stable conversation ID.
            created_at: Optional original creation timestamp.
            updated_at: Optional original update timestamp.
            image_branch_source: Server-validated source CID, owner, platform and
                checkpoint boundary; never accept these as model-generated grants.

        Returns:
            The created conversation.

        Raises:
            PermissionError: Source identity or inherited images are unauthorized.
            ValueError: The branch boundary or history is invalid.
        """
        from astrbot.core.image_asset_store import image_store_lock

        kwargs = {}
        if cid:
            kwargs["conversation_id"] = cid
        if created_at:
            kwargs["created_at"] = created_at
        if updated_at:
            kwargs["updated_at"] = updated_at
        async with image_store_lock():
            async with self.get_db() as session, session.begin():
                new_conversation = ConversationV2(
                    user_id=user_id,
                    content=[],
                    platform_id=platform_id,
                    title=title,
                    persona_id=persona_id,
                    **kwargs,
                )
                session.add(new_conversation)
                await session.flush()
                if image_branch_source is not None:
                    source_cid, owner, source_platform, boundary = image_branch_source
                    source_identity = (
                        await session.execute(
                            select(ConversationV2.conversation_id).where(
                                ConversationV2.conversation_id == source_cid,
                                ConversationV2.user_id == owner,
                                ConversationV2.platform_id == source_platform,
                            )
                        )
                    ).scalar_one_or_none()
                    source = (
                        await self._conversation_with_history(
                            session,
                            source_cid,
                            ConversationV2.user_id == owner,
                            ConversationV2.platform_id == source_platform,
                        )
                        if source_identity is not None
                        else None
                    )
                    if source is None:
                        raise PermissionError("Source conversation is not authorized")
                    await self._sync_image_history(session, source, None)
                    boundary_row = await session.get(
                        ConversationImageCheckpoint, (source_cid, boundary)
                    )
                    if boundary_row is None or not boundary_row.active:
                        raise ValueError("Branch checkpoint is not active")
                    inherited = list(
                        (
                            await session.execute(
                                select(ConversationImageCheckpoint).where(
                                    ConversationImageCheckpoint.conversation_id
                                    == source_cid,
                                    ConversationImageCheckpoint.active == True,  # noqa: E712
                                    ConversationImageCheckpoint.sequence
                                    <= boundary_row.sequence,
                                )
                            )
                        ).scalars()
                    )
                    inherited_ids = {row.checkpoint_id for row in inherited}
                    from astrbot.core.agent.message import get_checkpoint_id

                    if any(
                        get_checkpoint_id(item) not in inherited_ids
                        for item in content or []
                        if get_checkpoint_id(item)
                    ):
                        raise PermissionError(
                            "Branch history exceeds its checkpoint boundary"
                        )
                    for row in inherited:
                        session.add(
                            ConversationImageCheckpoint(
                                conversation_id=new_conversation.conversation_id,
                                checkpoint_id=row.checkpoint_id,
                                sequence=row.sequence,
                            )
                        )
                    refs = (
                        await session.execute(
                            select(ConversationImageRef)
                            .join(
                                ConversationImageCheckpoint,
                                (
                                    ConversationImageCheckpoint.conversation_id
                                    == ConversationImageRef.conversation_id
                                )
                                & (
                                    ConversationImageCheckpoint.checkpoint_id
                                    == ConversationImageRef.checkpoint_id
                                ),
                            )
                            .where(
                                ConversationImageRef.conversation_id == source_cid,
                                ConversationImageCheckpoint.active == True,  # noqa: E712
                                ConversationImageCheckpoint.sequence
                                <= boundary_row.sequence,
                            )
                        )
                    ).scalars()
                    for ref in refs:
                        values = ref.model_dump()
                        values["conversation_id"] = new_conversation.conversation_id
                        session.add(ConversationImageRef.model_validate(values))
                    await session.flush()
                await self._sync_image_history(session, new_conversation, content or [])
                new_conversation.content = content or []
                return new_conversation

    async def update_conversation(
        self,
        cid,
        title=None,
        persona_id=None,
        content=None,
        token_usage=None,
        *,
        image_refs=None,
        expected_history=None,
        expected_identity=None,
        prune_image_refs=False,
        image_checkpoint_replacement=None,
    ):
        """Update conversation history and image grants in one transaction.

        Args:
            cid: Conversation identity.
            title: Optional replacement title.
            persona_id: Optional replacement persona.
            content: New history; omission preserves existing history and catalog.
            token_usage: Optional usage value.
            image_refs: Trusted association models with active turn and asset IDs.
            expected_history: Snapshot required by interactive edit callers.
            expected_identity: Expected (user_id, platform_id) checked in the
                same transaction before writing the conversation.
            prune_image_refs: Explicitly revoke references removed by an edit.
            image_checkpoint_replacement: Old checkpoint, new checkpoint and user
                occurrences retained while regenerating the last turn.

        Returns:
            The updated conversation, or None for an absent legacy target/no changes.

        Raises:
            ValueError: History is stale, ordering invalid or explicit target absent.
            PermissionError: An image reference lacks a matching authorization.
        """
        from astrbot.core.image_asset_store import image_store_lock

        if (
            content is None
            and image_refs is None
            and not prune_image_refs
            and image_checkpoint_replacement is None
            and expected_history is None
            and expected_identity is None
        ):
            values = {}
            if title is not None:
                values["title"] = title
            if persona_id is not None:
                values["persona_id"] = persona_id
            if token_usage is not None:
                values["token_usage"] = token_usage
            if values:
                async with self.get_db() as session, session.begin():
                    await session.execute(
                        update(ConversationV2)
                        .where(ConversationV2.conversation_id == cid)
                        .values(**values)
                    )
                return await self.get_conversation_by_id(
                    cid,
                    include_history=False,
                )
            return None
        revoked_occurrences, revoked_checkpoints = set(), set()
        async with image_store_lock():
            async with self.get_db() as session, session.begin():
                if expected_identity is not None or expected_history is not None:
                    # SQLite legacy mode does not start a transaction on SELECT.
                    # Reserve the writer before reading the identity/snapshot so
                    # another connection cannot change either before our commit.
                    await session.execute(text("BEGIN IMMEDIATE"))
                if expected_identity is not None:
                    identity_result = await session.execute(
                        select(
                            ConversationV2.user_id,
                            ConversationV2.platform_id,
                        ).where(ConversationV2.conversation_id == cid)
                    )
                    actual_identity = identity_result.one_or_none()
                    if actual_identity is None:
                        raise ValueError("Conversation not found")
                    if tuple(actual_identity) != expected_identity:
                        raise PermissionError(
                            "Conversation identity changed before the update"
                        )
                conversation = await self._conversation_with_history(session, cid)
                if conversation is None:
                    if (
                        image_refs is not None
                        or expected_history is not None
                        or expected_identity is not None
                        or prune_image_refs
                        or image_checkpoint_replacement
                    ):
                        raise ValueError("Conversation not found")
                    return None
                if (
                    content is not None
                    or image_refs is not None
                    or image_checkpoint_replacement
                    or prune_image_refs
                    or expected_history is not None
                ):
                    (
                        revoked_occurrences,
                        revoked_checkpoints,
                    ) = await self._sync_image_history(
                        session,
                        conversation,
                        content,
                        image_refs=image_refs,
                        expected_history=expected_history,
                        prune_image_refs=prune_image_refs,
                        image_checkpoint_replacement=image_checkpoint_replacement,
                    )
                if title is not None:
                    conversation.title = title
                if persona_id is not None:
                    conversation.persona_id = persona_id
                if content is not None:
                    conversation.content = content
                if token_usage is not None:
                    conversation.token_usage = token_usage
                if expected_identity is not None and content is not None:
                    # A migration can expand tiny inline images into larger
                    # references. Check the actual stored JSON before committing
                    # so a successful migration never creates unreadable history.
                    await session.flush()
                    byte_size = await session.scalar(
                        select(_conversation_history_size()).where(
                            ConversationV2.conversation_id == cid
                        )
                    )
                    max_bytes = conversation_history_limits.MAX_ONLINE_HISTORY_BYTES
                    if byte_size > max_bytes:
                        raise conversation_history_limits.HistoryTooLargeError(
                            cid, byte_size, max_bytes
                        )
            from astrbot.core.image_context import ImageTurnContext

            ImageTurnContext.notify_committed_change(
                self,
                cid,
                revoked_occurrences=revoked_occurrences,
                revoked_checkpoints=revoked_checkpoints,
                persisted_references=image_refs or (),
            )
        if prune_image_refs or image_checkpoint_replacement:
            from astrbot.core import logger
            from astrbot.core.image_asset_store import collect_pending_images

            try:
                await collect_pending_images(self)
            except Exception as exc:
                logger.warning(
                    "Image cleanup deferred after history update: %s",
                    type(exc).__name__,
                )
        return conversation

    async def _delete_image_conversations(self, *, cid=None, user_id=None) -> None:
        """Remove conversations and release image grants in one locked transaction.

        Args:
            cid: A single conversation identity.
            user_id: Owner whose conversations should all be removed.
        """
        from astrbot.core.image_asset_store import image_store_lock

        async with image_store_lock():
            async with self.get_db() as session, session.begin():
                condition = (
                    ConversationV2.conversation_id == cid
                    if cid is not None
                    else ConversationV2.user_id == user_id
                )
                conversations = select(ConversationV2.conversation_id).where(condition)
                removed_conversations = list(
                    (await session.execute(conversations)).scalars()
                )
                removed_assets = select(ConversationImageRef.asset_id).where(
                    col(ConversationImageRef.conversation_id).in_(conversations)
                )
                surviving_assets = select(ConversationImageRef.asset_id).where(
                    ~col(ConversationImageRef.conversation_id).in_(conversations)
                )
                await session.execute(
                    update(ImageAsset)
                    .where(
                        col(ImageAsset.asset_id).in_(removed_assets),
                        ~col(ImageAsset.asset_id).in_(surviving_assets),
                    )
                    .values(state="pending_delete")
                )
                await session.execute(
                    delete(ConversationImageRef).where(
                        col(ConversationImageRef.conversation_id).in_(conversations)
                    )
                )
                await session.execute(
                    delete(ConversationImageCheckpoint).where(
                        col(ConversationImageCheckpoint.conversation_id).in_(
                            conversations
                        )
                    )
                )
                await session.execute(delete(ConversationV2).where(condition))

            from astrbot.core.image_context import ImageTurnContext

            for removed_cid in removed_conversations:
                ImageTurnContext.notify_committed_change(
                    self, removed_cid, deleted=True
                )

        from astrbot.core import logger
        from astrbot.core.image_asset_store import collect_pending_images

        try:
            await collect_pending_images(self)
        except Exception as exc:
            logger.warning(
                "Image cleanup deferred after conversation deletion: %s",
                type(exc).__name__,
            )

    async def delete_conversation(self, cid) -> None:
        await self._delete_image_conversations(cid=cid)

    async def delete_conversations_by_user_id(self, user_id: str) -> None:
        await self._delete_image_conversations(user_id=user_id)

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
        llm_checkpoint_id=None,
        max_messages=None,
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
                    llm_checkpoint_id=llm_checkpoint_id,
                )
                session.add(new_history)
                await session.flush()
                if max_messages is not None:
                    keep_ids = (
                        select(PlatformMessageHistory.id)
                        .where(
                            col(PlatformMessageHistory.platform_id) == platform_id,
                            col(PlatformMessageHistory.user_id) == user_id,
                        )
                        .order_by(desc(PlatformMessageHistory.id))
                        .limit(max(1, int(max_messages)))
                    )
                    await session.execute(
                        delete(PlatformMessageHistory).where(
                            col(PlatformMessageHistory.platform_id) == platform_id,
                            col(PlatformMessageHistory.user_id) == user_id,
                            col(PlatformMessageHistory.id).not_in(keep_ids),
                        )
                    )
                return new_history

    async def update_platform_message_history(
        self,
        message_id: int,
        content: dict | None = None,
        llm_checkpoint_id: str | None = None,
    ) -> None:
        """Update a platform message history record."""
        values = {}
        if content is not None:
            values["content"] = content
        if llm_checkpoint_id is not None:
            values["llm_checkpoint_id"] = llm_checkpoint_id
        if not values:
            return

        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    update(PlatformMessageHistory)
                    .where(col(PlatformMessageHistory.id) == message_id)
                    .values(**values)
                )

    async def delete_platform_message_history_by_id(self, message_id: int) -> None:
        """Delete a platform message history record by ID."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(PlatformMessageHistory).where(
                        col(PlatformMessageHistory.id) == message_id
                    )
                )

    async def delete_platform_message_offset(
        self,
        platform_id,
        user_id,
        offset_sec=86400,
    ) -> None:
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
                .order_by(
                    desc(PlatformMessageHistory.created_at),
                    desc(PlatformMessageHistory.id),
                )
            )
            result = await session.execute(query.offset(offset).limit(page_size))
            return result.scalars().all()

    async def count_platform_message_history(
        self,
        platform_id: str,
        user_id: str,
    ) -> int:
        """Count platform message history records for a scope.

        Args:
            platform_id: Platform identifier used to partition history.
            user_id: Platform user or session identifier.

        Returns:
            Number of records matching the platform/user scope.
        """
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(func.count(PlatformMessageHistory.id)).where(
                    PlatformMessageHistory.platform_id == platform_id,
                    PlatformMessageHistory.user_id == user_id,
                )
            )
            return int(result.scalar_one() or 0)

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

    async def create_webchat_thread(
        self,
        creator: str,
        parent_session_id: str,
        parent_message_id: int,
        base_checkpoint_id: str,
        selected_text: str,
    ) -> WebChatThread:
        """Create a WebChat side thread."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                thread = WebChatThread(
                    creator=creator,
                    parent_session_id=parent_session_id,
                    parent_message_id=parent_message_id,
                    base_checkpoint_id=base_checkpoint_id,
                    selected_text=selected_text,
                )
                session.add(thread)
                await session.flush()
                await session.refresh(thread)
                return thread

    async def get_webchat_thread_by_id(
        self,
        thread_id: str,
    ) -> WebChatThread | None:
        """Get a WebChat side thread by thread_id."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(WebChatThread).where(WebChatThread.thread_id == thread_id)
            )
            return result.scalar_one_or_none()

    async def get_webchat_threads_by_parent_session(
        self,
        parent_session_id: str,
        creator: str | None = None,
    ) -> list[WebChatThread]:
        """Get side threads for a parent WebChat session."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(WebChatThread).where(
                WebChatThread.parent_session_id == parent_session_id
            )
            if creator is not None:
                query = query.where(WebChatThread.creator == creator)
            query = query.order_by(col(WebChatThread.created_at))
            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_webchat_thread_by_parent_message_and_text(
        self,
        parent_session_id: str,
        parent_message_id: int,
        selected_text: str,
        creator: str | None = None,
    ) -> WebChatThread | None:
        """Get an existing side thread for the same selected text."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(WebChatThread).where(
                WebChatThread.parent_session_id == parent_session_id,
                WebChatThread.parent_message_id == parent_message_id,
                WebChatThread.selected_text == selected_text,
            )
            if creator is not None:
                query = query.where(WebChatThread.creator == creator)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def delete_webchat_thread(self, thread_id: str) -> None:
        """Delete a WebChat side thread."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(WebChatThread).where(
                        col(WebChatThread.thread_id) == thread_id
                    )
                )

    async def delete_webchat_threads_by_parent_session(
        self,
        parent_session_id: str,
    ) -> list[str]:
        """Delete side threads for a parent WebChat session."""
        threads = await self.get_webchat_threads_by_parent_session(parent_session_id)
        thread_ids = [thread.thread_id for thread in threads]
        if not thread_ids:
            return []
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(WebChatThread).where(
                        col(WebChatThread.thread_id).in_(thread_ids)
                    )
                )
        return thread_ids

    async def delete_webchat_threads_by_parent_message_ids(
        self,
        parent_session_id: str,
        parent_message_ids: list[int],
    ) -> list[str]:
        """Delete side threads linked to parent message IDs."""
        if not parent_message_ids:
            return []
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(WebChatThread.thread_id).where(
                    WebChatThread.parent_session_id == parent_session_id,
                    col(WebChatThread.parent_message_id).in_(parent_message_ids),
                )
            )
            thread_ids = list(result.scalars().all())
        if not thread_ids:
            return []
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(WebChatThread).where(
                        col(WebChatThread.thread_id).in_(thread_ids)
                    )
                )
        return thread_ids

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

    async def create_api_key(
        self,
        name: str,
        key_hash: str,
        key_prefix: str,
        scopes: list[str] | None,
        created_by: str,
        expires_at: datetime | None = None,
    ) -> ApiKey:
        """Create a new API key record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                api_key = ApiKey(
                    name=name,
                    key_hash=key_hash,
                    key_prefix=key_prefix,
                    scopes=scopes,
                    created_by=created_by,
                    expires_at=expires_at,
                )
                session.add(api_key)
                await session.flush()
                await session.refresh(api_key)
                return api_key

    async def list_api_keys(self) -> list[ApiKey]:
        """List all API keys."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(ApiKey).order_by(desc(ApiKey.created_at))
            )
            return list(result.scalars().all())

    async def get_api_key_by_id(self, key_id: str) -> ApiKey | None:
        """Get an API key by key_id."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(ApiKey).where(ApiKey.key_id == key_id)
            )
            return result.scalar_one_or_none()

    async def get_active_api_key_by_hash(self, key_hash: str) -> ApiKey | None:
        """Get an active API key by hash (not revoked, not expired)."""
        async with self.get_db() as session:
            session: AsyncSession
            now = datetime.now(timezone.utc)
            query = select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                col(ApiKey.revoked_at).is_(None),
                or_(col(ApiKey.expires_at).is_(None), col(ApiKey.expires_at) > now),
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def touch_api_key(self, key_id: str) -> None:
        """Update last_used_at of an API key."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    update(ApiKey)
                    .where(col(ApiKey.key_id) == key_id)
                    .values(last_used_at=datetime.now(timezone.utc)),
                )

    async def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = (
                    update(ApiKey)
                    .where(col(ApiKey.key_id) == key_id)
                    .values(revoked_at=datetime.now(timezone.utc))
                )
                result = T.cast(CursorResult, await session.execute(query))
                return result.rowcount > 0

    async def delete_api_key(self, key_id: str) -> bool:
        """Delete an API key."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = T.cast(
                    CursorResult,
                    await session.execute(
                        delete(ApiKey).where(col(ApiKey.key_id) == key_id)
                    ),
                )
                return result.rowcount > 0

    async def insert_persona(
        self,
        persona_id,
        system_prompt,
        begin_dialogs=None,
        tools=None,
        skills=None,
        custom_error_message=None,
        folder_id=None,
        sort_order=0,
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
                    skills=skills,
                    custom_error_message=custom_error_message,
                    folder_id=folder_id,
                    sort_order=sort_order,
                )
                session.add(new_persona)
                await session.flush()
                await session.refresh(new_persona)
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
        skills=NOT_GIVEN,
        custom_error_message=NOT_GIVEN,
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
                if skills is not NOT_GIVEN:
                    values["skills"] = skills
                if custom_error_message is not NOT_GIVEN:
                    values["custom_error_message"] = custom_error_message
                if not values:
                    return None
                query = query.values(**values)
                await session.execute(query)
        return await self.get_persona_by_id(persona_id)

    async def delete_persona(self, persona_id) -> None:
        """Delete a persona by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(Persona).where(col(Persona.persona_id) == persona_id),
                )

    # ====
    # Persona Folder Management
    # ====

    async def insert_persona_folder(
        self,
        name: str,
        parent_id: str | None = None,
        description: str | None = None,
        sort_order: int = 0,
    ) -> PersonaFolder:
        """Insert a new persona folder."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_folder = PersonaFolder(
                    name=name,
                    parent_id=parent_id,
                    description=description,
                    sort_order=sort_order,
                )
                session.add(new_folder)
                await session.flush()
                await session.refresh(new_folder)
                return new_folder

    async def get_persona_folder_by_id(self, folder_id: str) -> PersonaFolder | None:
        """Get a persona folder by its folder_id."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(PersonaFolder).where(PersonaFolder.folder_id == folder_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_persona_folders(
        self, parent_id: str | None = None
    ) -> list[PersonaFolder]:
        """Get all persona folders, optionally filtered by parent_id.

        Args:
            parent_id: If None, returns root folders only. If specified, returns
                       children of that folder.
        """
        async with self.get_db() as session:
            session: AsyncSession
            if parent_id is None:
                # Get root folders (parent_id is NULL)
                query = (
                    select(PersonaFolder)
                    .where(col(PersonaFolder.parent_id).is_(None))
                    .order_by(col(PersonaFolder.sort_order), col(PersonaFolder.name))
                )
            else:
                query = (
                    select(PersonaFolder)
                    .where(PersonaFolder.parent_id == parent_id)
                    .order_by(col(PersonaFolder.sort_order), col(PersonaFolder.name))
                )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_all_persona_folders(self) -> list[PersonaFolder]:
        """Get all persona folders."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(PersonaFolder).order_by(
                col(PersonaFolder.sort_order), col(PersonaFolder.name)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_persona_folder(
        self,
        folder_id: str,
        name: str | None = None,
        parent_id: T.Any = NOT_GIVEN,
        description: T.Any = NOT_GIVEN,
        sort_order: int | None = None,
    ) -> PersonaFolder | None:
        """Update a persona folder."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = update(PersonaFolder).where(
                    col(PersonaFolder.folder_id) == folder_id
                )
                values: dict[str, T.Any] = {}
                if name is not None:
                    values["name"] = name
                if parent_id is not NOT_GIVEN:
                    values["parent_id"] = parent_id
                if description is not NOT_GIVEN:
                    values["description"] = description
                if sort_order is not None:
                    values["sort_order"] = sort_order
                if not values:
                    return None
                query = query.values(**values)
                await session.execute(query)
        return await self.get_persona_folder_by_id(folder_id)

    async def delete_persona_folder(self, folder_id: str) -> None:
        """Delete a persona folder by its folder_id.

        Note: This will also set folder_id to NULL for all personas in this folder,
        moving them to the root directory.
        """
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                # Move personas to root directory
                await session.execute(
                    update(Persona)
                    .where(col(Persona.folder_id) == folder_id)
                    .values(folder_id=None)
                )
                # Delete the folder
                await session.execute(
                    delete(PersonaFolder).where(
                        col(PersonaFolder.folder_id) == folder_id
                    ),
                )

    async def move_persona_to_folder(
        self, persona_id: str, folder_id: str | None
    ) -> Persona | None:
        """Move a persona to a folder (or root if folder_id is None)."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    update(Persona)
                    .where(col(Persona.persona_id) == persona_id)
                    .values(folder_id=folder_id)
                )
        return await self.get_persona_by_id(persona_id)

    async def get_personas_by_folder(
        self, folder_id: str | None = None
    ) -> list[Persona]:
        """Get all personas in a specific folder.

        Args:
            folder_id: If None, returns personas in root directory.
        """
        async with self.get_db() as session:
            session: AsyncSession
            if folder_id is None:
                query = (
                    select(Persona)
                    .where(col(Persona.folder_id).is_(None))
                    .order_by(col(Persona.sort_order), col(Persona.persona_id))
                )
            else:
                query = (
                    select(Persona)
                    .where(Persona.folder_id == folder_id)
                    .order_by(col(Persona.sort_order), col(Persona.persona_id))
                )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def batch_update_sort_order(
        self,
        items: list[dict],
    ) -> None:
        """Batch update sort_order for personas and/or folders.

        Args:
            items: List of dicts with keys:
                - id: The persona_id or folder_id
                - type: Either "persona" or "folder"
                - sort_order: The new sort_order value
        """
        if not items:
            return

        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                for item in items:
                    item_id = item.get("id")
                    item_type = item.get("type")
                    sort_order = item.get("sort_order")

                    if item_id is None or item_type is None or sort_order is None:
                        continue

                    if item_type == "persona":
                        await session.execute(
                            update(Persona)
                            .where(col(Persona.persona_id) == item_id)
                            .values(sort_order=sort_order)
                        )
                    elif item_type == "folder":
                        await session.execute(
                            update(PersonaFolder)
                            .where(col(PersonaFolder.folder_id) == item_id)
                            .values(sort_order=sort_order)
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

    def get_preference_sync(
        self,
        scope: str,
        scope_id: str,
        key: str,
    ) -> dict | None:
        """Synchronous point query for a single preference value.

        Uses a dedicated stdlib sqlite3 connection instead of the async
        SQLAlchemy pool, so deprecated synchronous SharedPreferences APIs never
        wait on (or deadlock against) the event-loop-owned pool. The database
        runs in WAL mode, so this short index lookup can read concurrently with
        the async writer.

        Args:
            scope: Preference scope.
            scope_id: Identifier within the preference scope.
            key: Preference key.

        Returns:
            The stored value dict (e.g. ``{"val": ...}``), or None if missing.
        """
        conn = sqlite3.connect(Path(self.db_path), timeout=30)
        try:
            row = conn.execute(
                "SELECT value FROM preferences "
                "WHERE scope = ? AND scope_id = ? AND key = ?",
                (scope, scope_id, key),
            ).fetchone()
            if row is None:
                return None
            value = row[0]
            return (
                json.loads(value)
                if isinstance(value, (str, bytes, bytearray))
                else value
            )
        finally:
            conn.close()

    def get_preferences_sync(
        self,
        scope: str,
        scope_id: str | None = None,
        key: str | None = None,
    ) -> list[Preference]:
        """Synchronously query preferences within a scope.

        This compatibility path uses a dedicated sqlite3 connection instead of
        the async SQLAlchemy pool. It only loads the range explicitly requested
        by the deprecated synchronous API and is never called during startup.

        Args:
            scope: Preference scope to query.
            scope_id: Optional identifier within the scope.
            key: Optional preference key.

        Returns:
            Preferences matching the supplied filters.
        """
        query = "SELECT scope, scope_id, key, value FROM preferences WHERE scope = ?"
        params: list[str] = [scope]
        if scope_id is not None:
            query += " AND scope_id = ?"
            params.append(scope_id)
        if key is not None:
            query += " AND key = ?"
            params.append(key)

        conn = sqlite3.connect(Path(self.db_path), timeout=30)
        try:
            rows = conn.execute(query, params).fetchall()
            preferences = []
            for row_scope, row_scope_id, row_key, row_value in rows:
                value = (
                    json.loads(row_value)
                    if isinstance(row_value, (str, bytes, bytearray))
                    else row_value
                )
                preferences.append(
                    Preference(
                        scope=row_scope,
                        scope_id=row_scope_id,
                        key=row_key,
                        value=value,
                    )
                )
            return preferences
        finally:
            conn.close()

    async def get_preferences(self, scope=None, scope_id=None, key=None):
        """Get preferences, optionally filtered by scope, scope ID, or key."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Preference)
            if scope is not None:
                query = query.where(Preference.scope == scope)
            if scope_id is not None:
                query = query.where(Preference.scope_id == scope_id)
            if key is not None:
                query = query.where(Preference.key == key)
            result = await session.execute(query)
            return result.scalars().all()

    async def remove_preference(self, scope, scope_id, key) -> None:
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

    async def clear_preferences(self, scope, scope_id) -> None:
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

    @deprecated(version="4.0.0", reason="Use get_platform_stats instead")
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

        def runner() -> None:
            nonlocal result
            result = asyncio.run(_inner())

        t = threading.Thread(target=runner)
        t.start()
        t.join()
        return result

    @deprecated(version="4.0.0", reason="Use get_platform_stats instead")
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

        def runner() -> None:
            nonlocal result
            result = asyncio.run(_inner())

        t = threading.Thread(target=runner)
        t.start()
        t.join()
        return result

    @deprecated(version="4.0.0", reason="Use get_platform_stats instead")
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

        def runner() -> None:
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

    async def get_platform_sessions_by_ids(
        self, session_ids: list[str]
    ) -> list[PlatformSession]:
        """Get platform sessions by IDs."""
        if not session_ids:
            return []

        async with self.get_db() as session:
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
        async with self.get_db() as session:
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
    # UMO Alias Management
    # ====

    async def upsert_umo_alias(
        self,
        umo: str,
        creator_sender_id: str,
        auto_name: str | None,
        user_alias: str | None,
    ) -> UmoAlias:
        """Create or replace user-controlled alias metadata for a UMO.

        Args:
            umo: Unified message origin to name.
            creator_sender_id: Sender responsible for the manual alias update.
            auto_name: Latest name discovered from platform metadata.
            user_alias: User-controlled display alias.

        Returns:
            Persisted UMO alias record.
        """
        now = datetime.now(timezone.utc)
        statement = sqlite_insert(UmoAlias).values(
            umo=umo,
            creator_sender_id=creator_sender_id,
            auto_name=auto_name,
            user_alias=user_alias,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[UmoAlias.umo],
            set_={
                "creator_sender_id": statement.excluded.creator_sender_id,
                "auto_name": statement.excluded.auto_name,
                "user_alias": statement.excluded.user_alias,
                "updated_at": now,
            },
        )
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(statement)
                result = await session.execute(
                    select(UmoAlias).where(col(UmoAlias.umo) == umo)
                )
                return result.scalar_one()

    async def upsert_umo_auto_name(
        self,
        umo: str,
        creator_sender_id: str,
        auto_name: str,
    ) -> None:
        """Persist an automatic UMO name without changing its manual alias.

        Args:
            umo: Unified message origin to name.
            creator_sender_id: Sender that first caused the UMO to be recorded.
            auto_name: Name discovered from the inbound platform message.
        """
        now = datetime.now(timezone.utc)
        statement = sqlite_insert(UmoAlias).values(
            umo=umo,
            creator_sender_id=creator_sender_id,
            auto_name=auto_name,
            user_alias=None,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[UmoAlias.umo],
            set_={
                "auto_name": statement.excluded.auto_name,
                "updated_at": now,
            },
            where=col(UmoAlias.auto_name).is_distinct_from(
                statement.excluded.auto_name
            ),
        )
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(statement)

    async def get_umo_alias(self, umo: str) -> UmoAlias | None:
        """Get alias metadata for one UMO."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(UmoAlias).where(col(UmoAlias.umo) == umo)
            )
            return result.scalar_one_or_none()

    async def get_umo_aliases(self, umos: list[str] | None = None) -> list[UmoAlias]:
        """Get alias metadata, optionally restricted to a UMO list."""
        if umos is not None and not umos:
            return []

        async with self.get_db() as session:
            session: AsyncSession
            query = select(UmoAlias)
            if umos is not None:
                query = query.where(col(UmoAlias.umo).in_(umos))
            result = await session.execute(query)
            return list(result.scalars().all())

    # ====
    # ChatUI Project Management
    # ====

    async def create_chatui_project(
        self,
        creator: str,
        title: str,
        emoji: str | None = "📁",
        description: str | None = None,
        workspace_type: str = "session",
        workspace_path: str | None = None,
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
                    workspace_type=workspace_type,
                    workspace_path=workspace_path,
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
        workspace_type: str | None = None,
        workspace_path: str | None = None,
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
                if workspace_type is not None:
                    values["workspace_type"] = workspace_type
                    values["workspace_path"] = workspace_path

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

    # ====
    # Cron Job Management
    # ====

    async def create_cron_job(
        self,
        name: str,
        job_type: str,
        cron_expression: str | None,
        *,
        timezone: str | None = None,
        payload: dict | None = None,
        description: str | None = None,
        enabled: bool = True,
        persistent: bool = True,
        run_once: bool = False,
        status: str | None = None,
        job_id: str | None = None,
    ) -> CronJob:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                job = CronJob(
                    name=name,
                    job_type=job_type,
                    cron_expression=cron_expression,
                    timezone=timezone,
                    payload=payload or {},
                    description=description,
                    enabled=enabled,
                    persistent=persistent,
                    run_once=run_once,
                    status=status or "scheduled",
                )
                if job_id:
                    job.job_id = job_id
                session.add(job)
                await session.flush()
                await session.refresh(job)
                return job

    async def update_cron_job(
        self,
        job_id: str,
        *,
        name: str | None | object = CRON_FIELD_NOT_SET,
        cron_expression: str | None | object = CRON_FIELD_NOT_SET,
        timezone: str | None | object = CRON_FIELD_NOT_SET,
        payload: dict | None | object = CRON_FIELD_NOT_SET,
        description: str | None | object = CRON_FIELD_NOT_SET,
        enabled: bool | None | object = CRON_FIELD_NOT_SET,
        persistent: bool | None | object = CRON_FIELD_NOT_SET,
        run_once: bool | None | object = CRON_FIELD_NOT_SET,
        status: str | None | object = CRON_FIELD_NOT_SET,
        next_run_time: datetime | None | object = CRON_FIELD_NOT_SET,
        last_run_at: datetime | None | object = CRON_FIELD_NOT_SET,
        last_error: str | None | object = CRON_FIELD_NOT_SET,
    ) -> CronJob | None:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                updates: dict = {}
                for key, val in {
                    "name": name,
                    "cron_expression": cron_expression,
                    "timezone": timezone,
                    "payload": payload,
                    "description": description,
                    "enabled": enabled,
                    "persistent": persistent,
                    "run_once": run_once,
                    "status": status,
                    "next_run_time": next_run_time,
                    "last_run_at": last_run_at,
                    "last_error": last_error,
                }.items():
                    if val is CRON_FIELD_NOT_SET:
                        continue
                    updates[key] = val

                stmt = (
                    update(CronJob)
                    .where(col(CronJob.job_id) == job_id)
                    .values(**updates)
                    .execution_options(synchronize_session="fetch")
                )
                await session.execute(stmt)
                result = await session.execute(
                    select(CronJob).where(col(CronJob.job_id) == job_id)
                )
                return result.scalar_one_or_none()

    async def delete_cron_job(self, job_id: str) -> None:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(CronJob).where(col(CronJob.job_id) == job_id)
                )

    async def get_cron_job(self, job_id: str) -> CronJob | None:
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(CronJob).where(col(CronJob.job_id) == job_id)
            )
            return result.scalar_one_or_none()

    async def list_cron_jobs(self, job_type: str | None = None) -> list[CronJob]:
        async with self.get_db() as session:
            session: AsyncSession
            query = select(CronJob)
            if job_type:
                query = query.where(col(CronJob.job_type) == job_type)
            query = query.order_by(desc(CronJob.created_at))
            result = await session.execute(query)
            return list(result.scalars().all())
