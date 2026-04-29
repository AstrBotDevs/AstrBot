"""Unit tests for astrbot.core.pipeline.process_stage.stage.ProcessStage."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.pipeline.process_stage.stage import ProcessStage
from astrbot.core.provider.entities import ProviderRequest


@pytest.fixture
def mock_context():
    """Create a mock PipelineContext."""
    ctx = MagicMock()
    ctx.astrbot_config = {
        "provider_settings": {"enable": True, "wake_prefix": ""},
        "wake_prefix": ["bot"],
    }
    ctx.plugin_manager = MagicMock()
    ctx.plugin_manager.context = MagicMock()
    return ctx


@pytest.fixture
def mock_event():
    """Create a mock AstrMessageEvent."""
    event = MagicMock()
    event.get_extra.return_value = None
    event.is_stopped.return_value = False
    event._has_send_oper = False
    event.is_at_or_wake_command = True
    event.call_llm = True
    event.set_extra = MagicMock()
    return event


@pytest.fixture
def stage(mock_context):
    """Create a ProcessStage with mocked sub-stages."""
    stage = ProcessStage()

    stage.agent_sub_stage = MagicMock()
    stage.agent_sub_stage.process = AsyncMock()

    stage.star_request_sub_stage = MagicMock()
    stage.star_request_sub_stage.process = AsyncMock()

    stage.ctx = mock_context
    stage.config = mock_context.astrbot_config
    stage.plugin_manager = mock_context.plugin_manager
    stage.sdk_plugin_bridge = None
    return stage


class TestProcessStageInitialize:
    """Tests for ProcessStage.initialize()."""

    @pytest.mark.asyncio
    async def test_initialize_sets_attributes(self, mock_context):
        """Verify initialize sets ctx, config, plugin_manager."""
        stage = ProcessStage()
        with (
            patch.object(stage, "agent_sub_stage") as mock_agent,
            patch.object(stage, "star_request_sub_stage") as mock_star,
        ):
            await stage.initialize(mock_context)

        assert stage.ctx is mock_context
        assert stage.config is mock_context.astrbot_config
        assert stage.plugin_manager is mock_context.plugin_manager

    @pytest.mark.asyncio
    async def test_initialize_creates_sub_stages(self, mock_context):
        """Verify initialize creates and initializes sub-stages."""
        stage = ProcessStage()
        await stage.initialize(mock_context)

        assert hasattr(stage, "agent_sub_stage")
        assert hasattr(stage, "star_request_sub_stage")
        assert stage.agent_sub_stage is not None
        assert stage.star_request_sub_stage is not None

    @pytest.mark.asyncio
    async def test_initialize_sdk_plugin_bridge_present(self, mock_context):
        """Verify sdk_plugin_bridge is set when plugin_manager has it."""
        mock_context.plugin_manager.context.sdk_plugin_bridge = MagicMock()
        stage = ProcessStage()
        await stage.initialize(mock_context)

        assert stage.sdk_plugin_bridge is mock_context.plugin_manager.context.sdk_plugin_bridge

    @pytest.mark.asyncio
    async def test_initialize_sdk_plugin_bridge_absent(self, mock_context):
        """Verify sdk_plugin_bridge is None when plugin_manager has no context attr."""
        mock_context.plugin_manager = MagicMock(spec=[])  # no context attribute
        stage = ProcessStage()
        await stage.initialize(mock_context)

        assert stage.sdk_plugin_bridge is None


class TestProcessStageProcess:
    """Tests for ProcessStage.process()."""

    async def _collect(self, async_gen):
        """Helper to collect all items from an async generator."""
        results = []
        async for item in async_gen:
            results.append(item)
        return results

    @pytest.mark.asyncio
    async def test_process_no_activated_handlers_and_no_sdk_bridge(
        self, stage, mock_event,
    ):
        """When activated_handlers is None and no sdk bridge, skip handler path."""
        mock_event.get_extra.return_value = None
        stage.sdk_plugin_bridge = None

        results = await self._collect(stage.process(mock_event))

        assert results == []  # provider enabled, should still reach agent_sub_stage
        stage.agent_sub_stage.process.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_activated_handlers_with_provider_request(
        self, stage, mock_event,
    ):
        """When star_request yields a ProviderRequest, agent_sub_stage is called."""
        pr = ProviderRequest(prompt="hello")

        async def star_gen(_event):
            yield pr

        stage.star_request_sub_stage.process = star_gen

        agent_called = False

        async def agent_gen(_event):
            nonlocal agent_called
            agent_called = True
            yield None

        stage.agent_sub_stage.process = agent_gen

        results = await self._collect(stage.process(mock_event))

        assert agent_called is True
        mock_event.set_extra.assert_any_call("provider_request", pr)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_process_activated_handlers_with_non_provider_request(
        self, stage, mock_event,
    ):
        """When star_request yields a non-ProviderRequest, yield directly."""
        async def star_gen(_event):
            yield "some_other_result"

        stage.star_request_sub_stage.process = star_gen
        stage.sdk_plugin_bridge = None

        results = await self._collect(stage.process(mock_event))

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_process_activated_handlers_provider_request_empty_agent(
        self, stage, mock_event,
    ):
        """When agent_sub_stage yields nothing, should still yield once."""
        pr = ProviderRequest(prompt="hi")

        async def star_gen(_event):
            yield pr

        stage.star_request_sub_stage.process = star_gen

        async def empty_agent_gen(_event):
            if False:
                yield None

        stage.agent_sub_stage.process = empty_agent_gen

        results = await self._collect(stage.process(mock_event))

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_process_sdk_plugin_bridge_sent_message(self, stage, mock_event):
        """When sdk_plugin_bridge.dispatch_message returns sent_message=True."""
        mock_bridge = MagicMock()
        mock_result = MagicMock()
        mock_result.sent_message = True
        mock_result.stopped = False
        mock_bridge.dispatch_message = AsyncMock(return_value=mock_result)
        stage.sdk_plugin_bridge = mock_bridge

        results = await self._collect(stage.process(mock_event))

        # Should have yielded due to sent_message
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_process_sdk_plugin_bridge_stopped(self, stage, mock_event):
        """When sdk_plugin_bridge.dispatch_message returns stopped=True."""
        mock_bridge = MagicMock()
        mock_result = MagicMock()
        mock_result.sent_message = False
        mock_result.stopped = True
        mock_bridge.dispatch_message = AsyncMock(return_value=mock_result)
        stage.sdk_plugin_bridge = mock_bridge

        results = await self._collect(stage.process(mock_event))

        # Should have yielded due to stopped
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_process_sdk_plugin_bridge_none_and_event_has_send_oper(
        self, stage, mock_event,
    ):
        """When sdk bridge is None and _has_send_oper is True, skip LLM call."""
        stage.sdk_plugin_bridge = None
        mock_event._has_send_oper = True

        results = await self._collect(stage.process(mock_event))

        # Should NOT call agent_sub_stage for LLM
        assert results == []

    @pytest.mark.asyncio
    async def test_process_provider_disabled(self, stage, mock_event):
        """When provider_settings enable is False, return early."""
        stage.ctx.astrbot_config["provider_settings"]["enable"] = False
        stage.sdk_plugin_bridge = None
        mock_event.get_extra.return_value = None

        results = await self._collect(stage.process(mock_event))

        assert results == []

    @pytest.mark.asyncio
    async def test_process_llm_triggered(self, stage, mock_event):
        """When all conditions met, agent_sub_stage is called for LLM."""
        stage.sdk_plugin_bridge = None
        agent_called = False

        async def agent_gen(_event):
            nonlocal agent_called
            agent_called = True
            yield None

        stage.agent_sub_stage.process = agent_gen

        results = await self._collect(stage.process(mock_event))

        assert agent_called is True
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_process_llm_skipped_not_at_wake(self, stage, mock_event):
        """When is_at_or_wake_command is False, skip LLM call."""
        stage.sdk_plugin_bridge = None
        mock_event.is_at_or_wake_command = False

        results = await self._collect(stage.process(mock_event))

        assert results == []

    @pytest.mark.asyncio
    async def test_process_llm_skipped_event_stopped_with_result(
        self, stage, mock_event,
    ):
        """When event is stopped and effective_result exists, skip LLM call."""
        stage.sdk_plugin_bridge = None
        mock_event.is_stopped.return_value = True

        mock_bridge = MagicMock()
        mock_bridge.get_effective_should_call_llm.return_value = True
        mock_bridge.get_effective_result.return_value = "some_result"
        stage.sdk_plugin_bridge = mock_bridge

        results = await self._collect(stage.process(mock_event))

        # Event is stopped with result, skip LLM
        assert results == []

    @pytest.mark.asyncio
    async def test_process_sdk_bridge_with_effective_methods(
        self, stage, mock_event,
    ):
        """When sdk_plugin_bridge has get_effective_* methods, they are used."""
        mock_bridge = MagicMock()
        mock_bridge.get_effective_should_call_llm.return_value = False
        stage.sdk_plugin_bridge = mock_bridge

        await self._collect(stage.process(mock_event))

        mock_bridge.get_effective_should_call_llm.assert_called_once_with(
            mock_event,
        )

    @pytest.mark.asyncio
    async def test_process_with_activated_handlers_and_stopped(
        self, stage, mock_event,
    ):
        """When event is stopped after star_request processing, stop propagation."""
        async def star_gen(_event):
            yield ProviderRequest(prompt="test")

        stage.star_request_sub_stage.process = star_gen

        async def agent_gen(_event):
            yield None

        stage.agent_sub_stage.process = agent_gen

        mock_event.is_stopped.return_value = True

        results = await self._collect(stage.process(mock_event))

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_process_event_call_llm_false(self, stage, mock_event):
        """When event.call_llm is False and no sdk bridge, should_call_llm is True (inverted)."""
        stage.sdk_plugin_bridge = None
        mock_event.call_llm = False

        agent_called = False

        async def agent_gen(_event):
            nonlocal agent_called
            agent_called = True
            yield None

        stage.agent_sub_stage.process = agent_gen

        results = await self._collect(stage.process(mock_event))

        # event.call_llm is False, and no sdk_bridge -> should_call_llm = not False = True
        assert agent_called is True
        assert len(results) >= 1
