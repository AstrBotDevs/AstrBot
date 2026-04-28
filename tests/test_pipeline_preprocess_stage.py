"""Tests for astrbot.core.pipeline.preprocess_stage.stage module."""

from unittest.mock import MagicMock

import pytest

from astrbot.core.pipeline.preprocess_stage.stage import PreProcessStage
from astrbot.core.pipeline.stage import registered_stages, Stage


class TestPreProcessStage:
    """Smoke tests for PreProcessStage."""

    def test_module_import(self):
        """Verify the preprocess_stage module can be imported."""
        import astrbot.core.pipeline.preprocess_stage.stage  # noqa: F811
        assert hasattr(
            astrbot.core.pipeline.preprocess_stage.stage,
            "PreProcessStage",
        )

    def test_class_exists_and_is_stage_subclass(self):
        """Verify PreProcessStage subclasses Stage."""
        assert issubclass(PreProcessStage, Stage)

    def test_class_is_registered(self):
        """Verify PreProcessStage appears in registered_stages."""
        stage_names = {cls.__name__ for cls in registered_stages}
        assert "PreProcessStage" in stage_names

    def test_class_has_required_methods(self):
        """Verify PreProcessStage has initialize and process methods."""
        assert hasattr(PreProcessStage, "initialize")
        assert hasattr(PreProcessStage, "process")
