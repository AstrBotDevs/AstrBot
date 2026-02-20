# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AstrBot is a multi-platform LLM chatbot and development framework written in Python with a Vue.js dashboard. It supports QQ, Telegram, Discord, WeChat Work, Feishu, DingTalk, Slack, and more messaging platforms, with integration for OpenAI, Anthropic, Gemini, DeepSeek, and other LLM providers.

## Development Setup

### Core (Python 3.10+)

```bash
# Install dependencies using uv
uv sync

# Run the application
uv run main.py
```

The application starts an API server on `http://localhost:6185` by default.

### Dashboard (Vue.js)

```bash
cd dashboard
pnpm install    # First time setup
pnpm dev        # Development server on http://localhost:3000
pnpm build      # Production build
```

## Code Quality

Before committing, always run:

```bash
uv run ruff format .
uv run ruff check .
```

## Project Architecture

### Core Components (`astrbot/core/`)

- **AstrBotCoreLifecycle** (`core_lifecycle.py`): Main entry point that initializes all components
- **PlatformManager** (`platform/manager.py`): Manages messaging platform adapters (QQ, Telegram, etc.)
- **ProviderManager** (`provider/manager.py`): Manages LLM providers (OpenAI, Anthropic, Gemini, etc.)
- **PluginManager** (`star/`): Plugin system - plugins are called "Stars"
- **PipelineScheduler** (`pipeline/`): Message processing pipeline
- **ConversationManager** (`conversation_mgr.py`): Manages conversation contexts
- **AstrMainAgent** (`astr_main_agent.py`): Core AI agent implementation with tool execution

### API Layer (`astrbot/api/`)

Public API for plugin development. Key exports:
- `register`, `command`, `llm_tool`, `regex`: Plugin registration decorators
- `AstrMessageEvent`, `Platform`, `Provider`: Core abstractions
- `MessageEventResult`, `MessageChain`: Response types

### Plugin System (Stars)

Plugins are located in:
- `astrbot/builtin_stars/`: Built-in plugins (builtin_commands, web_searcher, session_controller)
- `data/plugins/`: User-installed plugins

Plugin handlers are registered via decorators in `astrbot/core/star/register/`:
- `register_star`: Register a plugin class
- `register_command`: Command handler
- `register_llm_tool`: LLM function tool
- `register_on_llm_request/response`: LLM lifecycle hooks
- `register_on_platform_loaded`: Platform initialization hook

### Platform Adapters (`astrbot/core/platform/sources/`)

Each messaging platform has an adapter implementing `Platform`:
- `qq/`: QQ protocol (via NapCat/OneBot)
- `telegram/`, `discord/`, `slack/`, `wechat/`, `wecom/`, `feishu/`, `dingtalk/`

### LLM Providers (`astrbot/core/provider/sources/`)

Provider implementations for different LLM services:
- `openai_source.py`: OpenAI and compatible APIs
- `anthropic_source.py`: Claude API
- `gemini_source.py`: Google Gemini
- Various TTS/STT providers

## Path Conventions

Use `pathlib.Path` and utilities from `astrbot.core.utils.astrbot_path`:
- `get_astrbot_root()`: Project root
- `get_astrbot_data_path()`: Data directory (`data/`)
- `get_astrbot_config_path()`: Config directory (`data/config/`)
- `get_astrbot_plugin_path()`: Plugin directory (`data/plugins/`)
- `get_astrbot_temp_path()`: Temp directory (`data/temp/`)

## Testing

```bash
# Set up test environment
mkdir -p data/plugins data/config data/temp
export TESTING=true

# Run tests
pytest --cov=. -v
```

## Branch Naming Conventions

- Bug fixes: `fix/1234` or `fix/1234-description`
- New features: `feat/description`

## Commit Message Format

Use conventional commit prefixes: `fix:`, `feat:`, `docs:`, `style:`, `refactor:`, `test:`, `chore:`

## Additional Guidelines

- Use English for all new comments and PR descriptions
- Maintain componentization in Dashboard/WebUI code
- Do not add report files (e.g., `*_SUMMARY.md`)
