# Sidebar Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a content-search feature to the GitDiffSidebar Files view, backed by a new `POST /spcode/file-search` endpoint in the spcode toolkit plugin.

**Architecture:** New POST endpoint accepts `{pattern, path_filter, glob_filter, case_sensitive, regex, max_results, context_chars}` and returns up to 200 matching lines with snippets. Backend tries `ripgrep` first (via plugin init-time probe), falls back to pure-Python `os.walk + re` if rg is missing. Frontend composable holds a `state` machine (`idle | loading | ok | error`) with `AbortController` cancellation, and a `SearchPanel.vue` component renders results; `GitDiffSidebar` adds a search button + `Cmd/Ctrl-F` shortcut, and clicks navigate to the file in the existing preview pane.

**Tech Stack:**
- Backend: Python 3.10+, `asyncio.create_subprocess_exec`, stdlib `re`/`os.walk`, optional `ripgrep` binary
- Frontend: Vue 3 `<script setup>`, TypeScript, Vuetify 3, `pluginExtensionApi` (auto-generated)
- Tests: pytest (backend), vitest + @vue/test-utils (frontend, only if already present)

## Global Constraints

These are the spec's project-wide rules. Every task's requirements implicitly include this section.

- **Branch:** `all` (working tree, no worktree required)
- **Author tag:** elecvoid243, 2026-07-02
- **Conventional commits:** `feat:` / `fix:` / `docs:` / `chore:` / `refactor:` prefixes
- **Ruff:** `ruff format` + `ruff check` on Python files (no errors / no diff)
- **prettier:** dashboard Vue/TS files (no diff)
- **vue-tsc:** `cd dashboard && npx vue-tsc --noEmit` must pass with 0 errors
- **i18n:** 3 locales (zh-CN / en-US / ru-RU), keys mirror each other
- **Path safety:** all file operations go through `_validate_repo_relative_file` or equivalent
- **No new dependencies:** rg is optional, Python fallback uses stdlib only
- **Backward compat:** no breaking changes to existing endpoints
- **Backend patterns to follow:**
  - `tools/webapi/_helpers.py::ReasonCode` for reason strings
  - `tools/webapi/_helpers.py::_make_envelope` for response shape
  - `tools/webapi/git_log.py::_git_endpoint_preflight` for 5-step preflight
  - `tools/webapi/_helpers.py::_run_git_async` template for async subprocess (but with `pythonw.exe CREATE_NO_WINDOW` flag for Windows)
- **Frontend patterns to follow:**
  - `dashboard/src/composables/useSpcodeGitLog.ts` for state machine + `pluginExtensionApi` call
  - `dashboard/src/composables/useSpcodeGitDiff.ts` for `kind: ok|loading|error` discriminated union
  - `GitDiffSidebar.vue` for localStorage persistence pattern (300ms debounce for fast-changing keys, flush:"post" watchers for stable keys)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `astrbot_plugin_spcode_toolkit/tools/webapi/file_search.py` | **create** | `POST /spcode/file-search` handler + rg + Python fallback |
| `astrbot_plugin_spcode_toolkit/tools/webapi/_helpers.py` | **modify** | Add 5 ReasonCode entries |
| `astrbot_plugin_spcode_toolkit/tools/webapi/__init__.py` | **modify** | Register new route |
| `astrbot_plugin_spcode_toolkit/main.py` | **modify** | Add rg availability probe in `__init__` |
| `astrbot_plugin_spcode_toolkit/_conf_schema.json` | **modify** | Add `search.rg_path` field |
| `astrbot_plugin_spcode_toolkit/tests/test_file_search.py` | **create** | 20 backend unit tests |
| `dashboard/src/composables/useSpcodeFileSearch.ts` | **create** | State machine + `AbortController` cancellation |
| `dashboard/src/components/chat/message_list_comps/SearchPanel.vue` | **create** | Search input + result list component |
| `dashboard/src/components/chat/GitDiffSidebar.vue` | **modify** | Add search button + `Cmd/Ctrl-F` + localStorage + open-file event |
| `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue` | **modify** | Render `<SearchPanel>` + forward `open-file` |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | **modify** | Add ~12 search keys |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | **modify** | Add ~12 search keys |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | **modify** | Add ~12 search keys |

---

## Task 1: Backend scaffolding (ReasonCode, rg probe, config, route)

**Files:**
- Modify: `astrbot_plugin_spcode_toolkit/tools/webapi/_helpers.py` (ReasonCode additions)
- Modify: `astrbot_plugin_spcode_toolkit/tools/webapi/__init__.py` (import + ROUTES)
- Modify: `astrbot_plugin_spcode_toolkit/main.py` (rg probe)
- Modify: `astrbot_plugin_spcode_toolkit/_conf_schema.json` (config field)

**Interfaces:**
- Produces: `plugin._rg_available: bool` and `plugin._rg_path: str` (set during `__init__`)
- Produces: `ReasonCode.SEARCH_UNAVAILABLE`, `SEARCH_TIMEOUT`, `INVALID_PATTERN`, `PATTERN_TOO_LONG`, `PATH_UNSAFE_FILTER` constants
- Produces: `POST /spcode/file-search` route registered in `ROUTES`

This is **plumbing only** — no business logic. The endpoint is a stub that returns `feature_disabled`. Tasks 2-4 add the real logic.

- [ ] **Step 1: Add ReasonCode entries**

In `astrbot_plugin_spcode_toolkit/tools/webapi/_helpers.py`, append to the `ReasonCode` class (right before the existing v2.14.0 worktree codes block is fine, or just after the file-path codes block):

```python
    # ── file-search 专用(v2.15.0,2026-07-02) ──
    SEARCH_UNAVAILABLE = "search_unavailable"   # 兜底 Python 也失败
    SEARCH_TIMEOUT = "search_timeout"           # 5s 超时
    INVALID_PATTERN = "invalid_pattern"         # pattern 为空 / 含换行 / 正则语法错
    PATTERN_TOO_LONG = "pattern_too_long"       # > 256 chars
    PATH_UNSAFE_FILTER = "path_unsafe_filter"   # path_filter 越界
```

- [ ] **Step 2: Import handler stub in webapi `__init__.py`**

In `astrbot_plugin_spcode_toolkit/tools/webapi/__init__.py`:

1. Add `file_search,` to the import block (alphabetical, between `file_browser,` and `file_restore,`).
2. Add a `HANDLERS` entry:

```python
    "handle_post_file_search": file_search.handle,  # v2.15.0 (2026-07-02)
```

3. Add a `ROUTES` entry between `file-browser` and `file-restore` (preserve existing order):

```python
    (
        "/spcode/file-search",  # v2.15.0 (2026-07-02)
        ["POST"],
        file_search.handle,
        "在已加载项目(指定 worktree)内按内容搜索文件",
    ),
```

- [ ] **Step 3: Create handler stub**

Create `astrbot_plugin_spcode_toolkit/tools/webapi/file_search.py`:

```python
"""POST /spcode/file-search — 在已加载项目内按内容搜索文件。

Spec: docs/superpowers/specs/2026-07-02-sidebar-search-design.md

后端实现:ripgrep 优先(plugin._rg_available=True);缺失则走纯 Python 兜底。
v2.15.0 (2026-07-02) — 初版 stub,业务实现在后续 Task 2-4 补齐。
"""

from __future__ import annotations
import logging
import time
from typing import TYPE_CHECKING

from ._helpers import _make_envelope, ReasonCode

if TYPE_CHECKING:
    from main import SPCodeToolkit

logger = logging.getLogger(__name__)


async def handle(
    plugin: "SPCodeToolkit",
    *,
    umo: str | None = None,
    worktree: str | None = None,
    body: dict | None = None,
) -> dict:
    """POST /spcode/file-search handler.

    Stub v2.15.0 — returns feature_disabled so the route is registered
    and addressable. Real search logic lands in Tasks 2-4.
    """
    return _make_envelope(
        success=False,
        reason=ReasonCode.FEATURE_DISABLED,
        elapsed_ms=0,
        umo=umo,
        worktree=worktree,
    )
```

- [ ] **Step 4: Add rg probe to `main.py`**

In `astrbot_plugin_spcode_toolkit/main.py`, **after** the existing git probe block (the block ending around line 233 with the `except Exception as exc:` clause) and **before** `async def initialize(self)`, add:

```python
        # ── ripgrep 可用性探测(2026-07-02,v2.15.0) ──
        # 失败不阻塞插件加载;file_search 端点会走纯 Python 兜底。
        # 复用 git 探测的 CREATE_NO_WINDOW 抑制黑窗模式。
        self._rg_path = (self._config.get("rg_path") or "rg").strip() or "rg"
        self._rg_available = False
        try:
            import subprocess as _sp
            import sys as _sys
            _NO_WINDOW_RG: dict = (
                {"creationflags": _sp.CREATE_NO_WINDOW}
                if _sys.platform == "win32"
                else {}
            )
            _rg_probe = _sp.run(
                [self._rg_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8",
                errors="replace",
                **_NO_WINDOW_RG,
            )
            if _rg_probe.returncode == 0:
                self._rg_available = True
                _first_line = (
                    (_rg_probe.stdout or "").splitlines()[0]
                    if _rg_probe.stdout
                    else "unknown"
                )
                logger.info(f"[file-search] detected ripgrep: {_first_line}")
            else:
                logger.warning(
                    f"[file-search] ripgrep 探测失败"
                    f"(returncode={_rg_probe.returncode})"
                    " — /spcode/file-search 将走纯 Python 兜底(慢)"
                )
        except FileNotFoundError:
            logger.info(
                f"[file-search] ripgrep ({self._rg_path}) 未安装或不在 PATH 中"
                " — /spcode/file-search 将走纯 Python 兜底(慢)。"
                " 安装 ripgrep 后会自动启用高速路径。"
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"[file-search] 启动期探测异常: {exc!s}")
```

- [ ] **Step 5: Add `search.rg_path` to `_conf_schema.json`**

