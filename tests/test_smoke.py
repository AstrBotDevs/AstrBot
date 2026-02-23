"""Smoke tests for critical startup and import paths."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from astrbot.core.pipeline.bootstrap import ensure_builtin_stages_registered
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party import (
    ThirdPartyAgentSubStage,
)
from astrbot.core.pipeline.stage import Stage, registered_stages
from astrbot.core.pipeline.stage_order import STAGES_ORDER

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_code_in_fresh_interpreter(code: str, failure_message: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"{failure_message}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}\n"
    )


def test_smoke_critical_imports_in_fresh_interpreter() -> None:
    code = (
        "import importlib;"
        "mods=["
        "'astrbot.core.core_lifecycle',"
        "'astrbot.core.astr_main_agent',"
        "'astrbot.core.pipeline.scheduler',"
        "'astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal',"
        "'astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party'"
        "];"
        "[importlib.import_module(m) for m in mods]"
    )
    _run_code_in_fresh_interpreter(code, "Smoke import check failed.")


def test_smoke_pipeline_stage_registration_matches_order() -> None:
    ensure_builtin_stages_registered()
    stage_names = {cls.__name__ for cls in registered_stages}

    assert set(STAGES_ORDER).issubset(stage_names)
    assert len(stage_names) == len(registered_stages)


def test_smoke_agent_sub_stages_are_stage_subclasses() -> None:
    assert issubclass(InternalAgentSubStage, Stage)
    assert issubclass(ThirdPartyAgentSubStage, Stage)


def test_pipeline_package_exports_remain_compatible() -> None:
    import astrbot.core.pipeline as pipeline

    assert pipeline.ProcessStage is not None
    assert pipeline.RespondStage is not None
    assert isinstance(pipeline.STAGES_ORDER, list)
    assert "ProcessStage" in pipeline.STAGES_ORDER


def test_builtin_stage_bootstrap_is_idempotent() -> None:
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


def test_pipeline_import_is_stable_with_mocked_apscheduler() -> None:
    """Regression: importing pipeline should not require cron/apscheduler modules."""
    code = (
        "import sys;"
        "from unittest.mock import MagicMock;"
        "mock_apscheduler = MagicMock();"
        "mock_apscheduler.schedulers = MagicMock();"
        "mock_apscheduler.schedulers.asyncio = MagicMock();"
        "mock_apscheduler.schedulers.background = MagicMock();"
        "sys.modules['apscheduler'] = mock_apscheduler;"
        "sys.modules['apscheduler.schedulers'] = mock_apscheduler.schedulers;"
        "sys.modules['apscheduler.schedulers.asyncio'] = mock_apscheduler.schedulers.asyncio;"
        "sys.modules['apscheduler.schedulers.background'] = mock_apscheduler.schedulers.background;"
        "import astrbot.core.pipeline as pipeline;"
        "assert pipeline.ProcessStage is not None;"
        "assert pipeline.RespondStage is not None"
    )
    _run_code_in_fresh_interpreter(
        code,
        "Pipeline import should not depend on real apscheduler package.",
    )
