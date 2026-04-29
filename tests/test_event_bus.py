"""Tests for astrbot.core.event_bus module."""

from asyncio import Queue
from unittest.mock import MagicMock

import pytest

from astrbot.core.event_bus import EventBus
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform import AstrMessageEvent


class TestEventBus:
    """Smoke tests for EventBus."""

    def test_module_import(self):
        """Verify the event_bus module can be imported."""
        import astrbot.core.event_bus  # noqa: F811
        assert hasattr(
            astrbot.core.event_bus,
            "EventBus",
        )

    def test_class_exists(self):
        """Verify EventBus class exists."""
        assert EventBus.__name__ == "EventBus"

    def test_init_requires_three_args(self):
        """Verify EventBus init requires queue, scheduler mapping, and config manager."""
        queue = Queue()
        scheduler_mapping: dict[str, PipelineScheduler] = {}
        config_mgr = MagicMock(spec=AstrBotConfigManager)
        bus = EventBus(queue, scheduler_mapping, config_mgr)
        assert bus.event_queue is queue
        assert bus.pipeline_scheduler_mapping is scheduler_mapping
        assert bus.astrbot_config_mgr is config_mgr

    def test_has_dispatch_method(self):
        """Verify EventBus has a dispatch method."""
        assert hasattr(EventBus, "dispatch")
        assert callable(EventBus.dispatch)
