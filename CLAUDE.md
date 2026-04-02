# AstrBot - Claude Code Guidelines

AstrBot is an open-source, all-in-one Agentic personal and group chat assistant supporting multiple IM platforms (QQ, Telegram, Discord, etc.) and LLM providers.

## Project Overview

- **Main entry**: `astrbot/__main__.py` or via CLI `astrbot run`
- **CLI commands**: `astrbot/cli/commands/`
- **Core modules**: `astrbot/core/`
- **Platform adapters**: `astrbot/core/platform/sources/`
- **Star plugins**: `astrbot/builtin_stars/`
- **Dashboard**: `dashboard/` (Vue.js frontend)

## Development Setup

```bash
# Install dependencies
uv tool install -e . --force

# Initialize AstrBot
astrbot init

# Run development
astrbot run

# Backend only (no WebUI)
astrbot run --backend-only

# Dashboard frontend
cd dashboard && bun dev

# Run tests
uv sync --group dev && uv run pytest --cov=astrbot tests/
```

## Code Style

### Python

1. **Type hints required** - Use Python 3.12+ syntax:
   - `list[str]` not `List[str]`
   - `int | None` not `Optional[int]`
   - Avoid `Any` when possible

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

### Stateful Tool Execution (Session Lifecycle)

Tools can maintain state across conversation turns within a session via `ToolSessionManager`.

**Key classes:**
- `ToolSessionManager` (`astrbot/core/agent/tool_session_manager.py`) — central manager, keyed by `(umo, tool_name)`
- `ToolSessionState` — dict-like per-tool session state with `set_persistent(key)` support
- `FunctionTool.is_stateful` — opt-in flag for stateful tools
- `FunctionTool.get_session_state(umo)` — get/create session state dict

**Usage in a tool:**
```python
@dataclass
class MyTool(FunctionTool):
    is_stateful = True  # declare stateful

    async def call(self, context, **kwargs):
        umo = context.context.event.unified_msg_origin
        state = self.get_session_state(umo)
        state["counter"] = state.get("counter", 0) + 1
        # Mark to survive session clear:
        state.set_persistent("persistent_data")
```

**Architecture flow:**
```
AgentContextWrapper(session_manager=ToolSessionManager())
    → ToolLoopAgentRunner.run_context.session_manager
    → executor.execute(..., session_manager=run_context.session_manager)
    → tool.call(context)  # context.session_manager available
```

## Testing

1. Tests go in `tests/` directory
2. Use `pytest` with `pytest-asyncio`
3. Coverage target: `uv run pytest --cov=astrbot tests/`
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
