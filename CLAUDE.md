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

## Testing

1. Tests go in `tests/` directory
2. Use `pytest` with `pytest-asyncio`
3. Coverage target: `uv run pytest --cov=astrbot tests/`
4. Test files: `test_*.py` or `*_test.py`

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
