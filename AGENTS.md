## Setup commands

### Core

```
uv tool install -e . --force
astrbot init
astrbot run # start the bot 
astrbot run --backend-only # start the backend only
```

Exposed an API server on `http://localhost:6185` by default.

### Dashboard(WebUI)

```
cd dashboard
bun install # First time only.
bun dev
```

Runs on `http://localhost:3000` by default.

## Pre-commit setup

AstrBot uses [pre-commit](https://pre-commit.com/) hooks to automatically format and lint Python code before each commit. The hooks run `ruff check`, `ruff format`, and `pyupgrade` (see [`.pre-commit-config.yaml`](.pre-commit-config.yaml) for details).

To set it up:

```bash
pip install pre-commit
pre-commit install
```

After installation, the hooks will run automatically on `git commit`. You can also run them manually at any time:

```bash
ruff format .
ruff check .
```

> **Note:** If you use VSCode, install the `Ruff` extension for real-time formatting and linting in the editor.

## Dev environment tips

- **Main entry**: `astrbot/__main__.py` or via CLI `astrbot run`
- **CLI commands**: `astrbot/cli/commands/`
- **Core modules**: `astrbot/core/`
- **Platform adapters**: `astrbot/core/platform/sources/`
- **Star plugins**: `astrbot/builtin_stars/`
- **Dashboard**: `dashboard/` (Vue.js frontend)

## File Organization

```
astrbot/
├── __main__.py          # Main entry point
├── __init__.py          # Package init, exports
├── cli/                 # CLI commands
│   └── commands/        # Individual command modules
├── core/                # Core functionality
│   ├── agent/           # Agent execution
│   ├── platform/        # Platform adapters
│   ├── pipeline/       # Message processing
│   ├── star/           # Plugin system
│   └── config/         # Configuration
├── builtin_stars/       # Built-in plugins
├── dashboard/           # Vue.js frontend
└── utils/              # Utilities
```

## Architecture

### Core Components

- `astrbot/core/` - Core bot functionality
- `astrbot/core/platform/` - Platform adapter system
- `astrbot/core/agent/` - Agent execution logic
- `astrbot/core/star/` - Plugin/Star handler system
- `astrbot/core/pipeline/` - Message processing pipeline
- `astrbot/cli/` - Command-line interface

### Important Utilities

```python
from astrbot.core.utils.astrbot_path import (
    get_astrbot_root,       # AstrBot root directory
    get_astrbot_data_path,  # Data directory
    get_astrbot_config_path, # Config directory
    get_astrbot_plugin_path, # Plugin directory
    get_astrbot_temp_path,   # Temp directory
    get_astrbot_skills_path, # Skills directory
)
```

### Platform Adapters

Platform adapters are in `astrbot/core/platform/sources/`:
- Each adapter extends base platform classes
- Use `@register_platform_adapter` decorator
- Events flow through `commit_event()` to message queue

### Star (Plugin) System

Stars are plugins in `astrbot/builtin_stars/`:
- Extend `Star` base class
- Use decorators for command handlers: `@star.on_command`, `@star.on_message`, etc.
- Access via `context` object

## Code Style

1. **Type hints required** - Use Python 3.12+ syntax:
   - `list[str]` not `List[str]`
   - `int | None` not `Optional[int]`
   - Avoid `Any` when possible. Use proper `TypedDict`, `dataclass`, or `Protocol` instead.
   - When encountering dict access issues (e.g., `msg.get("key")` where type inference is wrong), define a `TypedDict` with `total=False` to explicitly declare allowed keys.

   Good example:
   ```python
   class MessageComponent(TypedDict, total=False):
       type: str
       text: str
       path: str
   ```

   Bad example (avoid):
   ```python
   msg: Any = something
   msg = cast(dict, msg)
   ```

2. **Path handling** - Always use `pathlib.Path`:
   ```python
   from pathlib import Path
   # Use astrbot.core.utils.path_utils for data/temp directories
   from astrbot.core.utils.path_utils import get_astrbot_data_path
   ```

3. **Formatting** - Run before committing:
   ```bash
   ruff format .
   ruff check .
   ```

4. **Comments and logs** - Use English for all comments, docstrings, and log messages

5. **Imports** - Use absolute imports via `astrbot.` prefix

### Environment Variables

When adding new environment variables:

1. Use `ASTRBOT_` prefix: `ASTRBOT_ENABLE_FEATURE`
2. Add to `.env.example` with description
3. Update `astrbot/cli/commands/cmd_run.py`:
   - Add to module docstring under "Environment Variables Used in Project"
   - Add to `keys_to_print` list for debug output

## Testing

1. Tests go in `tests/` directory
2. Use `pytest` with `pytest-asyncio`
3. Run: `uv sync --group dev && uv run pytest --cov=astrbot tests/`
4. Test files: `test_*.py` or `*_test.py`

### Code Quality Scoring Test

The project enforces two independent source-quality gates in `tests/test_code_quality_typing.py`: the legacy score must be at least **80/100**, and V2 debt must be at most **200 integer units**. Both require a complete scan. These diagnostics supplement the blocking lint, static type checks, and behavioral tests; a passing custom score does not replace those checks.

**Run the gate and scanner regression tests:**

```bash
uv run pytest tests/test_code_quality_typing.py tests/test_quality_scanner.py -v
```

**Counts and clone extent:**

- `C`: resolved calls to `typing.cast(typing.Any, ...)`, including supported aliases.
- `I`: all actual `# type: ignore` comment directives.
- `B`: the subset of `I` containing a discouraged code, such as `unresolved-import`, `class-alias`, or `attr-defined`. Thus `0 <= B <= I`; a directive with several such codes is counted once.
- `E`: bare exception handlers without an exception type.
- `D`: additional non-overlapping copies of the exact clone blocks selected by the scanner.
- `k`: eligible executable AST statements in one selected clone, including eligible statements inside its compound statements. Imports, definition wrappers, docstrings, literal data declarations, and formatting do not contribute.
- `R = sum(extra_copies * max(5, k))` over the selected clone groups.
- `N`: eligible executable AST statements in fully scanned source files, counted once each across all scopes.

Clone matching retains its existing requirement of at least five distinct source lines that start eligible executable statements. Because those lines come from the same statement nodes used for `k`, admitted clones have `k >= 5`. The explicit `max(5, k)` floor preserves at least two debt points per extra copy even if the counting convention is revised later. A nested statement is counted once per clone; previously covered copies can anchor a shorter new match without being charged again. Names and literal values remain significant. Statement counting changes the cost of accepted clones, not the matching or five-line admission rule.

**V2 debt and score:**

```text
U = 10*C + 5*(I-B) + 35*B + 20*E + 4*R
debt = U / 10
score_v2 = 80000 / (800 + U)
PASS requires U <= 200
```

`U` is an integer, so the gate uses an exact comparison. The displayed score is 100 for zero debt and exactly 80 at `U = 200`; `U = 201` fails even if a rounded display reads 80. The smooth score remains informative beyond the failure threshold, while the raw debt identifies how much must be removed.

| Pattern | V2 debt cost |
|---------|--------------|
| `cast(Any, ...)` | 1 point each |
| Ordinary type-ignore directive (`I-B`) | 0.5 points each |
| Discouraged type-ignore directive (`B`) | 3.5 points total each |
| Bare exception handler | 2 points each |
| Extra exact clone | 0.4 points per eligible AST statement, with a 2-point minimum |

The ignore costs retain the legacy total: a discouraged directive previously paid 0.5 plus 3 points. V2 makes that subset relationship explicit. Bare handlers receive a larger cost because their unqualified catch hides exception categories. Clone cost increases with duplicated executable extent, so one long copied block no longer receives the same cost as a five-statement block. These weights and thresholds are fixed policy, independent of the current candidate's results.

`density = 1000 * debt / N` is reported only as a diagnostic. It is never a divisor for the debt or either gate. Adding unrelated clean code can reduce density but cannot improve the score or turn failure into success.

**Legacy gate, preserved unchanged:**

```text
legacy_score = max(0, 100 - C - 0.5*I - 3*B - 0.5*E - 2*D)
PASS also requires legacy_score >= 80
```

V2 debt is at least the unclamped legacy debt: existing cast/ignore costs are preserved, bare-handler cost increases, and every extra clone still costs at least two points. The legacy assertion remains independent so future changes cannot silently remove that constraint.

**Coverage and invalid scans:**

Reports include discovered, read, AST-parsed, and tokenized file counts plus `N`. Missing or empty source trees, zero executable statements, directory discovery failures, unreadable files, parse failures, and tokenization failures produce **INVALID**, with `score_v2 = None`, and fail the gate. A clean readable subset cannot stand in for the whole tree. Negative, non-integer, and impossible counts are rejected. No files or error categories may be excluded merely to improve a result.

**Agent rules when modifying code:**

1. Fix missing imports, incorrect aliases, and attribute errors instead of adding discouraged type-ignore directives.
2. Use accurate types instead of `cast(Any, ...)` to suppress errors.
3. Catch the specific exception categories the operation can handle.
4. Extract reusable logic when an exact executable block is duplicated.
5. Before committing, require complete coverage, `U <= 200`, the independent legacy score of at least 80, and the other blocking project checks.

## Git Conventions

### Commit Messages

Use conventional commits:
```
feat: add new feature
fix: resolve bug
docs: update documentation
refactor: restructure code
test: add tests
chore: maintenance tasks
```

### PR Guidelines

1. Title: conventional commit format
2. Description: English
3. Target branch: `dev`
4. Keep changes focused and atomic

## Project-Specific Guidelines

1. **No report files** - Do not add `xxx_SUMMARY.md` or similar
2. **Componentization** - Maintain clean code, avoid duplication in WebUI
3. **Backward compatibility** - When deprecating, add warnings
4. **CLI help** - Run `astrbot help --all` to see all commands
5. When modifying frontend/dashboard code, use the project's custom request module `@/utils/request` for HTTP calls
6. For fetch or SSE URLs, use `resolveApiUrl('/api/your-path')` so the configured `VITE_API_BASE` and dev proxy rules are respected
7. Do not import the plain `axios` package directly in dashboard source files
8. When backend API routes, request/response schemas, or OpenAPI definitions change, regenerate the frontend API client with `cd dashboard && pnpm generate:api`
9. Keep `[project].version` in `pyproject.toml` and `__version__` in `astrbot/__init__.py` in sync; `VERSION` in `astrbot/core/config/default.py` must derive from `astrbot.__version__` rather than hardcoding a separate value
10. For WebUI dialogs, use `text-h3 pa-4 pb-0 pl-6` as the base title class and use `variant="text"` or `variant="tonal"` for dialog buttons
11. Consider Windows, macOS, and Linux behavior on both Arm64 and x86 architectures, and preserve compatibility with Python 3.12+

12. When changing WebUI navigation, page structure, or terminology, update the affected instructions and screenshots in `docs/zh` and `docs/en` in the same PR. Include an old-to-new mapping for renamed, moved, or merged entry points in the relevant docs and changelog. See `CONTRIBUTING.md` for the review checklist.

## Common Tasks

### Adding a new platform adapter
1. Create adapter in `astrbot/core/platform/sources/`
2. Extend `Platform` base class
3. Use `@register_platform_adapter` decorator
4. Implement required methods: `run()`, `convert_message()`, `meta()`

### Adding a new command
1. Add to appropriate module in `cli/commands/`
2. Register with `@click.command()`
3. Update `astrbot/cli/__main__.py` to add command

### Adding a new Star handler
1. Create in `astrbot/builtin_stars/` or as plugin
2. Extend `Star` class
3. Use decorators: `@star.on_command()`, `@star.on_schedule()`, etc.

## Release versions

1. Replace current version name to specific version name.
2. Write changelog in `changelogs/`, you can refer to the full commit messages between the latest tag to the latest commit.
3. Make and push a commit into master branch with message format like: `chore: bump version to 4.25.0`
4. Create a tag and push the tag. For example: `git tag v4.25.0 && git push origin v4.25.0`
