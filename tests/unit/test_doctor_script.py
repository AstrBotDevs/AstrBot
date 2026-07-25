from pathlib import Path
from subprocess import CompletedProcess

from scripts import doctor

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_version_runs_resolved_executable(monkeypatch, tmp_path: Path) -> None:
    resolved = str(tmp_path / "pnpm.cmd")
    invoked: tuple[str, ...] | None = None

    monkeypatch.setattr(doctor.shutil, "which", lambda _command: resolved)

    def run(command, **_kwargs):
        nonlocal invoked
        invoked = command
        return CompletedProcess(command, 0, stdout="0.34.7\n", stderr="")

    monkeypatch.setattr(doctor.subprocess, "run", run)

    assert doctor.version(("pnpm", "--version"), tmp_path) == "0.34.7"
    assert invoked == (resolved, "--version")


def test_version_treats_process_start_failure_as_missing(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _command: "stale-command")

    def run(_command, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(doctor.subprocess, "run", run)

    assert doctor.version(("pnpm", "--version"), tmp_path) is None


def test_ci_pytest_runner_does_not_bypass_interpreter_teardown() -> None:
    """The CI runner must preserve pytest's normal process cleanup path."""
    script = (REPO_ROOT / "scripts" / "run_pytests_ci.sh").read_text(encoding="utf-8")

    assert "os._exit" not in script
    assert "pytest.main(" not in script
    assert 'uv run pytest "${PYTEST_TARGETS[@]}"' in script
