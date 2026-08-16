import typing as T
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import CursorResult, Row
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, desc, func, or_, select, text, update

from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import (
    ApiKey,
    Attachment,
    ChatUIProject,
    CommandConfig,
    CommandConflict,
    ConversationV2,
    CronJob,
    MemoryEpisode,
    MemoryFact,
    MemoryOperationLog,
    MemoryProfile,
    MemoryScopePolicyRecord,
    MemoryTuningTask,
    Persona,
    PersonaBehaviorPolicy,
    PersonaExpressionAsset,
    PersonaFolder,
    PersonaJargonAsset,
    PersonaSessionState,
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
from astrbot.core.sentinels import NOT_GIVEN

TxResult = T.TypeVar("TxResult")
CRON_FIELD_NOT_SET = object()


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
            await self._ensure_platform_message_history_columns(conn)
            await self._ensure_authorization_schema(conn)
        # Journal and cache settings must be issued outside the schema
        # transaction: SQLite rejects synchronous-mode changes otherwise.
        async with self.engine.connect() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=30000"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=20000"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
            await conn.execute(text("PRAGMA mmap_size=134217728"))
            await conn.execute(text("PRAGMA optimize"))
            await conn.commit()

    async def _ensure_platform_message_history_columns(self, conn) -> None:
        """Add current history columns to databases created by older revisions."""
        result = await conn.execute(text("PRAGMA table_info(platform_message_history)"))
        columns = {str(row[1]) for row in result.fetchall()}
        if "role" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE platform_message_history "
                    "ADD COLUMN role VARCHAR NOT NULL DEFAULT 'user'"
                )
            )
        if "is_group" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE platform_message_history "
                    "ADD COLUMN is_group BOOLEAN NOT NULL DEFAULT 0"
                )
            )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_platform_message_history_scope_order "
                "ON platform_message_history (platform_id, user_id, is_group, id)"
            )
        )

    async def _ensure_authorization_schema(self, conn) -> None:
        """Enforce one active role binding per subject and scope."""

        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uix_auth_role_binding_active_scope "
                "ON auth_role_bindings(subject_id, scope_type, scope_id, config_id) "
                "WHERE revoked_at IS NULL"
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
        """Get platform statistic rows within the specified offset in seconds."""
        async with self.get_db() as session:
            session: AsyncSession
            now = datetime.now()
            start_time = now - timedelta(seconds=offset_sec)
            result = await session.execute(
                select(PlatformStat)
                .where(col(PlatformStat.timestamp) >= start_time)
                .order_by(col(PlatformStat.timestamp).asc()),
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
                )
                session.add(record)
                await session.flush()
                await session.refresh(record)
                return record

    # ====
    # Persona Runtime and Long-term Memory
    # ====

    async def get_persona_session_state(
        self,
        persona_id: str,
        umo: str,
    ) -> PersonaSessionState | None:
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(PersonaSessionState).where(
                    col(PersonaSessionState.persona_id) == persona_id,
                    col(PersonaSessionState.umo) == umo,
                )
            )
            return result.scalar_one_or_none()

    async def upsert_persona_session_state(
        self,
        *,
        persona_id: str,
        umo: str,
        agent_state: str = "running",
        talk_frequency_adjust: float = 1.0,
        consecutive_idle_count: int = 0,
        cooldown_until: datetime | None = None,
        last_interaction_at: datetime | None = None,
        last_proactive_at: datetime | None = None,
        extra_state: dict | None = None,
    ) -> PersonaSessionState:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(PersonaSessionState).where(
                        col(PersonaSessionState.persona_id) == persona_id,
                        col(PersonaSessionState.umo) == umo,
                    )
                )
                state = result.scalar_one_or_none()
                if state is None:
                    state = PersonaSessionState(
                        persona_id=persona_id,
                        umo=umo,
                        agent_state=agent_state,
                        talk_frequency_adjust=talk_frequency_adjust,
                        consecutive_idle_count=consecutive_idle_count,
                        cooldown_until=cooldown_until,
                        last_interaction_at=last_interaction_at,
                        last_proactive_at=last_proactive_at,
                        extra_state=extra_state or {},
                    )
                    session.add(state)
                else:
                    state.agent_state = agent_state
                    state.talk_frequency_adjust = talk_frequency_adjust
                    state.consecutive_idle_count = consecutive_idle_count
                    state.cooldown_until = cooldown_until
                    state.last_interaction_at = last_interaction_at
                    state.last_proactive_at = last_proactive_at
                    state.extra_state = extra_state or {}
                    state.updated_at = datetime.now(UTC)
                await session.flush()
                await session.refresh(state)
                return state

    async def upsert_persona_expression_asset(
        self,
        *,
        persona_id: str,
        scope: str,
        trigger_scene: str,
        style_text: str,
        source_message_id: str,
        score: float = 0.5,
        enabled: bool = True,
    ) -> PersonaExpressionAsset:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(PersonaExpressionAsset).where(
                        col(PersonaExpressionAsset.persona_id) == persona_id,
                        col(PersonaExpressionAsset.scope) == scope,
                        col(PersonaExpressionAsset.trigger_scene) == trigger_scene,
                        col(PersonaExpressionAsset.style_text) == style_text,
                    )
                )
                asset = result.scalar_one_or_none()
                if asset is None:
                    asset = PersonaExpressionAsset(
                        persona_id=persona_id,
                        scope=scope,
                        trigger_scene=trigger_scene,
                        style_text=style_text,
                        source_message_id=source_message_id,
                        score=score,
                        enabled=enabled,
                    )
                    session.add(asset)
                else:
                    asset.source_message_id = source_message_id
                    asset.score = max(float(asset.score), score)
                    asset.enabled = enabled
                    asset.updated_at = datetime.now(UTC)
                await session.flush()
                await session.refresh(asset)
                return asset

    async def list_persona_expression_assets(
        self,
        *,
        persona_id: str,
        scope: str,
        enabled: bool = True,
        limit: int = 10,
    ) -> list[PersonaExpressionAsset]:
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(PersonaExpressionAsset)
                .where(
                    col(PersonaExpressionAsset.persona_id) == persona_id,
                    col(PersonaExpressionAsset.scope) == scope,
                    col(PersonaExpressionAsset.enabled) == enabled,
                )
                .order_by(desc(PersonaExpressionAsset.score))
                .limit(limit)
            )
            return list(result.scalars().all())

    async def upsert_persona_jargon_asset(
        self,
        *,
        persona_id: str,
        scope: str,
        term: str,
        meaning: str | None,
        source_message_id: str,
        score: float = 0.5,
        approved: bool = False,
        enabled: bool = True,
    ) -> PersonaJargonAsset:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(PersonaJargonAsset).where(
                        col(PersonaJargonAsset.persona_id) == persona_id,
                        col(PersonaJargonAsset.scope) == scope,
                        col(PersonaJargonAsset.term) == term,
                    )
                )
                asset = result.scalar_one_or_none()
                if asset is None:
                    asset = PersonaJargonAsset(
                        persona_id=persona_id,
                        scope=scope,
                        term=term,
                        meaning=meaning,
                        source_message_id=source_message_id,
                        score=score,
                        approved=approved,
                        enabled=enabled,
                    )
                    session.add(asset)
                else:
                    asset.meaning = meaning or asset.meaning
                    asset.source_message_id = source_message_id
                    asset.score = max(float(asset.score), score)
                    asset.approved = asset.approved or approved
                    asset.enabled = enabled
                    asset.updated_at = datetime.now(UTC)
                await session.flush()
                await session.refresh(asset)
                return asset

    async def list_persona_jargon_assets(
        self,
        *,
        persona_id: str,
        scope: str,
        enabled: bool = True,
        approved: bool | None = None,
        limit: int = 10,
    ) -> list[PersonaJargonAsset]:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(PersonaJargonAsset).where(
                col(PersonaJargonAsset.persona_id) == persona_id,
                col(PersonaJargonAsset.scope) == scope,
                col(PersonaJargonAsset.enabled) == enabled,
            )
            if approved is not None:
                stmt = stmt.where(col(PersonaJargonAsset.approved) == approved)
            stmt = stmt.order_by(desc(PersonaJargonAsset.score)).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def upsert_persona_behavior_policy(
        self,
        *,
        persona_id: str,
        scope: str,
        situation: str,
        preferred_action: str,
        avoid_action: str | None = None,
        confidence: float = 0.5,
        enabled: bool = True,
    ) -> PersonaBehaviorPolicy:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(PersonaBehaviorPolicy).where(
                        col(PersonaBehaviorPolicy.persona_id) == persona_id,
                        col(PersonaBehaviorPolicy.scope) == scope,
                        col(PersonaBehaviorPolicy.situation) == situation,
                        col(PersonaBehaviorPolicy.preferred_action) == preferred_action,
                    )
                )
                policy = result.scalar_one_or_none()
                if policy is None:
                    policy = PersonaBehaviorPolicy(
                        persona_id=persona_id,
                        scope=scope,
                        situation=situation,
                        preferred_action=preferred_action,
                        avoid_action=avoid_action,
                        confidence=confidence,
                        enabled=enabled,
                    )
                    session.add(policy)
                else:
                    policy.avoid_action = avoid_action or policy.avoid_action
                    policy.confidence = max(float(policy.confidence), confidence)
                    policy.enabled = enabled
                    policy.updated_at = datetime.now(UTC)
                await session.flush()
                await session.refresh(policy)
                return policy

    async def list_persona_behavior_policies(
        self,
        *,
        persona_id: str,
        scope: str,
        enabled: bool = True,
        limit: int = 10,
    ) -> list[PersonaBehaviorPolicy]:
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(PersonaBehaviorPolicy)
                .where(
                    col(PersonaBehaviorPolicy.persona_id) == persona_id,
                    col(PersonaBehaviorPolicy.scope) == scope,
                    col(PersonaBehaviorPolicy.enabled) == enabled,
                )
                .order_by(desc(PersonaBehaviorPolicy.confidence))
                .limit(limit)
            )
            return list(result.scalars().all())

    async def upsert_memory_fact(
        self,
        *,
        person_id: str,
        chat_id: str,
        scope_id: str,
        fact_text: str,
        fact_type: str,
        source_message_id: str,
        evidence_message_ids: list[str] | None = None,
        confidence: float = 0.6,
        status: str = "active",
        ttl_at: datetime | None = None,
    ) -> tuple[MemoryFact, bool]:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(MemoryFact).where(
                        col(MemoryFact.person_id) == person_id,
                        col(MemoryFact.chat_id) == chat_id,
                        col(MemoryFact.fact_text) == fact_text,
                    )
                )
                fact = result.scalar_one_or_none()
                created = fact is None
                if fact is None:
                    fact = MemoryFact(
                        person_id=person_id,
                        chat_id=chat_id,
                        scope_id=scope_id,
                        fact_text=fact_text,
                        fact_type=fact_type,
                        source_message_id=source_message_id,
                        evidence_message_ids=evidence_message_ids
                        or [source_message_id],
                        confidence=confidence,
                        status=status,
                        ttl_at=ttl_at,
                    )
                    session.add(fact)
                else:
                    evidence = list(fact.evidence_message_ids or [])
                    for message_id in evidence_message_ids or [source_message_id]:
                        if message_id not in evidence:
                            evidence.append(message_id)
                    fact.evidence_message_ids = evidence
                    fact.confidence = max(float(fact.confidence), confidence)
                    fact.updated_at = datetime.now(UTC)
                await session.flush()
                await session.refresh(fact)
                return fact, created

    async def list_memory_facts(
        self,
        *,
        person_id: str | None = None,
        chat_ids: list[str] | None = None,
        scope_id: str | None = None,
        query: str | None = None,
        status: str | None = "active",
        limit: int = 20,
        offset: int = 0,
    ) -> list[MemoryFact]:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(MemoryFact)
            if status:
                stmt = stmt.where(col(MemoryFact.status) == status)
            if person_id:
                stmt = stmt.where(col(MemoryFact.person_id) == person_id)
            if chat_ids is not None:
                if not chat_ids:
                    return []
                stmt = stmt.where(col(MemoryFact.chat_id).in_(chat_ids))
            if scope_id:
                stmt = stmt.where(col(MemoryFact.scope_id) == scope_id)
            if query:
                escaped = (
                    query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                stmt = stmt.where(
                    col(MemoryFact.fact_text).ilike(f"%{escaped}%", escape="\\")
                )
            stmt = (
                stmt.order_by(desc(MemoryFact.updated_at))
                .offset(max(offset, 0))
                .limit(max(limit, 1))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_memory_facts(
        self,
        *,
        person_id: str | None = None,
        chat_ids: list[str] | None = None,
        scope_id: str | None = None,
        query: str | None = None,
        status: str | None = "active",
    ) -> int:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(func.count()).select_from(MemoryFact)
            if status:
                stmt = stmt.where(col(MemoryFact.status) == status)
            if person_id:
                stmt = stmt.where(col(MemoryFact.person_id) == person_id)
            if chat_ids is not None:
                if not chat_ids:
                    return 0
                stmt = stmt.where(col(MemoryFact.chat_id).in_(chat_ids))
            if scope_id:
                stmt = stmt.where(col(MemoryFact.scope_id) == scope_id)
            if query:
                escaped = (
                    query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                stmt = stmt.where(
                    col(MemoryFact.fact_text).ilike(f"%{escaped}%", escape="\\")
                )
            result = await session.execute(stmt)
            return int(result.scalar_one() or 0)

    async def get_memory_fact(self, fact_id: int) -> MemoryFact | None:
        async with self.get_db() as session:
            session: AsyncSession
            return await session.get(MemoryFact, fact_id)

    async def update_memory_fact(
        self,
        fact_id: int,
        *,
        fact_text: str | None = None,
        fact_type: str | None = None,
        confidence: float | None = None,
        operator: str,
        reason: str | None = None,
    ) -> MemoryFact | None:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                fact = await session.get(MemoryFact, fact_id)
                if fact is None:
                    return None
                before = {
                    "fact_text": fact.fact_text,
                    "fact_type": fact.fact_type,
                    "confidence": fact.confidence,
                }
                if fact_text is not None:
                    fact.fact_text = fact_text
                if fact_type is not None:
                    fact.fact_type = fact_type
                if confidence is not None:
                    fact.confidence = confidence
                fact.updated_at = datetime.now(UTC)
                session.add(
                    MemoryOperationLog(
                        operator=operator,
                        target_type="memory_fact",
                        target_id=str(fact_id),
                        action="update",
                        reason=reason,
                        payload={
                            "before": before,
                            "after": {
                                "fact_text": fact.fact_text,
                                "fact_type": fact.fact_type,
                                "confidence": fact.confidence,
                            },
                            "person_id": fact.person_id,
                            "chat_id": fact.chat_id,
                        },
                    )
                )
                await session.flush()
                await session.refresh(fact)
                return fact

    async def update_memory_fact_status(
        self,
        fact_id: int,
        *,
        status: str,
        operator: str,
        reason: str | None = None,
    ) -> bool:
        if status not in {"active", "deleted"}:
            raise ValueError(f"Unsupported memory fact status: {status}")
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                fact = await session.get(MemoryFact, fact_id)
                if fact is None:
                    return False
                fact.status = status
                fact.updated_at = datetime.now(UTC)
                session.add(
                    MemoryOperationLog(
                        operator=operator,
                        target_type="memory_fact",
                        target_id=str(fact_id),
                        action="restore" if status == "active" else "delete",
                        reason=reason,
                        payload={
                            "person_id": fact.person_id,
                            "chat_id": fact.chat_id,
                            "fact_text": fact.fact_text,
                        },
                    )
                )
                return True

    async def upsert_memory_profile(
        self,
        *,
        person_id: str,
        chat_scope: str,
        profile_text: str,
        is_override: bool = False,
    ) -> MemoryProfile:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(MemoryProfile).where(
                        col(MemoryProfile.person_id) == person_id,
                        col(MemoryProfile.chat_scope) == chat_scope,
                        col(MemoryProfile.is_override) == is_override,
                    )
                )
                profile = result.scalar_one_or_none()
                if profile is None:
                    profile = MemoryProfile(
                        person_id=person_id,
                        chat_scope=chat_scope,
                        profile_text=profile_text,
                        is_override=is_override,
                    )
                    session.add(profile)
                else:
                    profile.profile_text = profile_text
                    profile.source_version += 1
                    profile.updated_at = datetime.now(UTC)
                await session.flush()
                await session.refresh(profile)
                return profile

    async def get_memory_profile(
        self,
        person_id: str,
        chat_scope: str,
        *,
        include_override: bool = True,
    ) -> MemoryProfile | None:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(MemoryProfile).where(
                col(MemoryProfile.person_id) == person_id,
                col(MemoryProfile.chat_scope) == chat_scope,
            )
            if not include_override:
                stmt = stmt.where(col(MemoryProfile.is_override).is_(False))
            stmt = stmt.order_by(desc(MemoryProfile.is_override))
            result = await session.execute(stmt)
            return result.scalars().first()

    async def list_memory_profiles(
        self,
        *,
        person_id: str | None = None,
        chat_scope: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[MemoryProfile]:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(MemoryProfile)
            if person_id:
                stmt = stmt.where(col(MemoryProfile.person_id) == person_id)
            if chat_scope:
                stmt = stmt.where(col(MemoryProfile.chat_scope) == chat_scope)
            stmt = (
                stmt.order_by(desc(MemoryProfile.updated_at))
                .offset(max(offset, 0))
                .limit(max(limit, 1))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_memory_profiles(
        self,
        *,
        person_id: str | None = None,
        chat_scope: str | None = None,
    ) -> int:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(func.count()).select_from(MemoryProfile)
            if person_id:
                stmt = stmt.where(col(MemoryProfile.person_id) == person_id)
            if chat_scope:
                stmt = stmt.where(col(MemoryProfile.chat_scope) == chat_scope)
            result = await session.execute(stmt)
            return int(result.scalar_one() or 0)

    async def upsert_memory_episode(
        self,
        *,
        episode_id: str,
        chat_id: str,
        scope_id: str,
        title: str,
        summary: str,
        participant_ids: list[str] | None = None,
        source_message_ids: list[str] | None = None,
        status: str = "active",
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> MemoryEpisode:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(MemoryEpisode).where(
                        col(MemoryEpisode.episode_id) == episode_id
                    )
                )
                episode = result.scalar_one_or_none()
                if episode is None:
                    episode = MemoryEpisode(
                        episode_id=episode_id,
                        chat_id=chat_id,
                        scope_id=scope_id,
                        title=title,
                        summary=summary,
                        participant_ids=participant_ids or [],
                        source_message_ids=source_message_ids or [],
                        status=status,
                        start_at=start_at or datetime.now(UTC),
                        end_at=end_at or datetime.now(UTC),
                    )
                    session.add(episode)
                else:
                    episode.title = title
                    episode.summary = summary
                    episode.participant_ids = participant_ids or episode.participant_ids
                    episode.source_message_ids = (
                        source_message_ids or episode.source_message_ids
                    )
                    episode.status = status
                    episode.end_at = end_at or datetime.now(UTC)
                    episode.updated_at = datetime.now(UTC)
                await session.flush()
                await session.refresh(episode)
                return episode

    async def list_memory_episodes(
        self,
        *,
        chat_ids: list[str] | None = None,
        scope_id: str | None = None,
        query: str | None = None,
        status: str = "active",
        limit: int = 10,
    ) -> list[MemoryEpisode]:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(MemoryEpisode).where(col(MemoryEpisode.status) == status)
            if chat_ids is not None:
                if not chat_ids:
                    return []
                stmt = stmt.where(col(MemoryEpisode.chat_id).in_(chat_ids))
            if scope_id:
                stmt = stmt.where(col(MemoryEpisode.scope_id) == scope_id)
            if query:
                escaped = (
                    query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                pattern = f"%{escaped}%"
                stmt = stmt.where(
                    or_(
                        col(MemoryEpisode.title).ilike(pattern, escape="\\"),
                        col(MemoryEpisode.summary).ilike(pattern, escape="\\"),
                    )
                )
            stmt = stmt.order_by(desc(MemoryEpisode.end_at)).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_memory_episodes(
        self,
        *,
        status: str | None = "active",
    ) -> int:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(func.count()).select_from(MemoryEpisode)
            if status:
                stmt = stmt.where(col(MemoryEpisode.status) == status)
            result = await session.execute(stmt)
            return int(result.scalar_one() or 0)

    async def upsert_memory_scope_policy(
        self,
        *,
        owner_scope_id: str,
        target_scope_id: str,
        sharing_mode: str = "group-shared",
        enabled: bool = True,
        operator: str = "memory_scope_policy",
        reason: str | None = None,
    ) -> MemoryScopePolicyRecord:
        if sharing_mode not in {"group-shared", "global-shared"}:
            raise ValueError(f"Unsupported memory sharing mode: {sharing_mode}")
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(MemoryScopePolicyRecord).where(
                        col(MemoryScopePolicyRecord.owner_scope_id) == owner_scope_id,
                        col(MemoryScopePolicyRecord.target_scope_id) == target_scope_id,
                        col(MemoryScopePolicyRecord.sharing_mode) == sharing_mode,
                    )
                )
                policy = result.scalar_one_or_none()
                if policy is None:
                    policy = MemoryScopePolicyRecord(
                        owner_scope_id=owner_scope_id,
                        target_scope_id=target_scope_id,
                        sharing_mode=sharing_mode,
                        enabled=enabled,
                    )
                    session.add(policy)
                else:
                    policy.enabled = enabled
                    policy.updated_at = datetime.now(UTC)
                await session.flush()
                session.add(
                    MemoryOperationLog(
                        operator=operator,
                        target_type="memory_scope_policy",
                        target_id=f"{owner_scope_id}->{target_scope_id}",
                        action="enable" if enabled else "disable",
                        reason=reason,
                        payload={
                            "owner_scope_id": owner_scope_id,
                            "target_scope_id": target_scope_id,
                            "sharing_mode": sharing_mode,
                        },
                    )
                )
                await session.flush()
                await session.refresh(policy)
                return policy

    async def list_memory_scope_policies(
        self,
        *,
        owner_scope_id: str | None = None,
        enabled: bool = True,
        limit: int = 50,
    ) -> list[MemoryScopePolicyRecord]:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(MemoryScopePolicyRecord).where(
                col(MemoryScopePolicyRecord.enabled) == enabled
            )
            if owner_scope_id:
                stmt = stmt.where(
                    col(MemoryScopePolicyRecord.owner_scope_id) == owner_scope_id
                )
            stmt = stmt.order_by(desc(MemoryScopePolicyRecord.updated_at)).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def upsert_memory_tuning_task(
        self,
        *,
        task_id: str,
        task_type: str,
        target_scope: str,
        candidate_config: dict | None = None,
        evaluation_result: dict | None = None,
        status: str = "pending",
    ) -> MemoryTuningTask:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(MemoryTuningTask).where(
                        col(MemoryTuningTask.task_id) == task_id
                    )
                )
                task = result.scalar_one_or_none()
                if task is None:
                    task = MemoryTuningTask(
                        task_id=task_id,
                        task_type=task_type,
                        target_scope=target_scope,
                        candidate_config=candidate_config or {},
                        evaluation_result=evaluation_result or {},
                        status=status,
                    )
                    session.add(task)
                else:
                    task.task_type = task_type
                    task.target_scope = target_scope
                    task.candidate_config = candidate_config or {}
                    task.evaluation_result = evaluation_result or {}
                    task.status = status
                    task.updated_at = datetime.now(UTC)
                await session.flush()
                await session.refresh(task)
                return task

    async def list_memory_tuning_tasks(
        self,
        *,
        target_scope: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[MemoryTuningTask]:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(MemoryTuningTask)
            if target_scope:
                stmt = stmt.where(col(MemoryTuningTask.target_scope) == target_scope)
            if status:
                stmt = stmt.where(col(MemoryTuningTask.status) == status)
            stmt = stmt.order_by(desc(MemoryTuningTask.updated_at)).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def insert_memory_operation_log(
        self,
        *,
        operator: str,
        target_type: str,
        target_id: str,
        action: str,
        reason: str | None = None,
        payload: dict | None = None,
    ) -> MemoryOperationLog:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                record = MemoryOperationLog(
                    operator=operator,
                    target_type=target_type,
                    target_id=target_id,
                    action=action,
                    reason=reason,
                    payload=payload or {},
                )
                session.add(record)
                await session.flush()
                await session.refresh(record)
                return record

    async def list_memory_operation_logs(
        self,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryOperationLog]:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(MemoryOperationLog)
            if target_type:
                stmt = stmt.where(col(MemoryOperationLog.target_type) == target_type)
            if target_id:
                stmt = stmt.where(col(MemoryOperationLog.target_id) == target_id)
            stmt = (
                stmt.order_by(desc(MemoryOperationLog.created_at))
                .offset(max(offset, 0))
                .limit(max(limit, 1))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_memory_operation_logs(
        self,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> int:
        async with self.get_db() as session:
            session: AsyncSession
            stmt = select(func.count()).select_from(MemoryOperationLog)
            if target_type:
                stmt = stmt.where(col(MemoryOperationLog.target_type) == target_type)
            if target_id:
                stmt = stmt.where(col(MemoryOperationLog.target_id) == target_id)
            result = await session.execute(stmt)
            return int(result.scalar_one() or 0)

    # ====
    # Conversation Management
    # ====

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

    async def insert_platform_message_history(
        self,
        platform_id: str,
        user_id: str,
        content: dict,
        sender_id: str | None = None,
        sender_name: str | None = None,
        role: str = "user",
        is_group: bool = False,
        llm_checkpoint_id: str | None = None,
        max_messages: int | None = None,
    ) -> PlatformMessageHistory:
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
                    role=role,
                    is_group=is_group,
                    llm_checkpoint_id=llm_checkpoint_id,
                )
                session.add(new_history)
                await session.flush()
                if max_messages is not None:
                    keep_count = max(1, int(max_messages))
                    keep_ids = (
                        select(PlatformMessageHistory.id)
                        .where(
                            col(PlatformMessageHistory.platform_id) == platform_id,
                            col(PlatformMessageHistory.user_id) == user_id,
                            col(PlatformMessageHistory.is_group) == is_group,
                        )
                        .order_by(desc(PlatformMessageHistory.id))
                        .limit(keep_count)
                    )
                    await session.execute(
                        delete(PlatformMessageHistory).where(
                            col(PlatformMessageHistory.platform_id) == platform_id,
                            col(PlatformMessageHistory.user_id) == user_id,
                            col(PlatformMessageHistory.is_group) == is_group,
                            col(PlatformMessageHistory.id).not_in(keep_ids),
                        )
                    )
                return new_history

    async def update_platform_message_history(
        self,
        message_id: int,
        content: dict | None = None,
        role: str | None = None,
        llm_checkpoint_id: str | None = None,
    ) -> None:
        """Update a platform message history record."""
        values = {}
        if content is not None:
            values["content"] = content
        if role is not None:
            values["role"] = role
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
        platform_id: str,
        user_id: str,
        offset_sec: int = 86400,
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
        platform_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        *,
        is_group: bool | None = None,
        before_id: int | None = None,
    ) -> list[PlatformMessageHistory]:
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
            if is_group is not None:
                query = query.where(PlatformMessageHistory.is_group == is_group)
            if before_id is not None:
                query = query.where(PlatformMessageHistory.id < before_id)
            result = await session.execute(query.offset(offset).limit(page_size))
            return list(result.scalars().all())

    async def get_group_message_history(
        self,
        platform_id: str,
        group_id: str,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[PlatformMessageHistory]:
        """Return only explicitly marked rows for one group scope."""
        return await self.get_platform_message_history(
            platform_id,
            group_id,
            page=1,
            page_size=max(1, min(int(limit), 500)),
            is_group=True,
            before_id=before_id,
        )

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
            now = datetime.now(UTC)
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
                    .values(last_used_at=datetime.now(UTC)),
                )

    async def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = (
                    update(ApiKey)
                    .where(col(ApiKey.key_id) == key_id)
                    .values(revoked_at=datetime.now(UTC))
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
        persona_id: str,
        system_prompt: str,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        custom_error_message: str | None = None,
        folder_id: str | None = None,
        sort_order: int = 0,
    ) -> Persona:
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

    async def get_persona_by_id(self, persona_id: str) -> Persona | None:
        """Get a persona by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Persona).where(Persona.persona_id == persona_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_personas(self) -> list[Persona]:
        """Get all personas for a specific bot."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Persona)
            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_persona(
        self,
        persona_id: str,
        system_prompt: str | None = None,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None | object = NOT_GIVEN,
        skills: list[str] | None | object = NOT_GIVEN,
        custom_error_message: str | None | object = NOT_GIVEN,
    ) -> Persona | None:
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

    async def insert_preference_or_update(
        self,
        scope: str,
        scope_id: str,
        key: str,
        value: dict,
    ) -> Preference:
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

    async def get_preference(
        self,
        scope: str,
        scope_id: str,
        key: str,
    ) -> Preference | None:
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

    async def get_preferences(
        self,
        scope: str | None = None,
        scope_id: str | None = None,
        key: str | None = None,
    ) -> list[Preference]:
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
            return list(result.scalars().all())

    async def remove_preference(self, scope: str, scope_id: str, key: str) -> None:
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

    async def clear_preferences(self, scope: str, scope_id: str) -> None:
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
        """Create or update alias metadata for a UMO."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(UmoAlias).where(col(UmoAlias.umo) == umo)
                )
                alias = result.scalar_one_or_none()
                if alias:
                    alias.creator_sender_id = creator_sender_id
                    alias.auto_name = auto_name
                    alias.user_alias = user_alias
                    alias.updated_at = datetime.now(UTC)
                else:
                    alias = UmoAlias(
                        umo=umo,
                        creator_sender_id=creator_sender_id,
                        auto_name=auto_name,
                        user_alias=user_alias,
                    )
                    session.add(alias)
                await session.flush()
                await session.refresh(alias)
                return alias

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
