"""Smoke tests for critical startup and import paths."""


import subprocess
import sys
from pathlib import Path

from astrbot.core.pipeline.bootstrap import builtin_stage_classes
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party import (
    ThirdPartyAgentSubStage,
)
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


def test_smoke_pipeline_stage_classes_match_fixed_order() -> None:
    stages = builtin_stage_classes()

    assert tuple(stage.__name__ for stage in stages) == STAGES_ORDER
    assert len({stage.__name__ for stage in stages}) == len(stages)


def test_smoke_agent_sub_stages_are_private_agent_request_helpers() -> None:
    """Agent request helpers are not independently schedulable pipeline stages."""
    assert InternalAgentSubStage.__base__ is object
    assert ThirdPartyAgentSubStage.__base__ is object


def test_pipeline_package_exports_remain_compatible() -> None:
    import astrbot.core.pipeline as pipeline

    assert pipeline.ProcessStage is not None
    assert pipeline.RespondStage is not None
    assert isinstance(pipeline.STAGES_ORDER, tuple)
    assert "ProcessStage" in pipeline.STAGES_ORDER


def test_builtin_stage_classes_are_immutable_snapshots() -> None:
    first = builtin_stage_classes()
    second = builtin_stage_classes()

    expected_stage_names = {
        "WakingCheckStage",
        "WhitelistCheckStage",
        "SessionStatusCheckStage",
        "RateLimitStage",
        "ContentSafetyCheckStage",
        "PreProcessStage",
        "GroupMessageHistoryStage",
        "ProcessStage",
        "ResultDecorateStage",
        "RespondStage",
    }

    assert expected_stage_names == {stage.__name__ for stage in first}
    assert first == second
    assert isinstance(first, tuple)


def test_pipeline_import_is_stable_with_mocked_apscheduler() -> None:
    """Regression: importing pipeline should not require cron/apscheduler modules."""
    code = (
        "import sys;"
        "from unittest.mock import MagicMock;"
        "mock_apscheduler = MagicMock();"
        "mock_apscheduler.schedulers = MagicMock();"
        "mock_apscheduler.schedulers.asyncio = MagicMock();"
        "mock_apscheduler.schedulers.background = MagicMock();"
        "mock_apscheduler.triggers = MagicMock();"
        "mock_apscheduler.triggers.cron = MagicMock();"
        "mock_apscheduler.triggers.date = MagicMock();"
        "sys.modules['apscheduler'] = mock_apscheduler;"
        "sys.modules['apscheduler.schedulers'] = mock_apscheduler.schedulers;"
        "sys.modules['apscheduler.schedulers.asyncio'] = mock_apscheduler.schedulers.asyncio;"
        "sys.modules['apscheduler.schedulers.background'] = mock_apscheduler.schedulers.background;"
        "sys.modules['apscheduler.triggers'] = mock_apscheduler.triggers;"
        "sys.modules['apscheduler.triggers.cron'] = mock_apscheduler.triggers.cron;"
        "sys.modules['apscheduler.triggers.date'] = mock_apscheduler.triggers.date;"
        "import astrbot.core.pipeline as pipeline;"
        "assert pipeline.ProcessStage is not None;"
        "assert pipeline.RespondStage is not None"
    )
    _run_code_in_fresh_interpreter(
        code,
        "Pipeline import should not depend on real apscheduler package.",
    )
