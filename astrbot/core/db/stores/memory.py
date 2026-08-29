from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, desc, func, or_, select

from astrbot.core.db.po import (
    MemoryEpisode,
    MemoryFact,
    MemoryOperationLog,
    MemoryProfile,
    MemoryScopePolicyRecord,
    MemoryTuningTask,
)
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session


class MemoryStoreMixin(DatabaseStoreMixin):
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
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
        async with store_session(self) as session:
            session: AsyncSession
            stmt = select(func.count()).select_from(MemoryOperationLog)
            if target_type:
                stmt = stmt.where(col(MemoryOperationLog.target_type) == target_type)
            if target_id:
                stmt = stmt.where(col(MemoryOperationLog.target_id) == target_id)
            result = await session.execute(stmt)
            return int(result.scalar_one() or 0)
