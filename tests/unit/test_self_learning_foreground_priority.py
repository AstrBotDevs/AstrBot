import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from data.plugins.astrbot_plugin_self_learning.core.interfaces import AnalysisResult
from data.plugins.astrbot_plugin_self_learning.services.learning.group_orchestrator import (
    GroupLearningOrchestrator,
)
from data.plugins.astrbot_plugin_self_learning.services.learning.persona_learning import (
    PersonaLearningModule,
)


@pytest.mark.asyncio
async def test_automatic_learning_waits_for_foreground_reply_window() -> None:
    progressive = SimpleNamespace(start_learning=AsyncMock(return_value=True))
    orchestrator = GroupLearningOrchestrator(
        plugin_config=SimpleNamespace(
            background_learning_start_delay_seconds=30.0,
        ),
        message_collector=SimpleNamespace(),
        progressive_learning=progressive,
        qq_filter=SimpleNamespace(),
        db_manager=SimpleNamespace(),
    )

    with patch(
        "data.plugins.astrbot_plugin_self_learning.services.learning.group_orchestrator.asyncio.sleep",
        new=AsyncMock(),
    ) as sleep:
        await orchestrator._start_group_learning("group-a")

    sleep.assert_awaited_once_with(30.0)
    progressive.start_learning.assert_awaited_once_with("group-a")


@pytest.mark.asyncio
async def test_persona_candidate_does_not_mutate_active_persona() -> None:
    persona_manager = SimpleNamespace(update_persona=AsyncMock(return_value=True))
    db_manager = SimpleNamespace(add_persona_learning_review=AsyncMock(return_value=7))
    module = PersonaLearningModule(
        config=SimpleNamespace(
            use_persona_manager_updates=False,
            auto_apply_persona_updates=False,
        ),
        context=SimpleNamespace(),
        db_manager=db_manager,
        persona_manager=persona_manager,
        multidimensional_analyzer=SimpleNamespace(),
        prompts=SimpleNamespace(),
        resolve_umo=lambda group_id: group_id,
        json_serializer=str,
    )

    applied = await module.apply_persona_learning(
        "group-a",
        AnalysisResult(
            success=True,
            confidence=0.8,
            data={"enhanced_prompt": "candidate"},
            timestamp=time.time(),
        ),
        [{"message": "sample"}],
        current_persona={"prompt": "original"},
        updated_persona={"prompt": "original candidate"},
    )

    assert applied is True
    persona_manager.update_persona.assert_not_awaited()
    db_manager.add_persona_learning_review.assert_awaited_once()
