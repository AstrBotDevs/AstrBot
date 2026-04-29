"""Unit tests for astrbot.core.pipeline.scheduler.PipelineScheduler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from astrbot.core.pipeline.scheduler import PipelineScheduler


@pytest.fixture
def mock_context():
    """Create a mock PipelineContext."""
    ctx = MagicMock()
    ctx.astrbot_config = {"provider_settings": {"enable": True}}
    ctx.plugin_manager = MagicMock()
    ctx.plugin_manager.context = MagicMock(spec_set=[])
    return ctx


@pytest.fixture
def mock_stage_cls():
    """Create a mock stage class that can be instantiated."""
    cls = MagicMock()
    instance = MagicMock()
    instance.initialize = AsyncMock()
    instance.process = AsyncMock()
    cls.return_value = instance
    cls.__name__ = "MockStage"
    return cls


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestPipelineSchedulerInit:
    """Tests for PipelineScheduler.__init__()."""

    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.STAGES_ORDER", ["MockStage"])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    def test_init_calls_ensure_and_sets_context(
        self, mock_ensure, mock_stages_order, mock_registered, mock_context,
    ):
        """Verify __init__ calls ensure_builtin_stages_registered and sets context."""
        mock_stage = MagicMock()
        mock_stage.__name__ = "MockStage"
        mock_registered.append(mock_stage)

        scheduler = PipelineScheduler(mock_context)

        mock_ensure.assert_called_once()
        assert scheduler.ctx is mock_context
        assert scheduler.stages == []


# ---------------------------------------------------------------------------
# Initialize
# ---------------------------------------------------------------------------


class TestPipelineSchedulerInitialize:
    """Tests for PipelineScheduler.initialize()."""

    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_initialize_creates_stage_instances(
        self, mock_ensure, mock_registered, mock_context, mock_stage_cls,
    ):
        """Verify initialize creates and initializes all registered stage instances."""
        mock_registered.append(mock_stage_cls)
        scheduler = PipelineScheduler(mock_context)

        await scheduler.initialize()

        assert len(scheduler.stages) == 1
        assert scheduler.stages[0] is mock_stage_cls.return_value
        mock_stage_cls.return_value.initialize.assert_awaited_once_with(mock_context)

    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_initialize_multiple_stages(
        self, mock_ensure, mock_registered, mock_context,
    ):
        """Verify multiple stages are initialized in order."""
        stage1_cls = MagicMock()
        stage1_cls.__name__ = "Stage1"
        stage1_instance = MagicMock()
        stage1_instance.initialize = AsyncMock()
        stage1_cls.return_value = stage1_instance

        stage2_cls = MagicMock()
        stage2_cls.__name__ = "Stage2"
        stage2_instance = MagicMock()
        stage2_instance.initialize = AsyncMock()
        stage2_cls.return_value = stage2_instance

        mock_registered.extend([stage1_cls, stage2_cls])
        scheduler = PipelineScheduler(mock_context)

        await scheduler.initialize()

        assert len(scheduler.stages) == 2
        stage1_instance.initialize.assert_awaited_once_with(mock_context)
        stage2_instance.initialize.assert_awaited_once_with(mock_context)


# ---------------------------------------------------------------------------
# _process_stages
# ---------------------------------------------------------------------------


class TestPipelineSchedulerProcessStages:
    """Tests for PipelineScheduler._process_stages()."""

    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_non_generator_stage_executed(
        self, mock_ensure, mock_registered, mock_context, mock_stage_cls,
    ):
        """Verify a non-generator stage is awaited."""
        mock_registered.append(mock_stage_cls)
        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = [mock_stage_cls.return_value]
        event = MagicMock()
        event.is_stopped.return_value = False

        await scheduler._process_stages(event)

        mock_stage_cls.return_value.process.assert_called_once_with(event)

    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_generator_stage_yields_and_next_stage_runs(
        self, mock_ensure, mock_registered, mock_context,
    ):
        """Verify a generator stage yields and the next stage runs."""
        async def gen_process(_event):
            yield None

        stage1 = MagicMock()
        stage1.process = gen_process
        stage1.__class__.__name__ = "Stage1"

        stage2 = MagicMock()
        stage2.process = AsyncMock()
        stage2.__class__.__name__ = "Stage2"

        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = [stage1, stage2]
        event = MagicMock()
        event.is_stopped.return_value = False

        await scheduler._process_stages(event)

        stage2.process.assert_called_once_with(event)

    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_generator_stage_stops_propagation(
        self, mock_ensure, mock_registered, mock_context,
    ):
        """Verify event.stop_event() breaks the pipeline in generator stage."""
        stage1_pass = [False]

        async def onion_process(_event):
            stage1_pass[0] = True
            yield None

        stage1 = MagicMock()
        stage1.process = onion_process
        stage1.__class__.__name__ = "Stage1"

        stage2 = MagicMock()
        stage2.process = AsyncMock()
        stage2.__class__.__name__ = "Stage2"

        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = [stage1, stage2]
        event = MagicMock()
        event.is_stopped = lambda: True  # always stopped

        await scheduler._process_stages(event)

        stage2.process.assert_not_called()

    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_non_generator_stage_stops_propagation(
        self, mock_ensure, mock_registered, mock_context,
    ):
        """Verify event.stop_event() breaks non-generator stage chain."""
        stage1 = MagicMock()
        stage1.process = AsyncMock()
        stage1.__class__.__name__ = "Stage1"

        stage2 = MagicMock()
        stage2.process = AsyncMock()
        stage2.__class__.__name__ = "Stage2"

        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = [stage1, stage2]
        event = MagicMock()
        event.is_stopped = lambda: True  # always stopped

        await scheduler._process_stages(event)

        stage1.process.assert_called_once_with(event)
        stage2.process.assert_not_called()

    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_generator_with_onion_recursion(
        self, mock_ensure, mock_registered, mock_context,
    ):
        """Verify generator stages recursively process subsequent stages (onion model)."""
        call_order = []

        async def onion_process(event):
            call_order.append("before_yield")
            yield None
            call_order.append("after_yield")

        stage1 = MagicMock()
        stage1.process = onion_process
        stage1.__class__.__name__ = "Stage1"

        stage2 = MagicMock()
        stage2.process = AsyncMock(side_effect=lambda e: call_order.append("stage2"))
        stage2.__class__.__name__ = "Stage2"

        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = [stage1, stage2]
        event = MagicMock()
        event.is_stopped.return_value = False

        await scheduler._process_stages(event)

        # Order: stage1 before_yield -> yield -> stage2 -> stage1 after_yield
        assert call_order == ["before_yield", "stage2", "after_yield"]


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


class TestPipelineSchedulerExecute:
    """Tests for PipelineScheduler.execute()."""

    @patch("astrbot.core.pipeline.scheduler.active_event_registry")
    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_execute_calls_process_stages(
        self, mock_ensure, mock_registered, mock_registry, mock_context,
    ):
        """Verify execute calls _process_stages and cleans up."""
        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = []
        scheduler._process_stages = AsyncMock()

        event = MagicMock()
        await scheduler.execute(event)

        scheduler._process_stages.assert_awaited_once_with(event)
        mock_registry.register.assert_called_once_with(event)
        mock_registry.unregister.assert_called_once_with(event)

    @patch("astrbot.core.pipeline.scheduler.active_event_registry")
    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_execute_webchat_event_sends_none(
        self, mock_ensure, mock_registered, mock_registry, mock_context,
    ):
        """Verify WebChatMessageEvent gets an extra None send."""
        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = []
        scheduler._process_stages = AsyncMock()

        event = MagicMock(spec=["send", "is_stopped"])
        event.__class__.__name__ = "WebChatMessageEvent"

        with patch(
            "astrbot.core.pipeline.scheduler.WebChatMessageEvent",
            event.__class__,
        ):
            await scheduler.execute(event)

        event.send.assert_awaited_once_with(None)
        mock_registry.unregister.assert_called_once_with(event)

    @patch("astrbot.core.pipeline.scheduler.active_event_registry")
    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_execute_wecom_event_sends_none(
        self, mock_ensure, mock_registered, mock_registry, mock_context,
    ):
        """Verify WecomAIBotMessageEvent gets an extra None send."""
        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = []
        scheduler._process_stages = AsyncMock()

        event = MagicMock(spec=["send", "is_stopped"])
        event.__class__.__name__ = "WecomAIBotMessageEvent"

        with patch(
            "astrbot.core.pipeline.scheduler.WecomAIBotMessageEvent",
            event.__class__,
        ):
            await scheduler.execute(event)

        event.send.assert_awaited_once_with(None)

    @patch("astrbot.core.pipeline.scheduler.active_event_registry")
    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_execute_normal_event_no_extra_send(
        self, mock_ensure, mock_registered, mock_registry, mock_context,
    ):
        """Verify regular events do not get extra None send."""
        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = []
        scheduler._process_stages = AsyncMock()

        event = MagicMock()
        event.__class__.__name__ = "NormalEvent"

        await scheduler.execute(event)

        event.send.assert_not_called()

    @patch("astrbot.core.pipeline.scheduler.active_event_registry")
    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_execute_with_sdk_plugin_bridge(
        self, mock_ensure, mock_registered, mock_registry, mock_context,
    ):
        """Verify sdk_plugin_bridge.close_request_overlay_for_event is called."""
        mock_bridge = MagicMock()
        mock_bridge.close_request_overlay_for_event = MagicMock()
        mock_context.plugin_manager.context.sdk_plugin_bridge = mock_bridge

        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = []
        scheduler._process_stages = AsyncMock()

        event = MagicMock()
        await scheduler.execute(event)

        mock_bridge.close_request_overlay_for_event.assert_called_once_with(event)

    @patch("astrbot.core.pipeline.scheduler.active_event_registry")
    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_execute_without_sdk_plugin_bridge(
        self, mock_ensure, mock_registered, mock_registry, mock_context,
    ):
        """Verify no error when sdk_plugin_bridge is absent."""
        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = []
        scheduler._process_stages = AsyncMock()

        event = MagicMock()
        await scheduler.execute(event)

        # Should not raise

    @patch("astrbot.core.pipeline.scheduler.active_event_registry")
    @patch("astrbot.core.pipeline.scheduler.registered_stages", [])
    @patch("astrbot.core.pipeline.scheduler.ensure_builtin_stages_registered")
    @pytest.mark.asyncio
    async def test_execute_unregisters_on_error(
        self, mock_ensure, mock_registered, mock_registry, mock_context,
    ):
        """Verify event is still unregistered when _process_stages raises."""
        scheduler = PipelineScheduler(mock_context)
        scheduler.stages = []
        scheduler._process_stages = AsyncMock(side_effect=RuntimeError("fail"))

        event = MagicMock()
        with pytest.raises(RuntimeError):
            await scheduler.execute(event)

        mock_registry.unregister.assert_called_once_with(event)
