"""Tests for astrbot.core.pipeline.context module."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from astrbot.core.pipeline import context as pipeline_context_module
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.context_utils import call_event_hook, call_handler


class TestPipelineContext:
    """Smoke tests for PipelineContext."""

    def test_module_import(self):
        """Verify the context module can be imported."""
        import astrbot.core.pipeline.context  # noqa: F811
        assert hasattr(
            astrbot.core.pipeline.context,
            "PipelineContext",
        )

    def test_class_is_dataclass(self):
        """Verify PipelineContext is a dataclass."""
        assert hasattr(PipelineContext, "__dataclass_fields__")

    def test_class_fields(self):
        """Verify PipelineContext has the expected fields."""
        fields = {f.name for f in PipelineContext.__dataclass_fields__.values()}
        assert "astrbot_config" in fields
        assert "plugin_manager" in fields
        assert "astrbot_config_id" in fields

    def test_call_handler_is_referenced(self):
        """Verify PipelineContext references call_handler."""
        assert PipelineContext.call_handler is call_handler

    def test_call_event_hook_is_referenced(self):
        """Verify PipelineContext references call_event_hook."""
        assert PipelineContext.call_event_hook is call_event_hook
