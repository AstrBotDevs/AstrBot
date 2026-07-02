# GitDiffSidebar In-Sidebar 搜索功能 — 设计 Spec

| | |
|---|---|
| **作者** | elecvoid243 |
| **日期** | 2026-07-02 |
| **分支** | all |
| **状态** | draft（待审核） |
| **范围** | v1：仅 In-sidebar content search；不含 outline / recent files / blame / AI-edited 标记 |

---

## 1. 背景与目标

### 1.1 现状

`GitDiffSidebar` 的 **Files 视图**目前只暴露目录树 + 文件预览，缺少"按内容快速定位文件"的能力。当用户希望：

- 在 `astrbot/` 子目录下找所有调用 `record_error` 的位置
- 找到 `TODO` 注释所在的所有文件
- 搜索"auth"相关的所有标识符

唯一可行路径是：在 chat 里让 agent 调用 `es_search`（**仅文件名**搜索，**不**能搜内容）或者 `codegraph_explore`（首次索引 5-30s，且依赖外部 CLI）。这两个工具对"快速人肉浏览"场景太重。

### 1.2 目标

在 Files 视图内增加一个**人肉即时搜索**入口：

- **触发**：`Cmd/Ctrl-F`（sidebar 可见时）或者工具栏的搜索按钮
- **行为**：输入 pattern → 300ms debounce → 后端搜索 → 实时结果列表
- **结果点击**：右侧 preview 打开文件 + 滚动到匹配行 + 行内高亮 2s
- **快捷**：Esc 收起
- **目标延迟**：rg 命中 P95 < 100ms；兜底 Python 路径 P95 < 2s（5k 文件小仓库）

### 1.3 非目标（v1 不做）

- ❌ 文件 outline / symbol tree（v1 不做）
- ❌ 最近修改文件列表（git log --name-only 派生，留 v2）
- ❌ blame chip / AI-edited 标记（需新 hook 点，留 v2）
- ❌ 搜索结果内二次过滤（type/case/regex 开关的完整 UI 暴露，留 v2）
- ❌ 跨 worktree 搜索（每次只搜当前 worktree）
- ❌ 在 Diff / History 视图内搜索（只在 Files 视图）

### 1.4 用户故事

1. 作为 AstrBot 用户，我在浏览项目时想找某个函数的所有调用点。打开侧边栏，按 `Cmd-F` 输入函数名，立即看到所有匹配位置，点击跳转到具体行。
2. 作为 AstrBot 用户，我在 review 之前想确认没有遗留 `TODO`。打开搜索，输入 `TODO`，看到所有 TODO 所在文件。
3. 作为 AstrBot 用户，rg 没装在系统上。我希望搜索仍然能用（变慢），而不是直接报错。

---

## 2. 设计决策

### 2.1 决策表

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| 1 | 搜索后端 | **ripgrep 优先 + 纯 Python 兜底** | rg 极快（5-30ms），`--json` 易解析；rg 缺失时 Python 兜底保证功能可用，前端用 `backend` 字段提示用户 |
| 2 | 后端实现位置 | spcode 工具箱插件（`astrbot_plugin_spcode_toolkit`） | 与现有 14 个 `/spcode/*` 端点同模块；前端已经在用 `pluginExtensionApi` |
| 3 | HTTP 方法 | **POST** + JSON body | pattern/filter 字段多 + 含 glob/正则，GET 长度受限且 URL 编码复杂 |
| 4 | 路径规范 | repo-relative | 与 `git-log` / `git-show` 现有约定一致 |
| 5 | 端点位置 | `POST /spcode/file-search` | 命名对齐 `file-browser` / `file-restore` |
| 6 | rg 缺失行为 | graceful degradation（`backend=python`） | 符合现有 `git unavailable` 的处理模式（`main.py:226-231`） |
| 7 | 结果截断 | hard cap `max_results`（默认 200，上限 1000） | 避免 10MB JSON 阻塞前端；超限时 `truncated=true` |
| 8 | 二进制 / 隐藏文件 | 跳过（rg 默认；Python 兜底跳过 `__pycache__` `.git` `.venv` `node_modules`） | 用户搜的是代码；二进制无意义 |
| 9 | 结果排序 | 按 `(path, line)` 升序 | 与 rg 一致；确定性 |
| 10 | 取消正在飞行的搜索 | 前端 use `AbortController` | 用户快速改 query 时取消旧请求 |
| 11 | 超时 | 5s（rg / Python 子进程统一） | rg P99 < 100ms；5s 只在最坏情况触发 |
| 12 | 缓存 | **不缓存**（每次按需请求） | 搜索 QPS 低（人肉操作），缓存失效逻辑复杂 |
| 13 | Cmd-F 快捷键作用域 | sidebar 可见 **且** viewMode === 'files' | 其他视图 / 隐藏时不抢全局快捷键 |
| 14 | localStorage 持久化 | 仅持久化 `searchOpen`（boolean） | 刷新后保持展开/收起；不持久化 query / 结果（隐私 + 状态过期） |
| 15 | rg 子进程编码 | utf-8 + `errors="replace"` | 与 `_run_git_async` 风格一致 |

