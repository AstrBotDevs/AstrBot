"""SQLite initialization and legacy schema migration."""

import asyncio

from sqlalchemy import event
from sqlmodel import SQLModel, text

from astrbot.core.db.migration.migra_conversation_events import migrate_conversations
from astrbot.core.db.relational import RelationalDatabase


class SQLiteDatabase(RelationalDatabase):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
        self.inited = False
        self._initialize_lock = asyncio.Lock()
        super().__init__()

        @event.listens_for(self.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record):
            """Enforce event ownership and ancestry on every pooled connection."""
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    async def initialize(self) -> None:
        """Serialize schema migration before allowing application traffic."""
        async with self._initialize_lock:
            await self._initialize_schema()

    async def _initialize_schema(self) -> None:
        """Initialize the database by creating tables if they do not exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: SQLModel.metadata.create_all(
                    sync_conn,
                    tables=[
                        table
                        for name, table in SQLModel.metadata.tables.items()
                        if name != "conversations"
                    ],
                )
            )
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
            await self._ensure_platform_message_history_event_columns(conn)
            await self._ensure_chatui_project_workspace_columns(conn)
            # The table-level unique constraint already provides an index for UMO
            # lookups. Older schemas also created this redundant explicit index.
            await conn.execute(text("DROP INDEX IF EXISTS ix_umo_aliases_umo"))
            await conn.commit()
        await migrate_conversations(self.conversation_store)
        self.inited = True

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

    async def _ensure_platform_message_history_event_columns(self, conn) -> None:
        """Migrate WebChat associations from legacy markers to event identities.

        Args:
            conn: Initialization transaction.
        """
        for table, old, new in (
            ("platform_message_history", "llm_checkpoint_id", "turn_id"),
            ("webchat_threads", "base_checkpoint_id", "base_event_id"),
        ):
            columns = {
                row[1]
                for row in (
                    await conn.execute(text(f"PRAGMA table_info({table})"))
                ).all()
            }
            if old in columns and new not in columns:
                await conn.execute(
                    text(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
                )
            elif new not in columns:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {new} VARCHAR")
                )
        columns = {
            row[1]
            for row in (
                await conn.execute(text("PRAGMA table_info(platform_message_history)"))
            ).all()
        }
        if "is_active" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE platform_message_history ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
                )
            )
        if "context_event_id" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE platform_message_history ADD COLUMN context_event_id VARCHAR"
                )
            )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_platform_message_history_turn_id ON platform_message_history (turn_id)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_platform_message_history_context_event_id ON platform_message_history (context_event_id)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_platform_message_history_platform_user_id ON platform_message_history (platform_id, user_id, id)"
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
