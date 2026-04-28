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

## Project Overview

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

4. **Comments** - Use English for all comments and docstrings

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

The project enforces a **code quality score** via `tests/test_code_quality_typing.py`. All agents must treat this as a hard constraint when modifying code.

**Run the test:**
```bash
uv run pytest tests/test_code_quality_typing.py -v
```

**Scoring rules (target: 100/100, threshold for PASS: 80/100):**

| Pattern | Cost |
|---------|------|
| `cast(Any, ...)` | -1 pt each |
| `# type: ignore` | -0.5 pt each |
| **BAD** `# type: ignore[...]` (unresolved-import, class-alias, no-name-module, attr-defined, etc.) | **-3 pt each** |
| `bare except:` (no exception type) | -0.5 pt each |
| Duplicate code block (5+ identical lines, ≥2 occurrences) | -2 pt each |

**Why bad type: ignore is heavily penalized:**
- `# type: ignore[unresolved-import]` — hides missing module/stub issues
- `# type: ignore[class-alias]` — hides improper type alias patterns
- `# type: ignore[attr-defined]` — hides missing attribute errors
- These are **workarounds, not fixes** — they paper over real type errors

**Scoring formula:**
```
score = max(0, 100 - cast_any - type_ignore*0.5 - bad_type_ignore*3 - bare_except*0.5 - dup_blocks*2)
```

**Agent rules when modifying code:**
1. **Do not add** `# type: ignore[unresolved-import]` or `# type: ignore[class-alias]` — fix the underlying issue instead
2. **Do not use** `cast(Any, ...)` to suppress type errors — use proper type annotations
3. **Do not add** bare `except:` clauses — use `except SomeSpecificException:`
4. **Do not copy-paste** 5+ line blocks — extract to a shared helper function
5. Before committing, run the scoring test and ensure score ≥ 80

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