### 2.2 关键权衡

**为什么不做 outline：** tree-sitter / codegraph MCP 都太重（包体 50MB+ / 5-30s 索引），手写 regex 准确度差。搜索能解决 80% 的"找代码"问题。

**为什么 rg + 兜底而不是只 rg：** AstrBot 用户多数在 Windows。Git for Windows 不带 rg。要求用户额外装 rg 是摩擦。Python 兜底虽然慢但能跑，把"装 rg"变成性能优化而不是硬需求。

**为什么 POST 不是 GET：** pattern / glob 字段可能含空格、`*`、`{`、正则元字符。GET 的 URL 编码 + 长 pattern 容易触发中间代理截断（实测 4-8KB 限制）。POST 没有这个坑。

---

## 3. 后端架构

### 3.1 新增文件

```
astrbot_plugin_spcode_toolkit/
├── tools/webapi/
│   ├── file_search.py             # 新增：POST /spcode/file-search handler
│   └── __init__.py                # 改：注册新路由到 ROUTES
├── tests/
│   └── test_file_search.py        # 新增：单测
├── _conf_schema.json              # 改：新增 search 分组
└── main.py                        # 改：init 时探测 rg
```

### 3.2 路由注册（`tools/webapi/__init__.py`）

按现有 ROUTES 列表风格追加（按字典序插入到 `file-browser` 之前）：

```python
from . import (
    # ... 现有 imports
    file_search,  # 新增
    # ...
)

ROUTES: list[tuple[str, list[str], Callable, str]] = [
    # ... 现有 routes
    (
        "/spcode/file-search",      # 新增
        ["POST"],
        file_search.handle,
        "在已加载项目(指定 worktree)内按内容搜索文件",
    ),
    # ...
]
```

### 3.3 Handler 模块（`tools/webapi/file_search.py`）

骨架：