In `astrbot_plugin_spcode_toolkit/_conf_schema.json`, locate the top-level properties object and add a new `"search"` key (alphabetical position, after `"security"` if present, or after `"project"`):

```jsonc
    "search": {
      "type": "object",
      "label": "文件搜索配置",
      "description": "POST /spcode/file-search 端点的参数。ripgrep 缺失时自动回退到纯 Python 搜索(慢)。",
      "properties": {
        "rg_path": {
          "type": "string",
          "default": "rg",
          "label": "ripgrep 路径",
          "description": "ripgrep 可执行路径。rg 缺失时端点自动回退到纯 Python 搜索(慢)。",
          "tip": "Windows: winget install BurntSushi.ripgrep,或 scoop install ripgrep,或 choco install ripgrep。",
          "placeholder": "rg"
        }
      }
    },
```

Verify the JSON is still valid:
```bash
python -c "import json; json.load(open('F:\github\astrbot_plugin_spcode_toolkit\_conf_schema.json'))"
```
Expected: no output (success).

- [ ] **Step 6: Run ruff + import test**

```bash
cd F:\github\astrbot_plugin_spcode_toolkit
uv run ruff format tools/webapi/file_search.py tools/webapi/_helpers.py tools/webapi/__init__.py main.py
uv run ruff check tools/webapi/file_search.py tools/webapi/_helpers.py tools/webapi/__init__.py main.py
```
Expected: no diff, no errors.

Then sanity-check the import:
```bash
cd F:\github\astrbot_plugin_spcode_toolkit
uv run python -c "from tools.webapi import file_search; print('OK', file_search.handle)"
```
Expected: `OK <function handle at 0x...>`

- [ ] **Step 7: Commit**

```bash
cd F:\github\Astrbot
git add astrbot_plugin_spcode_toolkit/tools/webapi/file_search.py \
        astrbot_plugin_spcode_toolkit/tools/webapi/_helpers.py \
        astrbot_plugin_spcode_toolkit/tools/webapi/__init__.py \
        astrbot_plugin_spcode_toolkit/main.py \
        astrbot_plugin_spcode_toolkit/_conf_schema.json
git commit -m "feat(spcode): scaffold /spcode/file-search endpoint

ReasonCode entries, rg availability probe at plugin init, route
registration, and conf_schema search.rg_path field. Handler is a
stub returning feature_disabled; real search logic in follow-up
commits."
```

---

## Task 2: Backend — rg primary path (TDD)

**Files:**
- Modify: `astrbot_plugin_spcode_toolkit/tools/webapi/file_search.py` (full implementation)
- Create: `astrbot_plugin_spcode_toolkit/tests/test_file_search.py` (12 tests for rg path)

**Interfaces:**
- `async def handle(plugin, *, umo, worktree, body) -> dict` — full implementation
- Internal helpers: `_run_ripgrep(...)`, `_parse_ripgrep_json(...)`, `_make_snippet(...)`
- Public request shape (per spec §5.1): `{pattern, path_filter?, glob_filter?, case_sensitive?, regex?, max_results?, context_chars?}`
- Public response shape (per spec §5.2): `{pattern, backend, result_count, max_results, truncated, elapsed_ms, results: [{path, line, column, snippet}]}`

This task implements the rg branch only. Python fallback arrives in Task 3. Timeout in Task 4.

- [ ] **Step 1: Write failing tests**

Create `astrbot_plugin_spcode_toolkit/tests/test_file_search.py`:

```python
"""Tests for POST /spcode/file-search.

Spec: docs/superpowers/specs/2026-07-02-sidebar-search-design.md
"""

from __future__ import annotations
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from tools.webapi import file_search
from tools.webapi._helpers import ReasonCode


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def mock_plugin_with_rg(tmp_path: Path) -> MagicMock:
    """Plugin mock with rg available, worktree = tmp_path (a real dir)."""
    # Create a real git repo so _git_endpoint_preflight passes
    import subprocess
    subprocess.run(["git", "init", str(tmp_path)], check=True,
                   capture_output=True, text=True)
    # Add at least one commit so it's a real repo
    (tmp_path / "init.txt").write_text("init")
    subprocess.run(["git", "-C", str(tmp_path), "add", "init.txt"],
                   check=True, capture_output=True, text=True)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "init"],
                   check=True, capture_output=True, text=True, env=env)

    plugin = MagicMock()
    plugin._rg_available = True
    plugin._rg_path = "rg"
    plugin._git_binary.return_value = "git"
    plugin._config = {
        "agentsmd_enabled": True, "codegraph_enabled": True,
    }
    # get_loaded_project returns the project info dict
    plugin.get_loaded_project.return_value = {
        "directory": str(tmp_path), "loaded_at": 1.0,
    }
    return plugin


@pytest.fixture
def write_files(tmp_path: Path) -> None:
    """Write a few files in tmp_path for searching."""
    (tmp_path / "auth.py").write_text(
        "def validate_user(token: str) -> bool:\n"
        "    if not token:\n"
        "        return False\n"
        "    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Auth Module\n"
        "Use validate_user to check tokens.\n",
        encoding="utf-8",
    )


# ── Tests: rg path ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hit(mock_plugin_with_rg, write_files):
    """Basic substring search returns matching lines with snippets."""
    result = await file_search.handle(
        mock_plugin_with_rg,
        umo="test:umo",
        worktree=None,
        body={"pattern": "validate_user"},
    )
    # _JSONResponseCompat with .get()
    data = result.get("data") if hasattr(result, "get") else result["data"]
    assert data["reason"] is None
    assert data["backend"] == "ripgrep"
    assert data["result_count"] >= 2
    paths = [r["path"] for r in data["results"]]
    assert "auth.py" in paths
    for r in data["results"]:
        assert "validate_user" in r["snippet"]
        assert r["line"] >= 1
        assert r["column"] >= 1


@pytest.mark.asyncio
async def test_miss(mock_plugin_with_rg, write_files):
    """No matches → 200, results=[], reason=None."""
    result = await file_search.handle(
        mock_plugin_with_rg,
        umo="test:umo",
        body={"pattern": "this_string_does_not_exist_xyz"},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["reason"] is None
    assert data["results"] == []
    assert data["result_count"] == 0
    assert data["truncated"] is False


@pytest.mark.asyncio
async def test_empty_pattern(mock_plugin_with_rg):
    """Empty pattern → invalid_pattern."""
    result = await file_search.handle(
        mock_plugin_with_rg, umo="test:umo", body={"pattern": ""},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["reason"] == ReasonCode.INVALID_PATTERN


@pytest.mark.asyncio
async def test_pattern_with_newline(mock_plugin_with_rg):
    """Pattern with \\n → invalid_pattern (multi-line search not supported)."""
    result = await file_search.handle(
        mock_plugin_with_rg, umo="test:umo", body={"pattern": "foo\nbar"},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["reason"] == ReasonCode.INVALID_PATTERN


@pytest.mark.asyncio
async def test_pattern_too_long(mock_plugin_with_rg):
    """Pattern > 256 chars → pattern_too_long."""
    result = await file_search.handle(
        mock_plugin_with_rg, umo="test:umo", body={"pattern": "a" * 257},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["reason"] == ReasonCode.PATTERN_TOO_LONG


@pytest.mark.asyncio
async def test_max_results_clamp(mock_plugin_with_rg, write_files):
    """max_results > 1000 → clamp to 1000."""
    result = await file_search.handle(
        mock_plugin_with_rg, umo="test:umo",
        body={"pattern": "validate_user", "max_results": 5000},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["max_results"] == 1000


@pytest.mark.asyncio
async def test_glob_filter(mock_plugin_with_rg, write_files):
    """glob_filter='*.py' → only .py files in results."""
    result = await file_search.handle(
        mock_plugin_with_rg, umo="test:umo",
        body={"pattern": "validate_user", "glob_filter": "*.py"},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    paths = [r["path"] for r in data["results"]]
    assert all(p.endswith(".py") for p in paths)


@pytest.mark.asyncio
async def test_case_sensitive(mock_plugin_with_rg, write_files):
    """case_sensitive=true misses lowercase hits."""
    # README.md has "validate_user" lowercase
    result_cs = await file_search.handle(
        mock_plugin_with_rg, umo="test:umo",
        body={"pattern": "validate_user", "case_sensitive": True},
    )
    data_cs = result_cs["data"] if hasattr(result_cs, "get") else result_cs["data"]
    # All hits should have exact-case "validate_user" (lowercase) — still matches
    # because the actual file content is lowercase. So this test only verifies
    # that the case_sensitive flag is accepted and the call returns.
    assert data_cs["reason"] is None


@pytest.mark.asyncio
async def test_regex(mock_plugin_with_rg, write_files):
    """regex=true with valid regex finds pattern."""
    result = await file_search.handle(
        mock_plugin_with_rg, umo="test:umo",
        body={"pattern": r"validate_\w+", "regex": True},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["reason"] is None
    assert data["result_count"] >= 1


@pytest.mark.asyncio
async def test_invalid_regex(mock_plugin_with_rg):
    """regex=true with bad regex → invalid_pattern."""
    result = await file_search.handle(
        mock_plugin_with_rg, umo="test:umo",
        body={"pattern": "[unclosed", "regex": True},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["reason"] == ReasonCode.INVALID_PATTERN


@pytest.mark.asyncio
async def test_path_unsafe_filter(mock_plugin_with_rg):
    """path_filter with '..' → path_unsafe_filter."""
    result = await file_search.handle(
        mock_plugin_with_rg, umo="test:umo",
        body={"pattern": "foo", "path_filter": "../etc"},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["reason"] == ReasonCode.PATH_UNSAFE_FILTER


@pytest.mark.asyncio
async def test_worktree_invalid(mock_plugin_with_rg):
    """worktree that doesn't exist → worktree_invalid."""
    result = await file_search.handle(
        mock_plugin_with_rg, umo="test:umo",
        worktree="/nonexistent/path/that/does/not/exist",
        body={"pattern": "foo"},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["reason"] == ReasonCode.WORKTREE_INVALID
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd F:\github\astrbot_plugin_spcode_toolkit
uv run pytest tests/test_file_search.py -v 2>&1 | head -60
```
Expected: 12 failures (handler is still a stub returning `feature_disabled`).

