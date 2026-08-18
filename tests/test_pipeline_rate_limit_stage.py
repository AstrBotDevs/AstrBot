"""Tests for astrbot.core.pipeline.rate_limit_check.stage module."""

from unittest.mock import MagicMock

import pytest

from astrbot.core.pipeline.rate_limit_check.stage import RateLimitStage
from astrbot.core.pipeline.stage import registered_stages, Stage


class TestRateLimitStage:
    """Smoke tests for RateLimitStage."""

    def test_module_import(self):
        """Verify the rate_limit_check stage module can be imported."""
        import astrbot.core.pipeline.rate_limit_check.stage  # noqa: F811
        assert hasattr(
            astrbot.core.pipeline.rate_limit_check.stage,
            "RateLimitStage",
        )

    def test_class_exists_and_is_stage_subclass(self):
        """Verify RateLimitStage subclasses Stage."""
        assert issubclass(RateLimitStage, Stage)

    def test_class_is_registered(self):
        """Verify RateLimitStage appears in registered_stages."""
        stage_names = {cls.__name__ for cls in registered_stages}
        assert "RateLimitStage" in stage_names

    def test_class_has_required_methods(self):
        """Verify RateLimitStage has initialize and process methods."""
        assert hasattr(RateLimitStage, "initialize")
        assert hasattr(RateLimitStage, "process")

    def test_default_attributes_initialized(self):
        """Verify RateLimitStage initializes default attributes."""
        instance = RateLimitStage()
        assert hasattr(instance, "event_timestamps")
        assert hasattr(instance, "locks")
        assert hasattr(instance, "rate_limit_count")
        assert hasattr(instance, "rate_limit_time")
