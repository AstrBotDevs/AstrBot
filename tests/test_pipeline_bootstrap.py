"""Tests for astrbot.core.pipeline.bootstrap module."""

import pytest

from astrbot.core.pipeline.bootstrap import ensure_builtin_stages_registered


class TestPipelineBootstrap:
    """Smoke tests for pipeline bootstrap utilities."""

    def test_module_import(self):
        """Verify the bootstrap module can be imported."""
        import astrbot.core.pipeline.bootstrap  # noqa: F811
        assert hasattr(astrbot.core.pipeline.bootstrap, "ensure_builtin_stages_registered")

    def test_ensure_builtin_stages_registered_is_callable(self):
        """Verify ensure_builtin_stages_registered is a function."""
        assert callable(ensure_builtin_stages_registered)

    def test_ensure_builtin_stages_registered_runs(self):
        """Verify ensure_builtin_stages_registered runs without error."""
        # Should be idempotent and not raise
        ensure_builtin_stages_registered()

    def test_registered_stages_contains_expected(self):
        """Verify that after registration, expected stage names are present."""
        from astrbot.core.pipeline.stage import registered_stages

        ensure_builtin_stages_registered()
        stage_names = {cls.__name__ for cls in registered_stages}
        expected = {
            "WakingCheckStage",
            "WhitelistCheckStage",
            "SessionStatusCheckStage",
            "RateLimitStage",
            "ContentSafetyCheckStage",
            "PreProcessStage",
            "ProcessStage",
            "ResultDecorateStage",
            "RespondStage",
        }
        assert expected.issubset(stage_names), (
            f"Missing stages: {expected - stage_names}"
        )
