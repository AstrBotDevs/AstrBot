# Linux Desktop Plugin Install Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make AstrBot recognize the desktop backend runtime when `ASTRBOT_DESKTOP_CLIENT=1` even if Python is not frozen, so Linux desktop plugin installs use `data/site-packages` correctly.

**Architecture:** Keep the runtime contract narrow by treating `ASTRBOT_DESKTOP_CLIENT` as the authoritative desktop-backend signal inside AstrBot. Update only the shared runtime detector and cover the affected installer/root-path behavior with regression tests so desktop launch behavior remains stable without changing unrelated frozen-runtime code.

**Tech Stack:** Python 3.12+, pytest, unittest.mock, AstrBot runtime utility modules.

---

### Task 1: Add runtime-detection regression coverage

**Files:**
- Create: `tests/test_runtime_env.py`
- Modify: `astrbot/core/utils/runtime_env.py`

**Step 1: Write the failing test**

```python
from astrbot.core.utils.runtime_env import is_packaged_desktop_runtime


def test_desktop_client_env_marks_desktop_runtime_without_frozen(monkeypatch):
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delattr("sys.frozen", raising=False)

    assert is_packaged_desktop_runtime() is True
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_runtime_env.py -q`
Expected: FAIL because desktop runtime still requires `sys.frozen`.

**Step 3: Write minimal implementation**

```python
def is_packaged_desktop_runtime() -> bool:
    return os.environ.get("ASTRBOT_DESKTOP_CLIENT") == "1"
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_runtime_env.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_runtime_env.py astrbot/core/utils/runtime_env.py
git commit -m "fix: detect desktop runtime without frozen python"
```

### Task 2: Add plugin installer regression coverage

**Files:**
- Create: `tests/test_pip_installer.py`
- Modify: `astrbot/core/utils/pip_installer.py`

**Step 1: Write the failing test**

```python
import pytest

from astrbot.core.utils.pip_installer import PipInstaller


@pytest.mark.asyncio
async def test_install_targets_site_packages_for_desktop_client(monkeypatch, tmp_path):
    recorded_args = []

    async def fake_run(args):
        recorded_args.append(args)
        return 0

    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delattr("sys.frozen", raising=False)
    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", lambda self, args: fake_run(args))
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer.get_astrbot_site_packages_path",
        lambda: str(tmp_path / "site-packages"),
    )

    installer = PipInstaller("")
    await installer.install(package_name="demo-package")

    assert "--target" in recorded_args[0]
    assert str(tmp_path / "site-packages") in recorded_args[0]
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pip_installer.py -q`
Expected: FAIL because installer still skips desktop `--target` branch when `sys.frozen` is false.

**Step 3: Keep implementation minimal**

Use the Task 1 runtime detector change only. Do not add a second branch in `PipInstaller` unless the new test exposes another issue.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pip_installer.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_pip_installer.py astrbot/core/utils/runtime_env.py
git commit -m "test: cover desktop plugin install target path"
```

### Task 3: Verify root-path behavior and targeted suite

**Files:**
- Modify: `tests/test_runtime_env.py`
- Inspect: `astrbot/core/utils/astrbot_path.py`

**Step 1: Add a root-path regression test**

```python
from astrbot.core.utils.astrbot_path import get_astrbot_root


def test_desktop_client_uses_home_root_without_explicit_astrbot_root(monkeypatch):
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delenv("ASTRBOT_ROOT", raising=False)
    monkeypatch.delattr("sys.frozen", raising=False)

    assert get_astrbot_root().endswith(".astrbot")
```

**Step 2: Run targeted tests**

Run: `.venv/bin/python -m pytest tests/test_runtime_env.py tests/test_pip_installer.py tests/test_dashboard.py -q`
Expected: PASS

**Step 3: Run lint on changed files**

Run: `.venv/bin/ruff check astrbot/core/utils/runtime_env.py tests/test_runtime_env.py tests/test_pip_installer.py`
Expected: PASS

**Step 4: Commit**

```bash
git add tests/test_runtime_env.py tests/test_pip_installer.py astrbot/core/utils/runtime_env.py docs/plans/2026-03-07-linux-desktop-plugin-install-design.md docs/plans/2026-03-07-linux-desktop-plugin-install.md
git commit -m "fix: support desktop plugin installs without frozen python"
```
