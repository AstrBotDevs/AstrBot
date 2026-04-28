"""Tests for astrbot.core.pipeline.process_stage.stage module."""

import pytest

from astrbot.core.pipeline.process_stage.stage import ProcessStage
from astrbot.core.pipeline.stage import registered_stages, Stage


class TestProcessStage:
    """Smoke tests for ProcessStage."""

    def test_module_import(self):
        """Verify the process_stage module can be imported."""
        import astrbot.core.pipeline.process_stage.stage  # noqa: F811
        assert hasattr(
            astrbot.core.pipeline.process_stage.stage,
            "ProcessStage",
        )

    def test_class_exists_and_is_stage_subclass(self):
        """Verify ProcessStage subclasses Stage."""
        assert issubclass(ProcessStage, Stage)

    def test_class_is_registered(self):
        """Verify ProcessStage appears in registered_stages."""
        stage_names = {cls.__name__ for cls in registered_stages}
        assert "ProcessStage" in stage_names

    def test_class_has_required_methods(self):
        """Verify ProcessStage has initialize and process methods."""
        assert hasattr(ProcessStage, "initialize")
        assert hasattr(ProcessStage, "process")
