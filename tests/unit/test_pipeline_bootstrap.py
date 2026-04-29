"""Unit tests for astrbot.core.pipeline.bootstrap module."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from astrbot.core.pipeline.bootstrap import (
    _BUILTIN_STAGE_MODULES,
    _EXPECTED_STAGE_NAMES,
    _builtin_stages_registered,
    ensure_builtin_stages_registered,
)


class TestEnsureBuiltinStagesRegistered:
    """Tests for ensure_builtin_stages_registered()."""

    def teardown_method(self):
        """Reset global state after each test."""
        # Use import and direct assignment to reset
        import astrbot.core.pipeline.bootstrap as bootstrap_mod

        bootstrap_mod._builtin_stages_registered = False

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_already_registered_flag_short_circuits(self):
        """When _builtin_stages_registered is True, return immediately."""
        import astrbot.core.pipeline.bootstrap as bootstrap_mod

        bootstrap_mod._builtin_stages_registered = True

        with patch(
            "astrbot.core.pipeline.bootstrap.import_module",
        ) as mock_import:
            ensure_builtin_stages_registered()

        mock_import.assert_not_called()

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_all_expected_stages_present_skips_import(self):
        """When all expected stages are already in registered_stages, skip importing."""
        import astrbot.core.pipeline.bootstrap as bootstrap_mod

        bootstrap_mod._builtin_stages_registered = False

        # Populate registered_stages with all expected stage names
        for name in _EXPECTED_STAGE_NAMES:
            cls = MagicMock()
            cls.__name__ = name
            bootstrap_mod.registered_stages.append(cls)

        with patch(
            "astrbot.core.pipeline.bootstrap.import_module",
        ) as mock_import:
            ensure_builtin_stages_registered()

        mock_import.assert_not_called()
        assert bootstrap_mod._builtin_stages_registered is True

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_registers_missing_stages(self):
        """When stages are missing, import built-in modules."""
        import astrbot.core.pipeline.bootstrap as bootstrap_mod

        bootstrap_mod._builtin_stages_registered = False
        bootstrap_mod.registered_stages.clear()

        with patch(
            "astrbot.core.pipeline.bootstrap.import_module",
        ) as mock_import:
            ensure_builtin_stages_registered()

        expected_calls = [call(mod) for mod in _BUILTIN_STAGE_MODULES]
        mock_import.assert_has_calls(expected_calls, any_order=True)
        assert mock_import.call_count == len(_BUILTIN_STAGE_MODULES)
        assert bootstrap_mod._builtin_stages_registered is True

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_idempotent(self):
        """Calling ensure_builtin_stages_registered twice only imports once."""
        import astrbot.core.pipeline.bootstrap as bootstrap_mod

        bootstrap_mod._builtin_stages_registered = False
        bootstrap_mod.registered_stages.clear()

        with patch(
            "astrbot.core.pipeline.bootstrap.import_module",
        ) as mock_import:
            ensure_builtin_stages_registered()
            ensure_builtin_stages_registered()

        # Should only import on first call
        mock_import.assert_called_once()

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_global_flag_set_after_import(self):
        """Verify the global flag is set after a full registration."""
        import astrbot.core.pipeline.bootstrap as bootstrap_mod

        bootstrap_mod._builtin_stages_registered = False
        bootstrap_mod.registered_stages.clear()

        with patch("astrbot.core.pipeline.bootstrap.import_module"):
            ensure_builtin_stages_registered()

        assert bootstrap_mod._builtin_stages_registered is True

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_already_registered_flag_persists(self):
        """Verify that once set, the flag persists across calls."""
        import astrbot.core.pipeline.bootstrap as bootstrap_mod

        bootstrap_mod._builtin_stages_registered = False
        bootstrap_mod.registered_stages.clear()

        with patch("astrbot.core.pipeline.bootstrap.import_module"):
            ensure_builtin_stages_registered()

        # Call again with import_module mocked to raise if called
        with patch(
            "astrbot.core.pipeline.bootstrap.import_module",
        ) as mock_import:
            ensure_builtin_stages_registered()

        mock_import.assert_not_called()

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_partial_stages_present_still_imports(self):
        """When only some expected stages are present, still import all modules."""
        import astrbot.core.pipeline.bootstrap as bootstrap_mod

        bootstrap_mod._builtin_stages_registered = False
        bootstrap_mod.registered_stages.clear()

        # Add only one of the expected stages
        cls = MagicMock()
        cls.__name__ = "ProcessStage"
        bootstrap_mod.registered_stages.append(cls)

        with patch(
            "astrbot.core.pipeline.bootstrap.import_module",
        ) as mock_import:
            ensure_builtin_stages_registered()

        expected_calls = [call(mod) for mod in _BUILTIN_STAGE_MODULES]
        mock_import.assert_has_calls(expected_calls, any_order=True)
        assert mock_import.call_count == len(_BUILTIN_STAGE_MODULES)

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_stage_names_check_exact(self):
        """Verify the check uses __name__ comparison, not identity."""
        import astrbot.core.pipeline.bootstrap as bootstrap_mod

        bootstrap_mod._builtin_stages_registered = False
        bootstrap_mod.registered_stages.clear()

        # Add stages with correct names
        for name in _EXPECTED_STAGE_NAMES:
            cls = MagicMock()
            cls.__name__ = name
            bootstrap_mod.registered_stages.append(cls)

        with patch(
            "astrbot.core.pipeline.bootstrap.import_module",
        ) as mock_import:
            ensure_builtin_stages_registered()

        mock_import.assert_not_called()

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_expected_stage_names_are_correct(self):
        """Verify _EXPECTED_STAGE_NAMES matches the expected set."""
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
        assert _EXPECTED_STAGE_NAMES == expected

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_builtin_stage_modules_count(self):
        """Verify the number of builtin stage modules matches expected."""
        assert len(_BUILTIN_STAGE_MODULES) == 9

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_all_builtin_modules_under_pipeline(self):
        """Verify all builtin modules are under astrbot.core.pipeline."""
        for mod in _BUILTIN_STAGE_MODULES:
            assert mod.startswith("astrbot.core.pipeline.")
            assert mod.endswith(".stage")

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_module_paths_alignment(self):
        """Verify each expected stage name has a corresponding module path."""
        from astrbot.core.pipeline.bootstrap import _BUILTIN_STAGE_MODULES, _EXPECTED_STAGE_NAMES

        # Derive expected names from module paths
        derived_names = set()
        for mod_path in _BUILTIN_STAGE_MODULES:
            parts = mod_path.split(".")
            # For modules like astrbot.core.pipeline.process_stage.stage
            # the stage name is found in the penultimate segment
            if parts[-2] in ("process_stage", "respond"):
                # Special cases: ProcessStage, RespondStage
                if parts[-2] == "process_stage":
                    derived_names.add("ProcessStage")
                elif parts[-2] == "respond":
                    derived_names.add("RespondStage")
                else:
                    derived_names.add(f"{parts[-2].title().replace('_', '')}Stage")
            else:
                name = parts[-2].replace("_", " ").title().replace(" ", "")
                name += "Stage"
                derived_names.add(name)

        assert _EXPECTED_STAGE_NAMES == derived_names

    @patch("astrbot.core.pipeline.bootstrap.registered_stages", new=[])
    def test_real_registration_smoke(self):
        """Smoke test: calling ensure_builtin_stages_registered with actual modules."""
        import astrbot.core.pipeline.bootstrap as bootstrap_mod

        bootstrap_mod._builtin_stages_registered = False
        bootstrap_mod.registered_stages.clear()

        # This should import the actual modules
        ensure_builtin_stages_registered()

        stage_names = {cls.__name__ for cls in bootstrap_mod.registered_stages}
        assert _EXPECTED_STAGE_NAMES.issubset(stage_names)