```python
"""POST /spcode/file-search — 在项目内按内容搜索文件。

Spec: docs/superpowers/specs/2026-07-02-sidebar-search-design.md

后端实现:ripgrep 优先(plugin._rg_available=True);缺失则走纯 Python 兜底。
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._helpers import (
    _JSONResponseCompat,
    _make_envelope,
    _run_git_async,  # 复用 git 异步子进程模式(虽然不用,但模板一致)
    ReasonCode,
)
from .git_log import _git_endpoint_preflight  # 复用 5 步前置
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

# Python 兜底要跳过的目录(降低 95% IO)
_PYTHON_FALLBACK_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "target", ".next", ".nuxt",
    ".idea", ".vscode",
})


# ── ReasonCode 扩展 ──
# 在 _helpers.ReasonCode 类内追加(详见 §3.5):
#   SEARCH_UNAVAILABLE    = "search_unavailable"   # 兜底 Python 也失败
#   SEARCH_TIMEOUT        = "search_timeout"
#   INVALID_PATTERN       = "invalid_pattern"
#   PATTERN_TOO_LONG      = "pattern_too_long"
#   PATH_UNSAFE_FILTER    = "path_unsafe_filter"
#   GLOB_INVALID          = "glob_invalid"


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
) -> dict:
    """调用 ripgrep 并解析 --json 输出。"""

    cmd: list[str] = [
        rg_path,
        "--json",                         # 机器可读
        "--no-config",                    # 不读 ~/.ripgreprc
        "--no-heading",                   # 不要 path:line: 前缀
        "--line-number",
        "--column",
        "--no-messages",                  # 不输出 "regex parse error" 之类到 stderr
        "--max-columns=200",              # 限制超长行
        "--max-columns-preview",          # 截断后加 ...
        "--max-filesize=1M",              # 单文件 1MB 上限
        "--no-follow",                    # 不跟随 symlink
        "--",                             # 后续全部视为 pattern/file
    ]
    if not case_sensitive:
        cmd.append("--ignore-case")
    if not regex:
        cmd.append("--fixed-strings")
    if glob_filter:
        cmd.extend(["--glob", glob_filter])
    # rg --max-count 是 per-file 上限,这里用 per-search cap
    # 因为 max_results 是 cross-file,需要在解析后截断
    cmd.extend(["--max-count", str(max_results)])
    cmd.append(pattern)
    # path_filter 限定子目录(repo-relative,已 validate)
    if path_filter:
        cmd.append(os.path.join(directory, path_filter))
    else:
        cmd.append(directory)

    # pythonw.exe 下抑制黑窗
    import sys as _sys
    import subprocess as _sp
    no_window = (
        {"creationflags": _sp.CREATE_NO_WINDOW}
        if _sys.platform == "win32"
        else {}
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.create_subprocess.PIPE,
            stderr=asyncio.create_subprocess.PIPE,
            cwd=directory or None,
            **no_window,
        )
    except FileNotFoundError:
        return {"ok": False, "error": f"{rg_path} 未安装或不在 PATH 中"}

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return {"ok": False, "error": f"rg timeout ({SEARCH_TIMEOUT_SECONDS}s)"}

    if proc.returncode == 0:
        return {"ok": True, "stdout": stdout_bytes.decode("utf-8", errors="replace")}
    if proc.returncode == 1:
        # rg exit 1 = "no matches" — 视为成功但无结果
        return {"ok": True, "stdout": "", "stdout_bytes": b""}
    # exit 2 = regex 错误等
    err_msg = stderr_bytes.decode("utf-8", errors="replace").strip()
    return {"ok": False, "error": err_msg or f"rg exit {proc.returncode}"}


def _parse_ripgrep_json(
    raw: str,
    max_results: int,
    context_chars: int,
) -> tuple[list[dict], bool]:
    """解析 rg --json 输出为 frontend-ready result 列表。

    Returns:
        (results, truncated)
    """
    results: list[dict] = []
    truncated = False
    # rg --json 是 NDJSON(stream of JSON objects)
    for line in raw.splitlines():
        if len(results) >= max_results:
            truncated = True
            break
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # 容错:跳过坏行
        if obj.get("type") != "match":
            continue  # 跳过 begin/summary/end 等
        data = obj["data"]
        path = data["path"]["text"]
        line_no = int(data["line_number"])
        # 取第一个 submatch(我们没有 -o 多 submatch)
        if not data.get("submatches"):
            continue
        sub = data["submatches"][0]
        col = int(sub["start"]) + 1  # 0-based -> 1-based
        full_line_text = data["lines"]["text"].rstrip("\n")
        snippet = _make_snippet(full_line_text, col - 1, len(sub["match"]["text"]),
                                context_chars)
        results.append({
            "path": path,
            "line": line_no,
            "column": col,
            "snippet": snippet,
        })
    return results, truncated


def _make_snippet(line: str, match_start: int, match_len: int,
                  context_chars: int) -> str:
    """从一整行中切出含匹配段的 snippet(前后各 context_chars 字符)。"""
    s = max(0, match_start - context_chars)
    e = min(len(line), match_start + match_len + context_chars)
    snippet = line[s:e]
    if s > 0:
        snippet = "..." + snippet
    if e < len(line):
        snippet = snippet + "..."
    # 截断总长 160 字符(超长行不爆前端)
    if len(snippet) > 160:
        # 以 match 为中心重新切
        mid = snippet.find(line[match_start:match_start + match_len])
        if mid >= 0:
            half = 70
            s2 = max(0, mid - half)
            e2 = min(len(snippet), mid + len(line[match_start:match_start + match_len]) + half)
            snippet = ("..." if s2 > 0 else "") + snippet[s2:e2] + ("..." if e2 < len(snippet) else "")
    return snippet


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
) -> tuple[list[dict], bool, str | None]:
    """纯 Python 兜底:os.walk + re.finditer。

    Returns:
        (results, truncated, error_message)
    """
    if regex:
        try:
            pat = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
        except re.error as exc:
            return [], False, f"invalid regex: {exc}"
    else:
        pat = re.compile(re.escape(pattern), 0 if case_sensitive else re.IGNORECASE)

    results: list[dict] = []
    truncated = False
    search_root = Path(directory) / path_filter if path_filter else Path(directory)
    if not search_root.is_dir():
        return [], False, f"path_filter not found: {path_filter}"

    glob_re = re.compile(glob_filter.replace(".", r"\.").replace("*", ".*")) \
        if glob_filter else None

    try:
        for root, dirs, files in os.walk(search_root, followlinks=False):
            # 原地修剪:跳过 _PYTHON_FALLBACK_SKIP_DIRS
            dirs[:] = [d for d in dirs if d not in _PYTHON_FALLBACK_SKIP_DIRS
                       and not d.startswith(".")]
            for fname in files:
                if len(results) >= max_results:
                    truncated = True
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
                                col = m.start() + 1
                                results.append({
                                    "path": str(fpath.relative_to(directory)),
                                    "line": i,
                                    "column": col,
                                    "snippet": _make_snippet(
                                        line.rstrip("\n"),
                                        m.start(),
                                        len(m.group(0)),
                                        context_chars,
                                    ),
                                })
                                if len(results) >= max_results:
                                    truncated = True
                                    break
                except OSError:
                    continue
            if len(results) >= max_results:
                truncated = True
                break
    except Exception as exc:
        return results, truncated, f"fallback error: {exc}"

    return results, truncated, None


async def handle(
    plugin: "SPCodeToolkit",
    *,
    umo: str | None = None,
    worktree: str | None = None,
    body: dict = None,
) -> dict:
    """POST /spcode/file-search handler."""
    t0 = time.time()

    def _elapsed() -> int:
        return int((time.time() - t0) * 1000)

    body = body or {}

    # 1. 参数校验
    pattern = (body.get("pattern") or "").strip()
    if not pattern:
        return _make_envelope(
            success=False,
            reason=ReasonCode.INVALID_PATTERN,
            elapsed_ms=_elapsed(),
            umo=umo, worktree=worktree,
        )
    if len(pattern) > MAX_PATTERN_LENGTH:
        return _make_envelope(
            success=False,
            reason=ReasonCode.PATTERN_TOO_LONG,
            elapsed_ms=_elapsed(),
            umo=umo, worktree=worktree,
        )
    if "\n" in pattern or "\r" in pattern:
        return _make_envelope(
            success=False,
            reason=ReasonCode.INVALID_PATTERN,
            elapsed_ms=_elapsed(),
            umo=umo, worktree=worktree,
        )

    case_sensitive = bool(body.get("case_sensitive", False))
    regex = bool(body.get("regex", False))
    max_results = max(1, min(int(body.get("max_results", DEFAULT_MAX_RESULTS)),
                             MAX_MAX_RESULTS))
    context_chars = max(10, min(int(body.get("context_chars", DEFAULT_CONTEXT_CHARS)),
                                MAX_CONTEXT_CHARS))

    path_filter = (body.get("path_filter") or "").strip() or None
    glob_filter = (body.get("glob_filter") or "").strip() or None

    # 2. preflight(umo / worktree / 目录 / git repo)
    err, ctx = await _git_endpoint_preflight(
        plugin, umo=umo, worktree_param=worktree,
    )
    if err is not None:
        err["data"]["elapsed_ms"] = _elapsed()
        return err
    directory = ctx["directory"]
    effective_umo = ctx["umo"]

    # 3. path_filter 防御(若提供)
    if path_filter:
        ok, err_reason, _ = _validate_repo_relative_file(path_filter)
        if not ok:
            return _make_envelope(
                success=False,
                reason=ReasonCode.PATH_UNSAFE_FILTER,
                elapsed_ms=_elapsed(),
                umo=effective_umo, worktree=worktree, directory=directory,
            )

    # 4. 实际搜索
    backend_used = "python"  # 默认兜底
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
        else:
            err_msg = rg_result.get("error", "")
            logger.warning(f"[file-search] rg failed: {err_msg}, falling back to Python")
            if "timeout" in err_msg.lower():
                return _make_envelope(
                    success=False,
                    reason=ReasonCode.SEARCH_TIMEOUT,
                    elapsed_ms=_elapsed(),
                    umo=effective_umo, worktree=worktree, directory=directory,
                )
            if "regex" in err_msg.lower() and regex:
                return _make_envelope(
                    success=False,
                    reason=ReasonCode.INVALID_PATTERN,
                    elapsed_ms=_elapsed(),
                    umo=effective_umo, worktree=worktree, directory=directory,
                )
            # 其他 rg 错误 → 走兜底
            results, truncated, fb_err = await _run_python_fallback(
                pattern=pattern, directory=directory,
                path_filter=path_filter, glob_filter=glob_filter,
                case_sensitive=case_sensitive, regex=regex,
                max_results=max_results, context_chars=context_chars,
            )
            if fb_err and fb_err.startswith("invalid regex"):
                return _make_envelope(
                    success=False,
                    reason=ReasonCode.INVALID_PATTERN,
                    elapsed_ms=_elapsed(),
                    umo=effective_umo, worktree=worktree, directory=directory,
                )
    else:
        results, truncated, fb_err = await _run_python_fallback(
            pattern=pattern, directory=directory,
            path_filter=path_filter, glob_filter=glob_filter,
            case_sensitive=case_sensitive, regex=regex,
            max_results=max_results, context_chars=context_chars,
        )
        if fb_err and fb_err.startswith("invalid regex"):
            return _make_envelope(
                success=False,
                reason=ReasonCode.INVALID_PATTERN,
                elapsed_ms=_elapsed(),
                umo=effective_umo, worktree=worktree, directory=directory,
            )

    return _JSONResponseCompat(
        _make_envelope(
            success=True,
            elapsed_ms=_elapsed(),
            umo=effective_umo,
            worktree=directory,
            pattern=pattern,
            backend=backend_used,
            result_count=len(results),
            max_results=max_results,
            truncated=truncated,
            results=results,
        ),
        status_code=200,
    )
```