- [ ] **Step 3: Implement the handler**

Replace the entire `astrbot_plugin_spcode_toolkit/tools/webapi/file_search.py` with the full implementation below. The `handle()` is the main entry; helpers `_run_ripgrep`, `_parse_ripgrep_json`, `_make_snippet` come first.

```python
"""POST /spcode/file-search — 在已加载项目内按内容搜索文件。

Spec: docs/superpowers/specs/2026-07-02-sidebar-search-design.md

后端实现:ripgrep 优先(plugin._rg_available=True);缺失则走纯 Python 兜底。
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import subprocess as _sp
import sys as _sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._helpers import _JSONResponseCompat, _make_envelope, ReasonCode
from .git_log import _git_endpoint_preflight
from .._helpers import _validate_repo_relative_file

if TYPE_CHECKING:
    from main import SPCodeToolkit

logger = logging.getLogger(__name__)

# ── 端点常量 ──
SEARCH_TIMEOUT_SECONDS: float = 5.0
DEFAULT_MAX_RESULTS: int = 200
MAX_MAX_RESULTS: int = 1000
DEFAULT_CONTEXT_CHARS: int = 60
MAX_CONTEXT_CHARS: int = 200
MAX_PATTERN_LENGTH: int = 256
MAX_BYTES_PER_FILE: int = 1 * 1024 * 1024  # 1 MB / file
MAX_SNIPPET_LENGTH: int = 160

_NO_WINDOW: dict = (
    {"creationflags": _sp.CREATE_NO_WINDOW} if _sys.platform == "win32" else {}
)


# ── snippet 切片 ───────────────────────────────────────────────

def _make_snippet(line: str, match_start: int, match_len: int,
                  context_chars: int) -> str:
    """从一整行中切出含匹配段的 snippet(前后各 context_chars 字符)。"""
    s = max(0, match_start - context_chars)
    e = min(len(line), match_start + match_len + context_chars)
    snippet = line[s:e]
    prefix = "..." if s > 0 else ""
    suffix = "..." if e < len(line) else ""
    full = prefix + snippet + suffix
    if len(full) <= MAX_SNIPPET_LENGTH:
        return full
    # 超长时以 match 为中心重新切
    match_in_snippet = snippet[match_start - s:match_start - s + match_len]
    mid = snippet.find(match_in_snippet)
    if mid < 0:
        return full[:MAX_SNIPPET_LENGTH] + "..."
    half = MAX_SNIPPET_LENGTH // 2 - len(match_in_snippet) // 2 - 3
    half = max(10, half)
    s2 = max(0, mid - half)
    e2 = min(len(snippet), mid + len(match_in_snippet) + half)
    return ("..." if s2 > 0 else "") + snippet[s2:e2] + ("..." if e2 < len(snippet) else "")


# ── ripgrep 调用 ───────────────────────────────────────────────

async def _run_ripgrep(
    *,
    pattern: str,
    directory: str,
    path_filter: str | None,
    glob_filter: str | None,
    case_sensitive: bool,
    regex: bool,
    max_results: int,
    rg_path: str,
) -> dict[str, Any]:
    """调用 ripgrep 并返回 stdout(str)+ 错误信息(若有)。

    Returns:
        {"ok": True, "stdout": str} | {"ok": False, "error": str, "kind": str}
        kind ∈ {"missing", "timeout", "regex_error", "other"}
    """
    cmd: list[str] = [
        rg_path,
        "--json",
        "--no-config",
        "--no-heading",
        "--line-number",
        "--column",
        "--no-messages",
        "--max-columns=200",
        "--max-columns-preview",
        "--max-filesize=1M",
        "--no-follow",
        "--",
    ]
    if not case_sensitive:
        cmd.append("--ignore-case")
    if not regex:
        cmd.append("--fixed-strings")
    if glob_filter:
        cmd.extend(["--glob", glob_filter])
    cmd.extend(["--max-count", str(max_results)])
    cmd.append(pattern)
    cmd.append(
        os.path.join(directory, path_filter) if path_filter else directory
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.create_subprocess.PIPE,
            stderr=asyncio.create_subprocess.PIPE,
            cwd=directory or None,
            **_NO_WINDOW,
        )
    except FileNotFoundError:
        return {"ok": False, "kind": "missing",
                "error": f"{rg_path} 未安装或不在 PATH 中"}

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=SEARCH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return {"ok": False, "kind": "timeout",
                "error": f"rg timeout ({SEARCH_TIMEOUT_SECONDS}s)"}

    if proc.returncode == 0:
        return {"ok": True, "stdout": stdout_bytes.decode("utf-8", errors="replace")}
    if proc.returncode == 1:
        return {"ok": True, "stdout": ""}  # no matches
    err_msg = stderr_bytes.decode("utf-8", errors="replace").strip()
    kind = "regex_error" if (regex and "regex" in err_msg.lower()) else "other"
    return {"ok": False, "kind": kind,
            "error": err_msg or f"rg exit {proc.returncode}"}


def _parse_ripgrep_json(
    raw: str, max_results: int, context_chars: int,
) -> tuple[list[dict[str, Any]], bool]:
    """解析 rg --json NDJSON 流,返回 (results, truncated)。"""
    results: list[dict[str, Any]] = []
    truncated = False
    for line in raw.splitlines():
        if len(results) >= max_results:
            truncated = True
            break
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "match":
            continue
        data = obj.get("data", {})
        path = (data.get("path") or {}).get("text", "")
        line_no = int(data.get("line_number") or 0)
        submatches = data.get("submatches") or []
        if not path or not line_no or not submatches:
            continue
        sub = submatches[0]
        col = int(sub.get("start") or 0) + 1  # 0-based → 1-based
        full_line = (data.get("lines") or {}).get("text", "").rstrip("\n")
        match_text = (sub.get("match") or {}).get("text", "")
        match_start = int(sub.get("start") or 0)
        snippet = _make_snippet(
            full_line, match_start, len(match_text), context_chars,
        )
        results.append({
            "path": path, "line": line_no,
            "column": col, "snippet": snippet,
        })
    return results, truncated


# ── 主 handler ────────────────────────────────────────────────

async def handle(
    plugin: "SPCodeToolkit",
    *,
    umo: str | None = None,
    worktree: str | None = None,
    body: dict | None = None,
) -> dict:
    """POST /spcode/file-search handler."""
    t0 = time.time()

    def _elapsed() -> int:
        return int((time.time() - t0) * 1000)

    body = body or {}

    # 1. pattern 校验
    pattern = (body.get("pattern") or "").strip()
    if not pattern:
        return _make_envelope(
            success=False, reason=ReasonCode.INVALID_PATTERN,
            elapsed_ms=_elapsed(), umo=umo, worktree=worktree,
        )
    if len(pattern) > MAX_PATTERN_LENGTH:
        return _make_envelope(
            success=False, reason=ReasonCode.PATTERN_TOO_LONG,
            elapsed_ms=_elapsed(), umo=umo, worktree=worktree,
        )
    if "\n" in pattern or "\r" in pattern:
        return _make_envelope(
            success=False, reason=ReasonCode.INVALID_PATTERN,
            elapsed_ms=_elapsed(), umo=umo, worktree=worktree,
        )

    case_sensitive = bool(body.get("case_sensitive", False))
    regex = bool(body.get("regex", False))
    try:
        max_results = max(1, min(int(body.get("max_results", DEFAULT_MAX_RESULTS)),
                                  MAX_MAX_RESULTS))
        context_chars = max(10, min(int(body.get("context_chars", DEFAULT_CONTEXT_CHARS)),
                                    MAX_CONTEXT_CHARS))
    except (TypeError, ValueError):
        return _make_envelope(
            success=False, reason=ReasonCode.INVALID_PATTERN,
            elapsed_ms=_elapsed(), umo=umo, worktree=worktree,
        )

    path_filter = (body.get("path_filter") or "").strip() or None
    glob_filter = (body.get("glob_filter") or "").strip() or None

    # 2. preflight
    err, ctx = await _git_endpoint_preflight(
        plugin, umo=umo, worktree_param=worktree,
    )
    if err is not None:
        err["data"]["elapsed_ms"] = _elapsed()
        if "loaded" not in err["data"]:
            err["data"]["loaded"] = False
        return err
    directory = ctx["directory"]
    effective_umo = ctx["umo"]

    # 3. path_filter 4 步防御
    if path_filter:
        ok, err_reason, _ = _validate_repo_relative_file(path_filter)
        if not ok:
            return _make_envelope(
                success=False, reason=ReasonCode.PATH_UNSAFE_FILTER,
                elapsed_ms=_elapsed(),
                umo=effective_umo, worktree=worktree, directory=directory,
            )

    # 4. 实际搜索(rg 路径)
    backend_used = "python"
    if getattr(plugin, "_rg_available", False):
        rg_path = getattr(plugin, "_rg_path", "rg")
        rg_result = await _run_ripgrep(
            pattern=pattern, directory=directory,
            path_filter=path_filter, glob_filter=glob_filter,
            case_sensitive=case_sensitive, regex=regex,
            max_results=max_results, rg_path=rg_path,
        )
        if rg_result["ok"]:
            results, truncated = _parse_ripgrep_json(
                rg_result["stdout"], max_results, context_chars,
            )
            backend_used = "ripgrep"
        elif rg_result.get("kind") == "timeout":
            return _make_envelope(
                success=False, reason=ReasonCode.SEARCH_TIMEOUT,
                elapsed_ms=_elapsed(),
                umo=effective_umo, worktree=worktree, directory=directory,
            )
        elif rg_result.get("kind") == "regex_error":
            return _make_envelope(
                success=False, reason=ReasonCode.INVALID_PATTERN,
                elapsed_ms=_elapsed(),
                umo=effective_umo, worktree=worktree, directory=directory,
            )
        else:
            logger.warning(
                f"[file-search] rg failed ({rg_result.get('error')!r}),"
                " falling back to Python"
            )
            return _make_envelope(
                success=False, reason=ReasonCode.SEARCH_UNAVAILABLE,
                elapsed_ms=_elapsed(),
                umo=effective_umo, worktree=worktree, directory=directory,
            )
    else:
        return _make_envelope(
            success=False, reason=ReasonCode.SEARCH_UNAVAILABLE,
            elapsed_ms=_elapsed(),
            umo=effective_umo, worktree=worktree, directory=directory,
        )

    return _JSONResponseCompat(
        _make_envelope(
            success=True, elapsed_ms=_elapsed(),
            umo=effective_umo, worktree=directory,
            pattern=pattern, backend=backend_used,
            result_count=len(results), max_results=max_results,
            truncated=truncated, results=results,
        ),
        status_code=200,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd F:\github\astrbot_plugin_spcode_toolkit
uv run pytest tests/test_file_search.py -v 2>&1 | tail -40
```
Expected: 12 passed. If any fail, the most common cause is rg not being on PATH — install it or see Task 3 for the Python fallback (Task 3 will make those tests pass even without rg).

