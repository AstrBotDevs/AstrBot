"""Tests for astrbot.core.pipeline.respond.stage module."""

import pytest

from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.pipeline.stage import registered_stages, Stage


class TestRespondStage:
    """Smoke tests for RespondStage."""

    def test_module_import(self):
        """Verify the respond stage module can be imported."""
        import astrbot.core.pipeline.respond.stage  # noqa: F811
        assert hasattr(
            astrbot.core.pipeline.respond.stage,
            "RespondStage",
        )

    def test_class_exists_and_is_stage_subclass(self):
        """Verify RespondStage subclasses Stage."""
        assert issubclass(RespondStage, Stage)

    def test_class_is_registered(self):
        """Verify RespondStage appears in registered_stages."""
        stage_names = {cls.__name__ for cls in registered_stages}
        assert "RespondStage" in stage_names

    def test_class_has_required_methods(self):
        """Verify RespondStage has initialize and process methods."""
        assert hasattr(RespondStage, "initialize")
        assert hasattr(RespondStage, "process")

    def test_component_validators_defined(self):
        """Verify _component_validators class attribute exists."""
        assert hasattr(RespondStage, "_component_validators")
        assert isinstance(RespondStage._component_validators, dict)
