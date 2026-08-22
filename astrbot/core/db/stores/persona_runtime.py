from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, desc, select

from astrbot.core.db.po import (
    PersonaBehaviorPolicy,
    PersonaExpressionAsset,
    PersonaJargonAsset,
    PersonaSessionState,
)


class PersonaRuntimeStoreMixin:
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