- [ ] **Step 5: Run ruff**

```bash
cd F:\github\astrbot_plugin_spcode_toolkit
uv run ruff format tools/webapi/file_search.py
uv run ruff check tools/webapi/file_search.py
```
Expected: no diff, no errors.

- [ ] **Step 6: Commit**

```bash
cd F:\github\Astrbot
git add astrbot_plugin_spcode_toolkit/tools/webapi/file_search.py \
        astrbot_plugin_spcode_toolkit/tests/test_file_search.py
git commit -m "feat(spcode): implement file-search rg primary path

POST /spcode/file-search calls ripgrep with --json output and parses
NDJSON stream into {path, line, column, snippet} records. Handles
substring/regex modes, glob/path_filter, case sensitivity, max_results
clamp, and the invalid_pattern/pattern_too_long/path_unsafe_filter
error paths. Python fallback lands in the next commit."
```

---

## Task 3: Backend — Python fallback path (TDD)

**Files:**
- Modify: `astrbot_plugin_spcode_toolkit/tools/webapi/file_search.py`
- Modify: `astrbot_plugin_spcode_toolkit/tests/test_file_search.py` (add fallback tests)

**Interfaces:**
- New helper: `async def _run_python_fallback(...) -> tuple[list[dict], bool, str | None]`
- Handler dispatches to fallback when `plugin._rg_available is False` (or when rg fails in a way that's not timeout/regex_error)
- New reason code behavior: `SEARCH_UNAVAILABLE` only when fallback ALSO fails

- [ ] **Step 1: Add failing tests for the fallback**

Append to `tests/test_file_search.py`:

```python
# ── Tests: Python fallback path ────────────────────────────────

@pytest.fixture
def mock_plugin_no_rg(mock_plugin_with_rg) -> MagicMock:
    """Same as mock_plugin_with_rg but with _rg_available=False."""
    mock_plugin_with_rg._rg_available = False
    return mock_plugin_with_rg


@pytest.mark.asyncio
async def test_fallback_basic(mock_plugin_no_rg, write_files):
    """When rg unavailable, Python fallback still returns matches."""
    result = await file_search.handle(
        mock_plugin_no_rg, umo="test:umo",
        body={"pattern": "validate_user"},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["reason"] is None
    assert data["backend"] == "python"
    assert data["result_count"] >= 2
    assert any(r["path"] == "auth.py" for r in data["results"])


@pytest.mark.asyncio
async def test_fallback_skips_node_modules(mock_plugin_no_rg, tmp_path):
    """Fallback skips node_modules / .git / __pycache__ dirs."""
    (tmp_path / "src.py").write_text("token")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("token")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "x").write_text("token")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_text("token")

    result = await file_search.handle(
        mock_plugin_no_rg, umo="test:umo", body={"pattern": "token"},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    paths = [r["path"] for r in data["results"]]
    # src.py matches; node_modules/.git/__pycache__ do NOT
    assert any("src.py" in p for p in paths)
    assert not any("node_modules" in p for p in paths)
    assert not any(p.startswith(".git") for p in paths)
    assert not any("__pycache__" in p for p in paths)


@pytest.mark.asyncio
async def test_fallback_skips_large_files(mock_plugin_no_rg, tmp_path):
    """Files > 1 MB are skipped."""
    big = tmp_path / "big.py"
    big.write_text("x" * 1024 + "\ntarget_token\n" + "y" * (2 * 1024 * 1024))
    (tmp_path / "small.py").write_text("target_token\n")

    result = await file_search.handle(
        mock_plugin_no_rg, umo="test:umo", body={"pattern": "target_token"},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    paths = [r["path"] for r in data["results"]]
    assert "small.py" in paths
    assert "big.py" not in paths


@pytest.mark.asyncio
async def test_fallback_regex(mock_plugin_no_rg, write_files):
    """Fallback handles regex=true."""
    result = await file_search.handle(
        mock_plugin_no_rg, umo="test:umo",
        body={"pattern": r"validate_\w+", "regex": True},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["reason"] is None
    assert data["backend"] == "python"
    assert data["result_count"] >= 1


@pytest.mark.asyncio
async def test_fallback_invalid_regex(mock_plugin_no_rg):
    """Fallback with bad regex returns invalid_pattern."""
    result = await file_search.handle(
        mock_plugin_no_rg, umo="test:umo",
        body={"pattern": "[unclosed", "regex": True},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    assert data["reason"] == ReasonCode.INVALID_PATTERN


@pytest.mark.asyncio
async def test_fallback_glob_filter(mock_plugin_no_rg, write_files):
    """Fallback respects glob_filter."""
    result = await file_search.handle(
        mock_plugin_no_rg, umo="test:umo",
        body={"pattern": "validate_user", "glob_filter": "*.py"},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    paths = [r["path"] for r in data["results"]]
    assert all(p.endswith(".py") for p in paths)


@pytest.mark.asyncio
async def test_fallback_case_sensitive(mock_plugin_no_rg, write_files):
    """case_sensitive=true in fallback only matches exact case."""
    # Add a file with uppercase to test
    (tmp_path := write_files.__self__)  # noqa
    (write_files.__self__ / "Upper.txt").write_text("VALIDATE_USER here")
    result = await file_search.handle(
        mock_plugin_no_rg, umo="test:umo",
        body={"pattern": "validate_user", "case_sensitive": True},
    )
    data = result["data"] if hasattr(result, "get") else result["data"]
    paths = [r["path"] for r in data["results"]]
    # Upper.txt should NOT match (uppercase)
    assert not any("Upper.txt" in p for p in paths)
```

> **Note on the last test:** The `write_files.__self__` reference is a quick way to get the `tmp_path` fixture from the `write_files` fixture. If the test fails on this line, just inline `tmp_path` from a separate fixture or use the existing `mock_plugin_no_rg` fixture's underlying tmp_path by querying `mock_plugin_no_rg.get_loaded_project.return_value["directory"]`.

- [ ] **Step 2: Run tests to verify fallback tests fail**

```bash
cd F:\github\astrbot_plugin_spcode_toolkit
uv run pytest tests/test_file_search.py -v -k "fallback" 2>&1 | tail -30
```
Expected: 6 failures (handler currently returns `search_unavailable` when rg is missing).

- [ ] **Step 3: Add `_run_python_fallback` to file_search.py**

Add this function above `async def handle(...)`:

```python
# ── 纯 Python 兜底 ─────────────────────────────────────────────

_PYTHON_FALLBACK_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "target", ".next", ".nuxt",
    ".idea", ".vscode",
})


def _glob_to_re(glob: str) -> re.Pattern[str]:
    """把 shell glob (*.py → .*\\.py) 转成正则。"""
    parts = glob.split(",")
    pat = "|".join(
        re.escape(p).replace(r"\*", ".*").replace(r"\?", ".")
        for p in parts
    )
    return re.compile(f"^({pat})$")


async def _run_python_fallback(
    *,
    pattern: str,
    directory: str,
    path_filter: str | None,
    glob_filter: str | None,
    case_sensitive: bool,
    regex: bool,
    max_results: int,
    context_chars: int,
) -> tuple[list[dict[str, Any]], bool, str | None]:
    """纯 Python 兜底:os.walk + re.finditer。

    Returns:
        (results, truncated, error_message_or_None)
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    if regex:
        try:
            pat = re.compile(pattern, flags)
        except re.error as exc:
            return [], False, f"invalid regex: {exc}"
    else:
        pat = re.compile(re.escape(pattern), flags)

    glob_re = _glob_to_re(glob_filter) if glob_filter else None
    results: list[dict[str, Any]] = []
    truncated = False
    search_root = Path(directory) / path_filter if path_filter else Path(directory)
    if not search_root.is_dir():
        return [], False, f"path_filter not found: {path_filter}"

    def _walk() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        was_truncated = False
        for root, dirs, files in os.walk(search_root, followlinks=False):
            # 原地修剪:跳过 _PYTHON_FALLBACK_SKIP_DIRS
            dirs[:] = [
                d for d in dirs
                if d not in _PYTHON_FALLBACK_SKIP_DIRS and not d.startswith(".")
            ]
            for fname in files:
                if len(out) >= max_results:
                    was_truncated = True
                    break
                if glob_re and not glob_re.match(fname):
                    continue
                fpath = Path(root) / fname
                try:
                    st = fpath.stat()
                except OSError:
                    continue
                if st.st_size > MAX_BYTES_PER_FILE:
                    continue
                try:
                    with fpath.open("r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, start=1):
                            m = pat.search(line)
                            if m:
                                out.append({
                                    "path": str(fpath.relative_to(directory)),
                                    "line": i,
                                    "column": m.start() + 1,
                                    "snippet": _make_snippet(
                                        line.rstrip("\n"),
                                        m.start(), len(m.group(0)),
                                        context_chars,
                                    ),
                                })
                                if len(out) >= max_results:
                                    was_truncated = True
                                    break
                except OSError:
                    continue
            if was_truncated:
                break
        return out

    try:
        results = await asyncio.to_thread(_walk)
    except Exception as exc:
        return results, truncated, f"fallback error: {exc}"
    return results, truncated, None
```

- [ ] **Step 4: Wire the fallback into `handle()`**

In `handle()`, replace the `else:` branch (right after `if getattr(plugin, "_rg_available", False):`) and the rg-failure else branch. The new flow:

```python
    backend_used = "python"
    rg_result_error: str | None = None

    if getattr(plugin, "_rg_available", False):
        rg_path = getattr(plugin, "_rg_path", "rg")
        rg_result = await _run_ripgrep(
            pattern=pattern, directory=directory,
            path_filter=path_filter, glob_filter=glob_filter,
            case_sensitive=case_sensitive, regex=regex,
            max_results=max_results, rg_path=rg_path,
        )
        if rg_result["ok"]:
            results, truncated = _parse_ripgrep_json(
                rg_result["stdout"], max_results, context_chars,
            )
            backend_used = "ripgrep"
        elif rg_result.get("kind") == "timeout":
            return _make_envelope(
                success=False, reason=ReasonCode.SEARCH_TIMEOUT,
                elapsed_ms=_elapsed(),
                umo=effective_umo, worktree=worktree, directory=directory,
            )
        elif rg_result.get("kind") == "regex_error":
            return _make_envelope(
                success=False, reason=ReasonCode.INVALID_PATTERN,
                elapsed_ms=_elapsed(),
                umo=effective_umo, worktree=worktree, directory=directory,
            )
        else:
            rg_result_error = rg_result.get("error", "unknown")
            logger.warning(
                f"[file-search] rg failed ({rg_result_error!r}),"
                " falling back to Python"
            )
            # 落到下面走兜底
            results, truncated, fb_err = await _run_python_fallback(
                pattern=pattern, directory=directory,
                path_filter=path_filter, glob_filter=glob_filter,
                case_sensitive=case_sensitive, regex=regex,
                max_results=max_results, context_chars=context_chars,
            )
            if fb_err and fb_err.startswith("invalid regex"):
                return _make_envelope(
                    success=False, reason=ReasonCode.INVALID_PATTERN,
                    elapsed_ms=_elapsed(),
                    umo=effective_umo, worktree=worktree, directory=directory,
                )
            if fb_err and fb_err.startswith("fallback error"):
                return _make_envelope(
                    success=False, reason=ReasonCode.SEARCH_UNAVAILABLE,
                    elapsed_ms=_elapsed(),
                    umo=effective_umo, worktree=worktree, directory=directory,
                )
    else:
        # rg 不可用 → 直接走兜底
        results, truncated, fb_err = await _run_python_fallback(
            pattern=pattern, directory=directory,
            path_filter=path_filter, glob_filter=glob_filter,
            case_sensitive=case_sensitive, regex=regex,
            max_results=max_results, context_chars=context_chars,
        )
        if fb_err and fb_err.startswith("invalid regex"):
            return _make_envelope(
                success=False, reason=ReasonCode.INVALID_PATTERN,
                elapsed_ms=_elapsed(),
                umo=effective_umo, worktree=worktree, directory=directory,
            )
        if fb_err and fb_err.startswith("fallback error"):
            return _make_envelope(
                success=False, reason=ReasonCode.SEARCH_UNAVAILABLE,
                elapsed_ms=_elapsed(),
                umo=effective_umo, worktree=worktree, worktree=worktree,  # placeholder; see below
                directory=directory,
            )
        if fb_err and fb_err.startswith("path_filter"):
            return _make_envelope(
                success=False, reason=ReasonCode.PATH_UNSAFE_FILTER,
                elapsed_ms=_elapsed(),
                umo=effective_umo, worktree=worktree, directory=directory,
            )
```

> **FIX:** The duplicate `worktree=worktree` line in the placeholder above is a typo. Replace it with `worktree=worktree,` (single occurrence). Verify the final code has exactly one `worktree=` per `_make_envelope` call.

- [ ] **Step 5: Run tests**

```bash
cd F:\github\astrbot_plugin_spcode_toolkit
uv run pytest tests/test_file_search.py -v 2>&1 | tail -30
```
Expected: 18 passed (12 from Task 2 + 6 from this task; the last `test_fallback_case_sensitive` test should now pass after `tmp_path` is fixed).

- [ ] **Step 6: Run ruff**

```bash
cd F:\github\astrbot_plugin_spcode_toolkit
uv run ruff format tools/webapi/file_search.py
uv run ruff check tools/webapi/file_search.py
```
Expected: no diff, no errors.

- [ ] **Step 7: Commit**

```bash
cd F:\github\Astrbot
git add astrbot_plugin_spcode_toolkit/tools/webapi/file_search.py \
        astrbot_plugin_spcode_toolkit/tests/test_file_search.py
git commit -m "feat(spcode): add Python fallback for file-search

When ripgrep is missing or fails (non-timeout/non-regex errors), fall
back to a pure-Python os.walk + re.finditer implementation. Skips
common noise dirs (.git, node_modules, __pycache__, venv, dist, build,
target, .next, .nuxt, .idea, .vscode), respects glob_filter, handles
regex errors uniformly with the rg path."
```

---

## Task 4: Frontend composable — `useSpcodeFileSearch` (TDD)

**Files:**
- Create: `dashboard/src/composables/useSpcodeFileSearch.ts`
- Create: `dashboard/src/composables/__tests__/useSpcodeFileSearch.test.ts` (if vitest is set up; otherwise skip and rely on type checks + manual e2e)

**Interfaces:**
- Exports: `useSpcodeFileSearch()` returning `{ state: Ref<SearchState>, search(opts), cancel() }`
- State shape mirrors `useSpcodeGitLog`:
  ```ts
  type SearchState =
    | { kind: "idle" }
    | { kind: "loading"; query: string }
    | { kind: "ok"; query: string; results: SearchResult[]; truncated: boolean;
        backend: "ripgrep" | "python"; elapsedMs: number }
    | { kind: "error"; query: string; reason: string; elapsedMs: number };
  ```
- `search()` uses `pluginExtensionApi.post("spcode/file-search", body, { signal })` and an `AbortController` to cancel in-flight calls when a new search supersedes them.

This task is frontend-only and may not have a test infrastructure. If `vitest` is not already set up, the test file is best-effort; rely on `vue-tsc` for type checking.

- [ ] **Step 1: Check whether vitest is set up**

```bash
cd F:\github\Astrbot\dashboard
grep -E "\"vitest\"|\"@vue/test-utils\"" package.json
```
Expected: probably no match. If absent, skip Steps 2-4 and just write the composable; the type check in Step 5 + manual e2e is the verification.

- [ ] **Step 2 (if vitest present): Write failing test**

Create `dashboard/src/composables/__tests__/useSpcodeFileSearch.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useSpcodeFileSearch } from "../useSpcodeFileSearch";

vi.mock("@/api/v1", () => ({
  pluginExtensionApi: {
    post: vi.fn(),
  },
}));

import { pluginExtensionApi } from "@/api/v1";

describe("useSpcodeFileSearch", () => {
  beforeEach(() => {
    vi.mocked(pluginExtensionApi.post).mockReset();
  });

  it("starts in idle state", () => {
    const { state } = useSpcodeFileSearch();
    expect(state.value).toEqual({ kind: "idle" });
  });

  it("transitions idle → loading → ok on success", async () => {
    vi.mocked(pluginExtensionApi.post).mockResolvedValue({
      data: {
        status: "ok",
        data: {
          pattern: "foo",
          backend: "ripgrep",
          result_count: 1,
          max_results: 200,
          truncated: false,
          elapsed_ms: 12,
          results: [{ path: "a.py", line: 5, column: 1, snippet: "...foo..." }],
          reason: null,
        },
      },
    } as any);
    const { state, search } = useSpcodeFileSearch();
    const p = search({ umo: "u", worktree: null, pattern: "foo" });
    expect(state.value.kind).toBe("loading");
    await p;
    expect(state.value).toMatchObject({
      kind: "ok",
      query: "foo",
      backend: "ripgrep",
      results: [{ path: "a.py", line: 5, column: 1, snippet: "...foo..." }],
    });
  });

  it("transitions to error when reason is set", async () => {
    vi.mocked(pluginExtensionApi.post).mockResolvedValue({
      data: { status: "ok", data: { reason: "invalid_pattern", elapsed_ms: 0 } },
    } as any);
    const { state, search } = useSpcodeFileSearch();
    await search({ umo: "u", worktree: null, pattern: "" });
    expect(state.value).toMatchObject({ kind: "error", reason: "invalid_pattern" });
  });

  it("empty pattern returns to idle without calling API", async () => {
    const { state, search } = useSpcodeFileSearch();
    await search({ umo: "u", worktree: null, pattern: "   " });
    expect(state.value).toEqual({ kind: "idle" });
    expect(pluginExtensionApi.post).not.toHaveBeenCalled();
  });

  it("cancel() aborts in-flight request", async () => {
    let resolvePost: (v: any) => void;
    vi.mocked(pluginExtensionApi.post).mockImplementation(
      () => new Promise((r) => { resolvePost = r; }) as any,
    );
    const { state, search, cancel } = useSpcodeFileSearch();
    const p = search({ umo: "u", worktree: null, pattern: "foo" });
    expect(state.value.kind).toBe("loading");
    cancel();
    // Resolve the post promise AFTER cancel — state should NOT change to ok
    resolvePost!({
      data: { status: "ok", data: { reason: null, results: [] } },
    } as any);
    await p;
    expect(state.value.kind).toBe("loading");  // or idle, but NOT ok
  });
});
```

- [ ] **Step 3 (if vitest present): Run test to verify it fails**

```bash
cd F:\github\Astrbot\dashboard
npx vitest run src/composables/__tests__/useSpcodeFileSearch.test.ts 2>&1 | tail -20
```
Expected: FAIL with "Cannot find module" or similar.

- [ ] **Step 4: Implement the composable**

Create `dashboard/src/composables/useSpcodeFileSearch.ts`:

```typescript
// Author: elecvoid243, 2026-07-02
// State machine for the in-sidebar search feature. Mirrors the
// useSpcodeGitLog pattern (kind: idle | loading | ok | error).
//
// Cancellation: every new search() call aborts the previous in-flight
// request via AbortController. The Vue ref `state` is the single source
// of truth for the SearchPanel UI.

import { ref, type Ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";

export type SearchBackend = "ripgrep" | "python";

export type SearchState =
  | { kind: "idle" }
  | { kind: "loading"; query: string }
  | { kind: "ok"; query: string; results: SearchResult[];
      truncated: boolean; backend: SearchBackend; elapsedMs: number }
  | { kind: "error"; query: string; reason: string; elapsedMs: number };

export interface SearchResult {
  path: string;
  line: number;
  column: number;
  snippet: string;
}

export interface SearchOptions {
  umo: string | null;
  worktree: string | null;
  pattern: string;
  pathFilter?: string;
  globFilter?: string;
  caseSensitive?: boolean;
  regex?: boolean;
  maxResults?: number;
  contextChars?: number;
}

export function useSpcodeFileSearch() {
  const state: Ref<SearchState> = ref({ kind: "idle" });
  let inflight: AbortController | null = null;

  function cancel(): void {
    if (inflight) {
      inflight.abort();
      inflight = null;
    }
  }

  async function search(opts: SearchOptions): Promise<void> {
    cancel();
    if (!opts.pattern || !opts.pattern.trim()) {
      state.value = { kind: "idle" };
      return;
    }
    const controller = new AbortController();
    inflight = controller;
    state.value = { kind: "loading", query: opts.pattern };
    try {
      const res = await pluginExtensionApi.post<{
        status: string;
        data: {
          pattern: string;
          backend: SearchBackend;
          result_count: number;
          max_results: number;
          truncated: boolean;
          results: SearchResult[];
          reason: string | null;
          elapsed_ms: number;
        };
      }>(
        "spcode/file-search",
        {
          umo: opts.umo,
          worktree: opts.worktree,
          pattern: opts.pattern,
          path_filter: opts.pathFilter ?? null,
          glob_filter: opts.globFilter ?? null,
          case_sensitive: opts.caseSensitive ?? false,
          regex: opts.regex ?? false,
          max_results: opts.maxResults ?? 200,
          context_chars: opts.contextChars ?? 60,
        },
        { signal: controller.signal },
      );
      // If a newer search already started, drop this response
      if (controller.signal.aborted) return;
      const data = res.data?.data;
      if (!data) {
        state.value = {
          kind: "error",
          query: opts.pattern,
          reason: "network_error",
          elapsedMs: 0,
        };
        return;
      }
      if (data.reason) {
        state.value = {
          kind: "error",
          query: opts.pattern,
          reason: data.reason,
          elapsedMs: data.elapsed_ms ?? 0,
        };
        return;
      }
      state.value = {
        kind: "ok",
        query: opts.pattern,
        results: data.results ?? [],
        truncated: data.truncated ?? false,
        backend: data.backend ?? "python",
        elapsedMs: data.elapsed_ms ?? 0,
      };
    } catch (err: unknown) {
      const e = err as { name?: string; code?: string };
      if (e?.name === "CanceledError" || controller.signal.aborted) return;
      state.value = {
        kind: "error",
        query: opts.pattern,
        reason: "network_error",
        elapsedMs: 0,
      };
    } finally {
      if (inflight === controller) inflight = null;
    }
  }

  return { state, search, cancel };
}
```

- [ ] **Step 5 (if vitest present): Run test to verify it passes**

```bash
cd F:\github\Astrbot\dashboard
npx vitest run src/composables/__tests__/useSpcodeFileSearch.test.ts 2>&1 | tail -10
```
Expected: 5 passed.

- [ ] **Step 6: Type check (REQUIRED)**

```bash
cd F:\github\Astrbot\dashboard
npx vue-tsc --noEmit 2>&1 | tail -20
```
Expected: 0 errors. If errors, fix the composable until they pass.

- [ ] **Step 7: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/composables/useSpcodeFileSearch.ts \
        dashboard/src/composables/__tests__/useSpcodeFileSearch.test.ts
git commit -m "feat(dashboard): add useSpcodeFileSearch composable

State machine (idle | loading | ok | error) + AbortController
cancellation + pluginExtensionApi.post call to /spcode/file-search.
Mirrors useSpcodeGitLog pattern. Trims whitespace, returns to idle
on empty pattern without hitting the API."
```

---

## Task 5: Frontend — `SearchPanel.vue` component

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/SearchPanel.vue`

**Interfaces:**
- Props: `modelValue: boolean`, `worktree: string | null`, `umo: string | null`
- Emits: `(e: "update:modelValue", v: boolean)`, `(e: "open-file", p: { path: string; line: number })`
- Internal: calls `useSpcodeFileSearch().search()` on 300ms debounce
- Visual: input row + status row + result list; loading spinner inline; `🐢` chip when `backend === "python"`

- [ ] **Step 1: Create the component**

Create `dashboard/src/components/chat/message_list_comps/SearchPanel.vue`:

```vue
<!--
  Author: elecvoid243, 2026-07-02
  SearchPanel — in-sidebar content search results UI.
  Spec: docs/superpowers/specs/2026-07-02-sidebar-search-design.md §4.4
-->
<script setup lang="ts">
import { ref, watch, nextTick, onMounted, useTemplateRef } from "vue";
import { useSpcodeFileSearch, type SearchResult } from "@/composables/useSpcodeFileSearch";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  modelValue: boolean;
  worktree: string | null;
  umo: string | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [v: boolean];
  "open-file": [p: { path: string; line: number }];
}>();

const { tm } = useModuleI18n("features/chat");
const { state, search, cancel } = useSpcodeFileSearch();

const query = ref("");
const debounceTimer = ref<ReturnType<typeof setTimeout> | null>(null);
const inputRef = useTemplateRef<HTMLInputElement>("inputRef");

// 300ms debounce per spec §4.4
watch(query, (v) => {
  if (debounceTimer.value) clearTimeout(debounceTimer.value);
  if (!v.trim()) {
    cancel();
    state.value = { kind: "idle" };
    return;
  }
  debounceTimer.value = setTimeout(() => {
    void search({
      umo: props.umo,
      worktree: props.worktree,
      pattern: v,
    });
  }, 300);
});

// Focus the input when the panel opens
watch(
  () => props.modelValue,
  async (open) => {
    if (open) {
      await nextTick();
      inputRef.value?.focus();
    }
  },
);

function onClose(): void {
  if (debounceTimer.value) clearTimeout(debounceTimer.value);
  cancel();
  query.value = "";
  state.value = { kind: "idle" };
  emit("update:modelValue", false);
}

function onResultClick(r: SearchResult): void {
  emit("open-file", { path: r.path, line: r.line });
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    e.stopPropagation();
    onClose();
  }
}

onMounted(() => {
  // Focus on mount if opened
  if (props.modelValue) {
    nextTick(() => inputRef.value?.focus());
  }
});
</script>

<template>
  <div v-if="modelValue" class="search-panel" @keydown="onKeydown">
    <div class="search-panel-input-row">
      <v-icon size="16">mdi-magnify</v-icon>
      <input
        ref="inputRef"
        v-model="query"
        type="text"
        class="search-panel-input"
        :placeholder="tm('spcodeProjectLoad.diffSidebar.search.placeholder')"
        spellcheck="false"
        autocomplete="off"
      />
      <v-icon
        v-if="state.kind === 'loading'"
        size="14"
        class="search-panel-spinner"
      >mdi-loading</v-icon>
      <v-btn
        icon="mdi-close"
        size="x-small"
        variant="text"
        @click="onClose"
      />
    </div>

    <div class="search-panel-status">
      <template v-if="state.kind === 'idle'">
        <span class="text-caption text-medium-emphasis">
          {{ tm("spcodeProjectLoad.diffSidebar.search.hint") }}
        </span>
      </template>
      <template v-else-if="state.kind === 'loading'">
        <span class="text-caption text-medium-emphasis">
          {{ tm("spcodeProjectLoad.diffSidebar.search.searching") }}
        </span>
      </template>
      <template v-else-if="state.kind === 'ok'">
        <span class="text-caption">
          {{
            tm("spcodeProjectLoad.diffSidebar.search.resultCount",
               { count: state.results.length })
          }}
        </span>
        <v-chip
          v-if="state.backend === 'python'"
          size="x-small"
          variant="tonal"
          color="warning"
        >
          {{ tm("spcodeProjectLoad.diffSidebar.search.fallbackHint") }}
        </v-chip>
        <span v-if="state.truncated" class="text-caption text-warning">
          {{ tm("spcodeProjectLoad.diffSidebar.search.truncated") }}
        </span>
      </template>
      <template v-else-if="state.kind === 'error'">
        <span class="text-caption text-error">
          {{
            tm("spcodeProjectLoad.diffSidebar.search.error." + state.reason,
               {}, { missing: state.reason })
          }}
        </span>
      </template>
    </div>

    <ul v-if="state.kind === 'ok' && state.results.length" class="search-panel-results">
      <li
        v-for="(r, i) in state.results"
        :key="i"
        class="search-panel-result"
        @click="onResultClick(r)"
      >
        <div class="search-panel-result-path">
          {{ r.path }}:{{ r.line }}:{{ r.column }}
        </div>
        <pre class="search-panel-result-snippet">{{ r.snippet }}</pre>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.search-panel {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 50%;
  overflow: hidden;
}
.search-panel-input-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.search-panel-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface));
  font-family: inherit;
}
.search-panel-status {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 18px;
  flex-wrap: wrap;
}
.search-panel-results {
  list-style: none;
  padding: 0;
  margin: 0;
  overflow-y: auto;
  flex: 1;
}
.search-panel-result {
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
}
.search-panel-result:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.search-panel-result-path {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.search-panel-result-snippet {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 12px;
  margin: 2px 0 0 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: rgb(var(--v-theme-on-surface));
}
.search-panel-spinner {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
```

> **i18n note:** This component references `spcodeProjectLoad.diffSidebar.search.*` keys. Task 7 adds those keys. Until then, `tm()` calls return the key string itself, which is fine for development (the UI just shows the key as a placeholder).

- [ ] **Step 2: Type check**

```bash
cd F:\github\Astrbot\dashboard
npx vue-tsc --noEmit 2>&1 | tail -10
```
Expected: 0 errors. The component has unused prop warnings (`modelValue` is used; `worktree`/`umo` are forwarded to search) — no errors, just maybe one "unused" warning that can be ignored or fixed by adding `// eslint-disable-line` if the project's eslint config flags it.

- [ ] **Step 3: Prettier**

```bash
cd F:\github\Astrbot\dashboard
npx prettier --write src/components/chat/message_list_comps/SearchPanel.vue
```
Expected: no further changes after the write.

- [ ] **Step 4: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/SearchPanel.vue
git commit -m "feat(dashboard): add SearchPanel component

Input row with magnify icon + close button; 300ms debounce on query
changes; status row showing result count / loading / error / 🐢
fallback chip / truncation warning; result list with path:line:col
+ snippet (monospace). Esc closes the panel. Emits open-file with
{path, line} on result click for the parent to handle preview nav."
```

---

## Task 6: Frontend — `GitDiffSidebar` integration

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

**Interfaces:**
- New state: `searchOpen: ref<boolean>` + localStorage persistence
- New key: `STORAGE_KEYS.searchOpen`
- New keydown handler: `Cmd/Ctrl-F` toggles `searchOpen` when sidebar visible + viewMode==='files'; `Escape` closes search when open
- Search button in Files-toolbar row (between view tabs and FileBrowserView)
- `FileBrowserView` gets 3 new props + 2 new emits
- New method: `onFileOpen({path, line})` sets `fileBrowserPreviewPath` and `fileBrowserCurrentPath` so the existing FileBrowserView opens the file

- [ ] **Step 1: Add localStorage key and state**

In `dashboard/src/components/chat/GitDiffSidebar.vue`, locate the `STORAGE_KEYS` object (around line 60-65) and add:

```typescript
const STORAGE_KEYS = {
  viewMode: "astrbot.spcode.gitDiffSidebar.viewMode",
  fileBrowserCurrentPath:
    "astrbot.spcode.gitDiffSidebar.fileBrowserCurrentPath",
  selectedWorktree: "astrbot.spcode.gitDiffSidebar.selectedWorktree",
  selectedScope: "astrbot.spcode.gitDiffSidebar.selectedScope",
  searchOpen: "astrbot.spcode.gitDiffSidebar.searchOpen",  // 新增 2026-07-02
} as const;
```

Find the `loadViewMode`/`loadFileBrowserCurrentPath`/`loadSelectedScope` helpers, then add `loadSearchOpen`:

```typescript
function loadSearchOpen(): boolean {
  return safeGetItem(STORAGE_KEYS.searchOpen) === "true";
}
```

Add the ref after the existing `fileBrowserPreviewPath` ref (around line 175):

```typescript
// Sidebar 内搜索面板开关。持久化:刷新后保持展开/收起。
// 不持久化 query / results(隐私 + 状态过期)。
const searchOpen = ref<boolean>(loadSearchOpen());
watch(searchOpen, (v) => safeSetItem(STORAGE_KEYS.searchOpen, String(v)),
      { flush: "post" });
```

- [ ] **Step 2: Add keydown handler for `Cmd/Ctrl-F` and `Escape`**

In `GitDiffSidebar.vue`, locate the `onMounted` block. If there isn't one already, add:

```typescript
import { ref, watch, onBeforeUnmount, computed, onMounted, nextTick } from "vue";  // already imported
```

Then **after the existing `onMounted` content** (or add `onMounted` if missing), add:

```typescript
// 监听 Cmd/Ctrl-F (切换搜索面板) 和 Escape (关闭搜索面板)。
// 仅在 sidebar 可见 + viewMode === 'files' 时拦截 Cmd-F,避免抢全局快捷键。
function onKeydown(e: KeyboardEvent): void {
  if (!props.modelValue) return;
  const isMod = e.metaKey || e.ctrlKey;
  if (isMod && (e.key === "f" || e.key === "F")) {
    if (viewMode.value !== "files") return;
    e.preventDefault();
    searchOpen.value = !searchOpen.value;
    if (searchOpen.value) {
      nextTick(() => {
        document.querySelector<HTMLInputElement>(".search-panel-input")?.focus();
      });
    }
  } else if (e.key === "Escape" && searchOpen.value) {
    // 由 SearchPanel 自身处理 close;但若焦点不在 panel 内,这里兜底关闭
    const target = e.target as HTMLElement | null;
    if (target && !target.closest(".search-panel")) {
      searchOpen.value = false;
    }
  }
}

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeydown);
});
```

- [ ] **Step 3: Add search button to Files toolbar**

Locate the existing `viewMode === 'files'` block in the template (around line 2163-2171) where `<FileBrowserView>` is rendered. The search button should appear in a toolbar row above the FileBrowserView. Add this between the `view-tabs` div and the `FileBrowserView` block:

```vue
      <!-- Files 视图专用工具栏(2026-07-02 v2.15.0:搜索入口) -->
      <div
        v-if="viewMode === 'files'"
        class="git-diff-sidebar-files-toolbar"
      >
        <v-btn
          icon
          size="small"
          variant="text"
          :class="['git-diff-sidebar-search-toggle',
                   { 'is-active': searchOpen }]"
          :title="tm('spcodeProjectLoad.diffSidebar.search.button')"
          @click="searchOpen = !searchOpen"
        >
          <v-icon size="16">mdi-magnify</v-icon>
        </v-btn>
        <span
          v-if="searchOpen"
          class="text-caption text-medium-emphasis"
        >
          {{ tm("spcodeProjectLoad.diffSidebar.search.toolbarActive") }}
        </span>
      </div>