### 3.4 init 时探测 rg（`main.py` 修改）

在 `SPCodeToolkit.__init__` 末尾（git 探测之前或之后均可；推荐**之后**）追加：

```python
# ── ripgrep 可用性探测 ──
# 失败不阻塞插件加载;file_search 端点会走纯 Python 兜底。
# 复用 git 探测的 CREATE_NO_WINDOW 抑制黑窗模式。
self._rg_path = (self._config.get("rg_path") or "rg").strip() or "rg"
self._rg_available = False
try:
    import subprocess as _sp
    import sys as _sys
    _NO_WINDOW = (
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
        **_NO_WINDOW,
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
            f"[file-search] ripgrep 探测失败(returncode={_rg_probe.returncode})"
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

### 3.5 `ReasonCode` 扩展（`tools/webapi/_helpers.py`）

在 `ReasonCode` 类内追加：

```python
# ── file-search 专用(v2.15.0,2026-07-02) ──
SEARCH_UNAVAILABLE = "search_unavailable"   # 兜底 Python 也失败
SEARCH_TIMEOUT = "search_timeout"           # 5s 超时
INVALID_PATTERN = "invalid_pattern"         # pattern 为空 / 含换行 / 正则语法错
PATTERN_TOO_LONG = "pattern_too_long"       # > 256 chars
PATH_UNSAFE_FILTER = "path_unsafe_filter"   # path_filter 越界
```

### 3.6 配置文件（`_conf_schema.json`）

新增 `search` 分组：

```jsonc
{
  "search": {
    "rg_path": {
      "type": "string",
      "default": "rg",
      "description": "ripgrep 可执行路径。rg 缺失时 /spcode/file-search 自动走纯 Python 兜底(慢)。",
      "tip": "Windows 用户可通过 `winget install BurntSushi.ripgrep` 或 scoop/choco 安装。",
      "placeholder": "rg"
    }
  }
}
```

注：`_conf_schema.json` 在主项目里有（`astrbot_plugin_spcode_toolkit/_conf_schema.json`）；具体结构以现有 schema 为准。改动需与现有分组风格一致（中文 / `description` / `tip` / `placeholder`）。

---

## 4. 前端架构

### 4.1 新增文件

```
dashboard/src/
├── composables/
│   └── useSpcodeFileSearch.ts       # 新增
├── components/chat/message_list_comps/
│   └── SearchPanel.vue              # 新增
└── i18n/locales/{zh-CN,en-US,ru-RU}/
    └── features/chat.json           # 改：加 ~8 个 key
