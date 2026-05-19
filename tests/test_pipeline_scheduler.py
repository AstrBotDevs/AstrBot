"""Tests for astrbot.core.pipeline.scheduler module."""

from unittest.mock import MagicMock

import pytest

from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.pipeline.context import PipelineContext


class TestPipelineScheduler:
    """Smoke tests for PipelineScheduler."""

    def test_module_import(self):
        """Verify the scheduler module can be imported."""
        import astrbot.core.pipeline.scheduler  # noqa: F811
        assert hasattr(
            astrbot.core.pipeline.scheduler,
            "PipelineScheduler",
        )

    def test_class_exists(self):
        """Verify PipelineScheduler class exists."""
        assert PipelineScheduler.__name__ == "PipelineScheduler"

    def test_init_requires_context(self):
        """Verify PipelineScheduler init requires PipelineContext."""
        ctx = MagicMock(spec=PipelineContext)
        scheduler = PipelineScheduler(ctx)
        assert scheduler.ctx is ctx
        assert scheduler.stages == []