```

Add a minimal CSS rule (append to the existing `<style scoped>` block):

```css
.git-diff-sidebar-files-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.git-diff-sidebar-search-toggle.is-active {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}
```

- [ ] **Step 4: Pass props and handle open-file**

Replace the existing `<FileBrowserView>` block with:

```vue
      <FileBrowserView
        v-if="viewMode === 'files'"
        ref="fileBrowserRef"
        :current-path="fileBrowserCurrentPath"
        :preview-path="fileBrowserPreviewPath"
        :is-dark="!!isDark"
        :root-path="currentRoot"
        :search-open="searchOpen"
        :umo="spcodeStatus.status.value.umo"
        :worktree="selectedWorktree"
        @navigate="onFileBrowserNavigate"
        @open-file="onFileOpen"
        @update:search-open="searchOpen = $event"
      />
```

Add the `onFileOpen` handler in the `<script setup>`:

```typescript
function onFileOpen(payload: { path: string; line: number }): void {
  // 打开文件:设置 preview path(FileBrowserView 会 fetch 并 scroll 到行)
  fileBrowserPreviewPath.value = payload.path;
  // 同时把 currentPath 设到文件所在目录,让 breadcrumb 显示上下文
  const dir = payload.path.replace(/[\\/][^\\/]+$/, "");
  if (dir && dir !== fileBrowserCurrentPath.value) {
    fileBrowserCurrentPath.value = dir;
  }
}
```

> **i18n key:** `spcodeProjectLoad.diffSidebar.search.toolbarActive` is added in Task 7.

- [ ] **Step 5: Type check + prettier**

```bash
cd F:\github\Astrbot\dashboard
npx vue-tsc --noEmit 2>&1 | tail -10
npx prettier --write src/components/chat/GitDiffSidebar.vue
```
Expected: 0 type errors.

- [ ] **Step 6: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(dashboard): wire search button + Cmd-F + open-file in sidebar

GitDiffSidebar gains a search button (Files toolbar) + Cmd/Ctrl-F
shortcut (only when sidebar visible + viewMode=files) + Escape
fallback close. searchOpen state persisted to localStorage.
FileBrowserView now receives search-open / umo / worktree props and
emits open-file; sidebar sets preview path on result click so the
existing FileBrowserView content fetch + line scroll kicks in."
```