```

### 4.2 改动文件

```
dashboard/src/
├── components/chat/
│   ├── GitDiffSidebar.vue           # 改：加搜索按钮 + Cmd-F 监听
│   └── message_list_comps/
│       └── FileBrowserView.vue      # 改：渲染 <SearchPanel>，接收 open-file 事件
```

### 4.3 Composable（`useSpcodeFileSearch.ts`）

骨架：

```typescript
import { ref, computed } from "vue";
import { pluginExtensionApi } from "@/api/v1";

export type SearchBackend = "ripgrep" | "python";
export type SearchState =
  | { kind: "idle" }
  | { kind: "loading"; query: string; abort: AbortController }
  | { kind: "ok"; query: string; results: SearchResult[]; truncated: boolean;
      backend: SearchBackend; elapsedMs: number }
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
  const state = ref<SearchState>({ kind: "idle" });

  // 取消正在飞行的请求
  let inflight: AbortController | null = null;
  function cancel() {
    if (inflight) {
      inflight.abort();
      inflight = null;
    }
  }

  async function search(opts: SearchOptions): Promise<void> {
    cancel();
    if (!opts.pattern.trim()) {
      state.value = { kind: "idle" };
      return;
    }
    const controller = new AbortController();
    inflight = controller;
    state.value = {
      kind: "loading",
      query: opts.pattern,
      abort: controller,
    };
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
      }>("spcode/file-search", {
        umo: opts.umo,
        worktree: opts.worktree,
        pattern: opts.pattern,
        path_filter: opts.pathFilter ?? null,
        glob_filter: opts.globFilter ?? null,
        case_sensitive: opts.caseSensitive ?? false,
        regex: opts.regex ?? false,
        max_results: opts.maxResults ?? 200,
        context_chars: opts.contextChars ?? 60,
      }, { signal: controller.signal });

      // 若发起新搜索,本调用已被新 controller 取代
      if (controller.signal.aborted) return;

      const data = res.data?.data;
      if (data?.reason) {
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
        results: data?.results ?? [],
        truncated: data?.truncated ?? false,
        backend: data?.backend ?? "python",
        elapsedMs: data?.elapsed_ms ?? 0,
      };
    } catch (err: any) {
      if (err?.name === "CanceledError" || controller.signal.aborted) return;
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

### 4.4 组件（`SearchPanel.vue`）

形态：v-card 风格的面板，渲染在 FileBrowserView 顶部（v-if="searchOpen"）。

```vue
<script setup lang="ts">
import { ref, watch } from "vue";
import { useSpcodeFileSearch, type SearchResult } from "@/composables/useSpcodeFileSearch";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  modelValue: boolean;        // open/closed
  worktree: string | null;
  umo: string | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [v: boolean];
  "open-file": [{ path: string; line: number }];
}>();

const { tm } = useModuleI18n("features/chat");
const { state, search, cancel } = useSpcodeFileSearch();

const query = ref("");
const debounceTimer = ref<ReturnType<typeof setTimeout> | null>(null);

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

function onResultClick(r: SearchResult) {
  emit("open-file", { path: r.path, line: r.line });
}

function onClose() {
  if (debounceTimer.value) clearTimeout(debounceTimer.value);
  cancel();
  query.value = "";
  state.value = { kind: "idle" };
  emit("update:modelValue", false);
}
</script>

<template>
  <div v-if="modelValue" class="search-panel">
    <div class="search-panel-input-row">
      <v-icon size="16">mdi-magnify</v-icon>
      <input
        ref="inputEl"
        v-model="query"
        type="text"
        class="search-panel-input"
        :placeholder="tm('spcodeProjectLoad.diffSidebar.search.placeholder')"
        @keydown.esc="onClose"
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
          {{ tm("spcodeProjectLoad.diffSidebar.search.resultCount",
                 { count: state.results.length }) }}
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
          {{ tm("spcodeProjectLoad.diffSidebar.search.error." + state.reason,
                 {}, { missing: state.reason }) }}
        </span>
      </template>
    </div>

    <ul v-if="state.kind === 'ok'" class="search-panel-results">
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
}
.search-panel-status {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 18px;
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

### 4.5 `GitDiffSidebar.vue` 改动

1. **加 localStorage 键**：
   ```typescript
   const STORAGE_KEYS = {
     // ... 现有 keys
     searchOpen: "astrbot.spcode.gitDiffSidebar.searchOpen",
   } as const;
   ```

2. **加 state + watcher**：
   ```typescript
   const searchOpen = ref(safeGetItem(STORAGE_KEYS.searchOpen) === "true");
   watch(searchOpen, (v) => safeSetItem(STORAGE_KEYS.searchOpen, String(v)),
         { flush: "post" });
   ```

3. **Files 视图下加搜索按钮**（在 view tabs 之后）：
   ```vue
   <div v-if="viewMode === 'files'" class="git-diff-sidebar-files-toolbar">
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
   </div>
   ```

4. **Cmd/Ctrl-F 全局快捷键**（在 onMounted 钩子内）：
   ```typescript
   function onKeydown(e: KeyboardEvent) {
     if (!props.modelValue) return;  // sidebar 隐藏
     if (viewMode.value !== "files") return;
     const isMod = e.metaKey || e.ctrlKey;
     if (isMod && e.key === "f") {
       e.preventDefault();
       searchOpen.value = true;
       // next tick → focus input
       nextTick(() => {
         document.querySelector<HTMLInputElement>(
           ".search-panel-input"
         )?.focus();
       });
     } else if (e.key === "Escape" && searchOpen.value) {
       searchOpen.value = false;
     }
   }
   onMounted(() => {
     window.addEventListener("keydown", onKeydown);
   });
   onBeforeUnmount(() => {
     window.removeEventListener("keydown", onKeydown);
   });
   ```

5. **透传 props 到 FileBrowserView**：
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

6. **结果点击处理**（在 `onFileOpen` 内）：
   ```typescript
   function onFileOpen(payload: { path: string; line: number }) {
     fileBrowserPreviewPath.value = payload.path;
     fileBrowserCurrentPath.value = payload.path;  // 高亮 line
     // (FileBrowserView 收到 preview-path 变化后会 fetch content 并 scroll 到行)
   }
   ```

### 4.6 `FileBrowserView.vue` 改动

- 新增 props: `searchOpen: boolean`, `umo: string | null`, `worktree: string | null`
- 新增 emit: `update:searchOpen`, `open-file`
- 模板顶部（现有 breadcrumb / path 之下）插入：
  ```vue
  <SearchPanel
    :model-value="searchOpen"
    :umo="umo"
    :worktree="worktree"
    @update:model-value="emit('update:searchOpen', $event)"
    @open-file="(p) => emit('open-file', p)"
  />
  ```
- 当 `searchOpen === true` 时，文件树暂时隐藏（只显示搜索面板），让结果占满左半边
- preview 收到 `open-file` 时（来自父组件 GitDiffSidebar），`preview-path` 设置后 fetch + scroll

### 4.7 i18n keys（3 个 locale 各加）

```jsonc
// spcodeProjectLoad.diffSidebar.search.*
"search": {
  "button": "Search files (Cmd/Ctrl-F)",
  "placeholder": "Search in project…",
  "hint": "Type to search · Esc to close",
  "searching": "Searching…",
  "resultCount": "{count} match(es)",
  "truncated": "Truncated — narrow your pattern",
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
}
```

---

## 5. 接口契约

### 5.1 请求

```
POST /spcode/file-search
Content-Type: application/json

{
  "umo": "FriendMessage:webchat!astrbot!xxx",   // 可省，省时回退最近 loaded
  "worktree": "C:/path/to/repo/.worktrees/feat-x",  // 可省，省时用 main worktree
  "pattern": "validate_user",                  // 必填，1-256 字符，无换行
  "path_filter": "src/api/",                   // 可选，repo-relative 子目录
  "glob_filter": "*.py",                       // 可选，文件 glob
  "case_sensitive": false,                     // 默认 false
  "regex": false,                              // 默认 false（substring 优先）
  "max_results": 200,                          // 默认 200，上限 1000
  "context_chars": 60                          // 默认 60，上限 200
}
```

### 5.2 响应（成功）

```jsonc
{
  "status": "ok",
  "data": {
    "umo": "FriendMessage:webchat!astrbot!xxx",
    "worktree": "C:/path/to/repo",
    "pattern": "validate_user",
    "backend": "ripgrep",                       // "ripgrep" | "python"
    "result_count": 12,
    "max_results": 200,
    "truncated": false,
    "elapsed_ms": 48,
    "results": [
      {
        "path": "src/api/auth.py",
        "line": 42,
        "column": 7,
        "snippet": "...def validate_user(token: str) -> bool:..."
      },
      {
        "path": "src/api/auth.py",
        "line": 87,
        "column": 14,
        "snippet": "    if not validate_user(token):\n        raise..."
      }
    ]
  }
}
```

### 5.3 响应（错误）

```jsonc
{
  "status": "ok",
  "data": {
    "umo": "FriendMessage:webchat!astrbot!xxx",
    "worktree": null,
    "pattern": "validate_user",
    "reason": "invalid_pattern",                 // 见 ReasonCode
    "stderr": "",
    "elapsed_ms": 5
  }
}
```

`reason` 取值：

| reason | 含义 |
|---|---|
| `no_project_loaded` | 当前 session 无已加载项目 |
| `worktree_invalid` | worktree 参数非法（不在 worktree 列表内） |
| `directory_missing` | 项目目录不存在 |
| `not_a_git_repo` | 目录不是 git 仓库 |
| `feature_disabled` | feature flag 关闭（理论不会发生，保留兼容） |
| `invalid_pattern` | pattern 为空 / 含换行 / 正则语法错 |
| `pattern_too_long` | pattern 超过 256 字符 |
| `path_unsafe_filter` | path_filter 越界（含 `..` 或绝对路径） |
| `search_timeout` | 5s 超时 |
| `network_error` | 前端 fetch 失败（前端映射，非后端 reason） |

### 5.4 错误响应示例

```jsonc
// 空 pattern
{ "status": "ok", "data": { "reason": "invalid_pattern", "elapsed_ms": 0 } }

// rg 缺失 + Python 兜底也出错（如权限）
{ "status": "ok", "data": { "reason": "search_unavailable", "elapsed_ms": 3200 } }

// path_filter 越界
{ "status": "ok", "data": { "reason": "path_unsafe_filter", "elapsed_ms": 3 } }
```

### 5.5 状态码

- 200：成功或失败（区分在 data.reason）
- 304：不适用（搜索不缓存）
- 5xx：未捕获异常（仅灾难性情况，spec 内不允许）

---

## 6. 配置与部署

### 6.1 配置文件改动

**`_conf_schema.json`**：新增 `search.rg_path` 字段（详见 §3.6）。

**前端**：`localStorage` 加一个 key（详见 §4.5）。

### 6.2 部署

无新增依赖（rg 二进制是可选）。Python 兜底用 stdlib `os.walk` + `re`。

### 6.3 兼容性

- **AstrBot 主项目**：无需改动（`pluginExtensionApi` 已存在）
- **Dashboard**：无破坏性改动
- **已有端点**：无影响
- **i18n**：3 个 locale 各加 key，向后兼容

### 6.4 升级路径

- 用户从 v2.14.x 升级到 v2.15.0（新增 `file-search`）
- 旧 dashboard 调不到新端点：无影响
- 新 dashboard 调旧插件：`POST /spcode/file-search` 返回 404 → 前端 `network_error`

---

## 7. 测试策略

### 7.1 后端单测（`tests/test_file_search.py`）

| # | 用例 | 预期 |
|---|---|---|
| 1 | hit：基础 substring 匹配 | 200, results 中含预期 path/line |
| 2 | miss：无匹配 | 200, results=[] |
| 3 | truncated：结果超 max_results | 200, truncated=true, results.length == max_results |
| 4 | regex：合法正则 | 200, results 中含正确匹配 |
| 5 | regex：非法正则（`[unclosed`） | reason=invalid_pattern |
| 6 | empty pattern | reason=invalid_pattern |
| 7 | pattern 含换行 | reason=invalid_pattern |
| 8 | pattern 超 256 字符 | reason=pattern_too_long |
| 9 | path_filter 越界（`../etc`） | reason=path_unsafe_filter |
| 10 | case_sensitive=true vs false | 命中数与大小写预期一致 |
| 11 | rg_unavailable（mock `plugin._rg_available=False`） | backend=python，结果仍正确 |
| 12 | rg 失败 + 兜底也失败 | reason=search_unavailable |
| 13 | 超时（mock rg 阻塞 6s） | reason=search_timeout |
| 14 | worktree_invalid | reason=worktree_invalid |
| 15 | no_project_loaded | reason=no_project_loaded |
| 16 | glob_filter（`*.py`） | 仅 .py 文件匹配 |
| 17 | binary file 跳过 | 搜索 `.png` 内容不返回二进制 |
| 18 | max_results clamp | 请求 5000 → 实际 max_results=1000 |
| 19 | context_chars | snippet 长度 ≈ context_chars*2 + match_len |
| 20 | 大仓库性能（mock 1k 文件） | elapsed_ms < 5000 |

### 7.2 前端单测

- `useSpcodeFileSearch.ts`：jest/vitest 测：
  - 状态机转换 idle→loading→ok/error
  - 取消正在飞行的请求（AbortController）
  - 空 query → 立即重置为 idle
- `SearchPanel.vue` 测：
  - 输入框 → debounce 300ms → 触发 search
  - Esc 键 → 关闭 + emit update:modelValue
  - 结果点击 → emit open-file

### 7.3 端到端（手动）

- 在 Astrbot repo 上跑：搜 `record_error` → 应返回多个匹配
- 切换 worktree → 搜索范围正确变更
- 卸载 rg → 端点仍可用（变慢，UI 显示 🐢 提示）
- `Cmd-F` 在 sidebar 隐藏时按 → 无反应
- `Cmd-F` 在 Diff 视图按 → 无反应
- 搜 `*`（无 regex 模式）→ 应作字面量搜，不崩溃

---

## 8. 风险与权衡

### 8.1 风险表

| 风险 | 严重度 | 缓解 |
|---|---|---|
| rg 缺失时 Python 兜底太慢，大仓库卡死 | 中 | 5s 超时 + 跳过常见无用目录（`.git` `node_modules` 等） |
| 用户搜的 pattern 在 rg 语法中非法但 mode=substring | 低 | rg `--fixed-strings` 避免 regex 解析 |
| 搜索结果含敏感信息（密码、token） | 中 | 仅在已加载项目内搜（路径防御已就位）；不缓存到 localStorage |
| Cmd-F 抢浏览器原生快捷键 | 中 | 仅 sidebar 可见 + viewMode==='files' 时拦截；其他场景透传 |
| rg 二进制版本差异（老版本不支持 `--json`） | 低 | init 时探测，检测 `--json` flag；不支持则降级 |
| 大仓库首次搜索慢（首次全 walk） | 中 | 仅 Python 路径；rg 路径仅索引无 walk；前端 loading 状态透明 |
| `path_filter` 注入（如 `../../etc`） | 已防御 | `_validate_repo_relative_file` |
| 5s 超时太短/太长 | 中 | P95 < 100ms（rg）P95 < 2s（Python 5k 文件）；5s 是 2x P99 安全裕度 |

### 8.2 权衡决策

- **不做 outline**：tree-sitter / codegraph MCP 太重。搜索能解决 80% 「找代码」需求。
- **不做正则模式 UI 暴露**：v1 默认 substring（`--fixed-strings`）。前端 UI 暂不暴露 regex 开关（虽然 API 支持），避免误用。留给 v2 加 toggle。
- **不做结果二次过滤**：v1 只暴露 pattern。结果排序固定按 path/line。如果用户抱怨，再加 type filter。
- **不做跨 worktree 搜索**：每次只搜当前 worktree（与 sidebar 顶部 worktree 切换同步）。
- **不做 Diff / History 视图搜索**：那些视图有自己专属信息架构，搜索会破坏 focus。

### 8.3 已知限制

- rg 的 `--max-count` 是 per-file 上限，与前端 max_results（per-search）语义不同。若用户搜 1 个文件有 1w 个匹配，rg 会立刻停（5000 个）；需在解析后做 cross-file 截断。
- Python 兜底对超大文件（接近 1MB）逐行 read 在 Windows 上慢（~50MB/s）。但已经按 size 过滤，绝大部分仓库中位文件 < 50KB。
- search 端点不缓存（每次都重搜）。若用户在同一 pattern 上反复搜索，体感会卡。v2 可加 ETag 缓存。

---

## 9. 未来扩展（不在 v1 范围）

| 扩展 | 优先级 | 备注 |
|---|---|---|
| 文件 outline（tree-sitter 或自实现） | 高 | v2，与搜索同 sidebar |
| 搜索结果内嵌 preview 缩略图 | 中 | 点击展开 5 行上下文 |
| 正则/case/glob 模式开关 UI | 中 | API 已支持，缺 UI |
| 搜索历史（localStorage 5 条） | 低 | 简单增强 |
| 跨 worktree 搜索 | 低 | 加 UI toggle |
| Diff / History 视图内搜索 | 低 | 视情况 |
| ETag 缓存（同一 pattern + path_filter） | 低 | 命中即返回 304 |

---

## 10. 变更日志

| 日期 | 作者 | 变更 |
|---|---|---|
| 2026-07-02 | elecvoid243 | 初稿 |
