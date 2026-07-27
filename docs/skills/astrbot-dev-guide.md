---
name: astrbot-dev-guide
description: Guide for AI assistants developing AstrBot - project conventions, code style, and common patterns
---

# AstrBot Developer Guide

This skill provides guidance for AI assistants working on AstrBot development.

## Project Overview

AstrBot is an open-source, all-in-one Agentic chat assistant supporting multiple IM platforms (QQ, Telegram, Discord, Lark, DingTalk, Slack, etc.) and LLM providers.

- **Main entry**: `astrbot/__main__.py` or CLI `astrbot run`
- **CLI commands**: `astrbot/cli/commands/`
- **Core modules**: `astrbot/core/`
- **Platform adapters**: `astrbot/core/platform/sources/`
- **Star plugins**: `astrbot/builtin_stars/`
- **Dashboard**: `dashboard/` (Vue.js)

## Quick Start Commands

```bash
# Install
uv tool install -e . --force

# Initialize
astrbot init

# Run
astrbot run

# Backend only (no WebUI)
astrbot run --backend-only

# Frontend
cd dashboard && bun dev

# Tests
uv sync --group dev && uv run pytest --cov=astrbot tests/
```

## Code Style Rules

### Type Hints (Required)
Use Python 3.12+ syntax:
- `list[str]` not `List[str]`
- `int | None` not `Optional[int]`
- Avoid `Any` when possible

### Path Handling
Always use `pathlib.Path`:
```python
from pathlib import Path
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
```

### Formatting
Run before every commit:
```bash
ruff format .
ruff check .
```

### Comments
Write all comments in English.

## Environment Variables

When adding new environment variables:

1. Prefix with `ASTRBOT_` (e.g., `ASTRBOT_ENABLE_FEATURE`)
2. Add to `.env.example` with description
3. Update `astrbot/cli/commands/cmd_run.py`:
   - Add to module docstring under "Environment Variables Used in Project"
   - Add to `keys_to_print` list for debug output

## Core Paths Utility

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

## Architecture Patterns

### Adding a Platform Adapter

1. Create in `astrbot/core/platform/sources/`
2. Extend `Platform` base class
3. Use `@register_platform_adapter` decorator
4. Implement: `run()`, `convert_message()`, `meta()`

### Adding a CLI Command

1. Create in `astrbot/cli/commands/`
2. Use `@click.command()`
3. Update `astrbot/cli/__main__.py` to add command

### Adding a Star Handler

1. Create in `astrbot/builtin_stars/` or as plugin
2. Extend `Star` class
3. Use decorators: `@star.on_command()`, `@star.on_schedule()`, etc.

## Testing

- Test location: `tests/` directory
- Framework: `pytest` with `pytest-asyncio`
- Run: `uv run pytest --cov=astrbot tests/`

## Git Conventions

### Commit Messages (Conventional Commits)
```
feat: add new feature
fix: resolve bug
docs: update documentation
refactor: restructure code
test: add tests
chore: maintenance
```

### PR Guidelines
- Title: conventional commit format in English
- Target branch: `dev`
- Keep changes atomic and focused

## Important Guidelines

1. **No report files** - Do not add `xxx_SUMMARY.md`
2. **Componentization** - Keep WebUI code clean, avoid duplication
3. **Backward compatibility** - Add deprecation warnings when changing APIs
4. **CLI help** - Run `astrbot help --all` to see all commands

## Directory Structure

```
astrbot/
├── __main__.py          # Main entry point
├── __init__.py          # Package init, exports
├── cli/                 # CLI commands
│   └── commands/        # Individual commands
├── core/                # Core functionality
│   ├── agent/           # Agent execution
│   ├── platform/        # Platform adapters
│   ├── pipeline/        # Message processing
│   ├── star/            # Plugin system
│   └── config/          # Configuration
├── builtin_stars/       # Built-in plugins
├── dashboard/           # Vue.js frontend
└── utils/              # Utilities
```