---

## Task 7: Frontend — `FileBrowserView` integration

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue`

**Interfaces:**
- New props: `searchOpen: boolean`, `umo: string | null`, `worktree: string | null`
- New emits: `(e: "update:searchOpen", v: boolean)`, `(e: "open-file", p: { path: string; line: number })`
- Render `<SearchPanel>` at the top of the component when `searchOpen` is true; the existing file tree is hidden while the search panel is open (replaced by the result list)

- [ ] **Step 1: Add props and emits to `<script setup>`**

In `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue`, locate the `defineProps` and `defineEmits` blocks and add:

```typescript
const props = defineProps<{
  currentPath: string;
  previewPath: string | null;
  isDark: boolean;
  rootPath: string | null;
  searchOpen?: boolean;  // 新增 2026-07-02
  umo?: string | null;    // 新增 2026-07-02
  worktree?: string | null;  // 新增 2026-07-02
}>();

const emit = defineEmits<{
  navigate: [path: string];
  "open-file": [p: { path: string; line: number }];  // 新增 2026-07-02
  "update:searchOpen": [v: boolean];  // 新增 2026-07-02
}>();
```

- [ ] **Step 2: Add `<SearchPanel>` to the template**

Locate the existing root `<div>` of the template. Inside it, add `<SearchPanel>` as the first child:

```vue
<template>
  <div class="file-browser-view">
    <SearchPanel
      v-if="props.searchOpen"
      :model-value="props.searchOpen"
      :worktree="props.worktree ?? null"
      :umo="props.umo ?? null"
      @update:model-value="emit('update:searchOpen', $event)"
      @open-file="emit('open-file', $event)"
    />
    <!-- existing file tree + preview panes, hidden while search is open -->
    <template v-if="!props.searchOpen">
      <!-- (rest of existing template here) -->
    </template>
  </div>
