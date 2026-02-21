"""Smoke tests for critical startup and import paths."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from astrbot.core.pipeline.bootstrap import ensure_builtin_stages_registered
from astrbot.core.pipeline.stage import Stage, registered_stages
from astrbot.core.pipeline.stage_order import STAGES_ORDER
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party import (
    ThirdPartyAgentSubStage,
)


def test_smoke_critical_imports_in_fresh_interpreter() -> None:
    repo_root = Path(__file__).resolve().parents[1]
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
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        "Smoke import check failed.\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}\n"
    )


def test_smoke_pipeline_stage_registration_matches_order() -> None:
    ensure_builtin_stages_registered()
    stage_names = {cls.__name__ for cls in registered_stages}

    assert set(STAGES_ORDER).issubset(stage_names)
    assert len(stage_names) == len(registered_stages)


def test_smoke_agent_sub_stages_are_stage_subclasses() -> None:
    assert issubclass(InternalAgentSubStage, Stage)
    assert issubclass(ThirdPartyAgentSubStage, Stage)
