"""Keep routine image-context builds free of memory sampling logs."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import test_process_stage_images as image_support
from test_process_stage_images import make_event

from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.pipeline.process_stage.stage import ProcessStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent


@pytest.fixture
def image_harness(tmp_path, monkeypatch):
    """Reuse the established ProcessStage provider fixture in this module."""
    return image_support.harness.__wrapped__(tmp_path, monkeypatch)


async def _run_process_stage(harness, event: AstrMessageEvent) -> None:
    """Run the real process stage and consume any returned stream."""
    if harness.config["provider_settings"].get("image_context_enabled", True):
        conversation = (
            harness.context.conversation_manager.get_conversation.return_value
        )
        conversation.user_id = event.unified_msg_origin
        conversation.platform_id = event.get_platform_id()
    stage = ProcessStage()
    await stage.initialize(harness.ctx)
    async for _ in stage.process(event):
        result = event.get_result()
        if result and result.async_stream:
            async for _ in result.async_stream:
                pass


@pytest.mark.asyncio
async def test_image_context_build_emits_no_memory_sampling_logs(
    image_harness, monkeypatch
):
    image_harness.config["provider_settings"]["image_context_enabled"] = True
    info = MagicMock()
    warning = MagicMock()
    monkeypatch.setattr(internal.logger, "info", info)
    monkeypatch.setattr(internal.logger, "warning", warning)

    await _run_process_stage(image_harness, make_event())

    assert image_harness.provider.text_chat.await_count == 1
    assert not any(
        "Image context memory" in str(call.args[0])
        for call in (*info.call_args_list, *warning.call_args_list)
        if call.args
    )