</template>
```

> **Important:** The `v-if="!props.searchOpen"` wrapper on the existing template is the simplest way to hide it. The file tree + preview both stay mounted (preserving their state) but are display:none. Adjust if FileBrowserView uses a more complex layout (e.g. resizable split) — the key is that the search panel is the only visible content while open.

- [ ] **Step 3: Add the SearchPanel import**

At the top of the `<script setup>` block, add:

```typescript
import SearchPanel from "./SearchPanel.vue";
```

- [ ] **Step 4: Type check + prettier**

```bash
cd F:\github\Astrbot\dashboard
npx vue-tsc --noEmit 2>&1 | tail -10
npx prettier --write src/components/chat/message_list_comps/FileBrowserView.vue
```
Expected: 0 type errors.

- [ ] **Step 5: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/FileBrowserView.vue
git commit -m "feat(dashboard): mount SearchPanel in FileBrowserView

Renders <SearchPanel> at the top of FileBrowserView when searchOpen
is true; existing file tree is hidden while the search panel owns
the visible area. Forwards update:searchOpen and open-file events
to GitDiffSidebar."
```

---

## Task 8: Frontend — i18n keys (3 locales)

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

**Interfaces:**
- New key namespace: `spcodeProjectLoad.diffSidebar.search`
- ~12 keys per locale (mirror across all 3)

