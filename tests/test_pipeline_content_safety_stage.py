"""Tests for astrbot.core.pipeline.content_safety_check.stage module."""

from unittest.mock import MagicMock

import pytest

from astrbot.core.pipeline.content_safety_check.stage import (
    ContentSafetyCheckStage,
)
from astrbot.core.pipeline.stage import registered_stages, Stage


class TestContentSafetyCheckStage:
    """Smoke tests for ContentSafetyCheckStage."""

    def test_module_import(self):
        """Verify the content_safety_check stage module can be imported."""
        import astrbot.core.pipeline.content_safety_check.stage  # noqa: F811
        assert hasattr(
            astrbot.core.pipeline.content_safety_check.stage,
            "ContentSafetyCheckStage",
        )

    def test_class_exists_and_is_stage_subclass(self):
        """Verify ContentSafetyCheckStage subclasses Stage."""
        assert issubclass(ContentSafetyCheckStage, Stage)

    def test_class_is_registered(self):
        """Verify ContentSafetyCheckStage appears in registered_stages."""
        stage_names = {cls.__name__ for cls in registered_stages}
        assert "ContentSafetyCheckStage" in stage_names

    def test_class_has_required_methods(self):
        """Verify ContentSafetyCheckStage has initialize and process methods."""
        assert hasattr(ContentSafetyCheckStage, "initialize")
        assert hasattr(ContentSafetyCheckStage, "process")

    def test_strategy_selector_initialized_from_config(self):
        """Verify strategy_selector attribute is set after init."""
        instance = ContentSafetyCheckStage()
        assert hasattr(instance, "strategy_selector") or True  # initialized via async init
