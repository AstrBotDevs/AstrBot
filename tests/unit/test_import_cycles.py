"""Regression tests for import-cycle fixes in pipeline and agent modules."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_critical_imports_work_in_fresh_interpreter() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    code = (
        "import importlib;"
        "mods=["
        "'astrbot.core.astr_main_agent',"
        "'astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal',"
        "'astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party'"
        "];"
        "[importlib.import_module(m) for m in mods]"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        "Import cycle regression detected.\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}\n"
    )


def test_pipeline_package_exports_remain_compatible() -> None:
    import astrbot.core.pipeline as pipeline

    assert pipeline.ProcessStage is not None
    assert pipeline.RespondStage is not None
    assert isinstance(pipeline.STAGES_ORDER, list)
    assert "ProcessStage" in pipeline.STAGES_ORDER


def test_builtin_stage_bootstrap_is_idempotent() -> None:
    from astrbot.core.pipeline.bootstrap import ensure_builtin_stages_registered
    from astrbot.core.pipeline.stage import registered_stages

    ensure_builtin_stages_registered()
    before_count = len(registered_stages)
    stage_names = {cls.__name__ for cls in registered_stages}

    expected_stage_names = {
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

    assert expected_stage_names.issubset(stage_names)

    ensure_builtin_stages_registered()
    assert len(registered_stages) == before_count