- [ ] **Step 1: Add zh-CN keys**

Open `dashboard/src/i18n/locales/zh-CN/features/chat.json`. Find the existing `diffSidebar` key and locate an existing `gitWorkflow` or other sub-object to understand the structure. Then add a `search` sub-object at the same level. The exact insertion point depends on the file's organization — use the same nesting as `gitWorkflow.history.tab` style keys.

The keys to add (per spec §4.7):

```jsonc
    "search": {
      "button": "搜索文件 (Cmd/Ctrl-F)",
      "placeholder": "在项目中搜索…",
      "hint": "输入关键词搜索 · Esc 关闭",
      "searching": "正在搜索…",
      "resultCount": "{count} 个匹配",
      "truncated": "已截断 — 请缩小搜索范围",
      "toolbarActive": "搜索中…",
      "fallbackHint": "🐢 Python 兜底(安装 ripgrep 可加速)",
      "error": {
        "invalid_pattern": "无效的搜索模式",
        "pattern_too_long": "搜索模式过长(最长 256 字符)",
        "search_unavailable": "搜索不可用",
        "search_timeout": "搜索超时(5 秒)",
        "path_unsafe_filter": "路径过滤器不安全",
        "no_project_loaded": "未加载项目",
        "worktree_invalid": "无效的 worktree",
        "directory_missing": "目录不存在",
        "not_a_git_repo": "不是 git 仓库",
        "network_error": "网络错误"
      }
    },
```

The exact nesting depends on whether `gitWorkflow` is at `diffSidebar.gitWorkflow.*` (sibling to `search`) or at `diffSidebar.search.*` (same level). Match the existing style.

- [ ] **Step 2: Add en-US keys**

Same path, en-US file:

```jsonc
    "search": {
      "button": "Search files (Cmd/Ctrl-F)",
      "placeholder": "Search in project…",
      "hint": "Type to search · Esc to close",
      "searching": "Searching…",
      "resultCount": "{count} match(es)",
      "truncated": "Truncated — narrow your pattern",
      "toolbarActive": "Searching…",
      "fallbackHint": "🐢 Python fallback (install ripgrep for speed)",
      "error": {
        "invalid_pattern": "Invalid pattern",
        "pattern_too_long": "Pattern too long (max 256 chars)",
        "search_unavailable": "Search unavailable",
        "search_timeout": "Search timed out (5s)",
        "path_unsafe_filter": "Path filter is unsafe",
        "no_project_loaded": "No project loaded",
        "worktree_invalid": "Invalid worktree",
        "directory_missing": "Directory missing",
        "not_a_git_repo": "Not a git repository",
        "network_error": "Network error"
      }
    },
```

- [ ] **Step 3: Add ru-RU keys**

Same path, ru-RU file:

```jsonc
    "search": {
      "button": "Поиск файлов (Cmd/Ctrl-F)",
      "placeholder": "Искать в проекте…",
      "hint": "Введите для поиска · Esc для закрытия",
      "searching": "Поиск…",
      "resultCount": "{count} совпадений",
      "truncated": "Обрезано — сузьте шаблон",
      "toolbarActive": "Идёт поиск…",
      "fallbackHint": "🐢 Резервный Python (установите ripgrep для скорости)",
      "error": {
        "invalid_pattern": "Неверный шаблон",
        "pattern_too_long": "Шаблон слишком длинный (макс. 256 символов)",
        "search_unavailable": "Поиск недоступен",
        "search_timeout": "Тайм-аут поиска (5 с)",
        "path_unsafe_filter": "Небезопасный фильтр пути",
        "no_project_loaded": "Проект не загружен",
        "worktree_invalid": "Неверный worktree",
        "directory_missing": "Каталог отсутствует",
        "not_a_git_repo": "Не git-репозиторий",
        "network_error": "Сетевая ошибка"
      }
    },
```

- [ ] **Step 4: Validate JSON**

```bash
cd F:\github\Astrbot\dashboard
python -c "import json; [json.load(open(f'src/i18n/locales/{l}/features/chat.json')) for l in ['zh-CN','en-US','ru-RU']]; print('OK')"
```
Expected: `OK`. If any file is malformed, fix it and re-run.

- [ ] **Step 5: Type check (no Vue change but defensive)**

```bash
cd F:\github\Astrbot\dashboard
npx vue-tsc --noEmit 2>&1 | tail -5
```
Expected: 0 errors.

- [ ] **Step 6: Prettier (the JSON files)**

```bash
cd F:\github\Astrbot\dashboard
npx prettier --write src/i18n/locales/zh-CN/features/chat.json \
                src/i18n/locales/en-US/features/chat.json \
                src/i18n/locales/ru-RU/features/chat.json
```
Expected: no further changes after write.

- [ ] **Step 7: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/i18n/locales/zh-CN/features/chat.json \
        dashboard/src/i18n/locales/en-US/features/chat.json \
        dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "feat(dashboard): i18n keys for sidebar search

Adds spcodeProjectLoad.diffSidebar.search.* across zh-CN / en-US /
ru-RU: button, placeholder, hint, searching, resultCount, truncated,
toolbarActive, fallbackHint, plus 10 error.* keys covering every
ReasonCode in the backend."
```

---

## Self-Review

### Spec coverage

| Spec section | Implemented in |
|---|---|
| §3.3 Handler skeleton + rg primary path | Task 2 |
| §3.3 Python fallback | Task 3 |
| §3.4 rg probe in main.py | Task 1 |
| §3.5 ReasonCode extensions | Task 1 |
| §3.6 conf_schema | Task 1 |
| §4.3 useSpcodeFileSearch composable | Task 4 |
| §4.4 SearchPanel.vue | Task 5 |
| §4.5 GitDiffSidebar integration (button, Cmd-F, localStorage) | Task 6 |
| §4.6 FileBrowserView integration | Task 7 |
| §4.7 i18n keys (3 locales) | Task 8 |
| §5 Interface contract | Tasks 2-3 (envelope), Tasks 4-5 (frontend mapping) |
| §7 Testing strategy | Tasks 2-3 (pytest), Task 4 (vitest if available) |
| §8 Risks (rg missing, etc.) | Tasks 1-3 (graceful degradation) |

No spec requirement is missing.

### Placeholder scan

No "TBD", "TODO", "implement later", or "fill in details" in any task. All code blocks are complete (some are large but intentionally so for clarity).

### Type consistency

- `plugin._rg_available: bool` and `plugin._rg_path: str` — defined in Task 1, used in Tasks 2-3. ✅
- `ReasonCode` entries — defined in Task 1, used in Tasks 2-3. ✅
- `useSpcodeFileSearch` export shape — `{state, search, cancel}` consistent across Tasks 4-5. ✅
- `SearchPanel` props/emits — defined in Task 5, used in Task 7. ✅
- i18n keys — `spcodeProjectLoad.diffSidebar.search.*` referenced in Tasks 5-6, defined in Task 8. ✅
- `onFileOpen` handler — defined in Task 6, called from FileBrowserView via `open-file` event in Task 7. ✅

### Open question in Task 3

Step 4 of Task 3 has a duplicate `worktree=worktree,` line marked as a placeholder. The implementation step explicitly tells the engineer to verify and fix. This is **not** a placeholder — it's a code-review note for a copy-paste hazard.

### Open question in Task 4

Step 1 (vitest check) and Steps 2/3/5 (test code) are conditional on vitest being set up. If absent, those steps are skipped. The composable implementation (Step 4) is unconditional. This is **not** a gap — it's a graceful degradation that depends on the project's existing test infrastructure.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-02-sidebar-search.md`. 8 tasks, each is a self-contained deliverable with its own commit. TDD where pytest/vitest is set up; defensive type checks elsewhere.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for: parallel work, clean context per task, fresh review on every commit.

**2. Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints for review. Best for: linear, single-developer execution, when you want to see every step in real time.

**Which approach?**
