# AstrBot Development Instructions

AstrBot is a multi-platform LLM chatbot and development framework written in Python with a Vue.js dashboard. It supports multiple messaging platforms (QQ, Telegram, Discord, etc.) and various LLM providers (OpenAI, Anthropic, Google Gemini, etc.).

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

### Bootstrap and Install Dependencies
- **Python 3.10+ required** - Check `.python-version` file
- Install UV package manager: `pip install uv`
- Install project dependencies: `uv sync` -- takes 6-7 minutes. NEVER CANCEL. Set timeout to 10+ minutes.
- Create required directories: `mkdir -p data/plugins data/config data/temp`

### Running the Application
- Run main application: `uv run main.py` -- starts in ~3 seconds
- Application creates WebUI on http://localhost:6185 (default credentials: `astrbot`/`astrbot`)
- Dashboard download may fail with "division by zero" error -- this is a known issue, application still works
- Application loads plugins automatically from `packages/` and `data/plugins/` directories

### CLI Tools
- **CAREFUL**: CLI commands require user input and may hang waiting for input
- Check CLI help: `uvx astrbot --help` -- takes 1-2 minutes on first run to download dependencies. NEVER CANCEL.
- Initialize new project: `uvx astrbot init` -- will prompt for confirmation of directory
- CLI resolves dependencies automatically but can be slow on first run

### Dashboard Build (Vue.js/Node.js)
- **Prerequisites**: Node.js 20+ and npm 10+ required
- Navigate to dashboard: `cd dashboard`
- Install dashboard dependencies: `npm install` -- takes 2-3 minutes. NEVER CANCEL. Set timeout to 5+ minutes.
- Build dashboard: `npm run build` -- takes 25-30 seconds. NEVER CANCEL.
- Dashboard creates optimized production build in `dashboard/dist/`

### Testing
- Install test dependencies: `uv add --dev pytest pytest-asyncio pytest-cov`
- Set up test environment: `export TESTING=true`
- Run tests: `uv run pytest --cov=. -v` -- takes 5-10 seconds
- **Expected Results**: Some tests may fail due to missing API keys or configuration - this is normal
- Tests create coverage report showing ~36% code coverage

### Code Quality and Linting
- Install ruff linter: `uv add --dev ruff`
- Check code style: `uv run ruff check .` -- takes <1 second
- Check formatting: `uv run ruff format --check .` -- takes <1 second
- Fix formatting: `uv run ruff format .`
- **ALWAYS** run `uv run ruff check .` and `uv run ruff format .` before committing changes

## Validation and Testing

### Manual Application Testing
- Start application with `uv run main.py`
- Verify WebUI loads at http://localhost:6185
- Check logs for successful plugin loading (python_interpreter, web_searcher, etc.)
- Application should show "AstrBot 启动完成" (startup complete) message
- Verify no critical errors in startup logs (warnings about dashboard download are expected)

### File Structure Verification
After running application, verify these directories exist:
```
data/
├── config/           # Configuration files
├── plugins/          # Plugin data
├── temp/            # Temporary files
├── py_interpreter_shared/
├── py_interpreter_workplace/
├── webchat/
├── cmd_config.json
├── data_v3.db      # SQLite database
└── shared_preferences.json
```

## Common Tasks and Timing Expectations

### Build and Dependency Installation Times
- **NEVER CANCEL** any of these operations. Wait for completion.
- `uv sync`: 6-7 minutes (Python dependencies)
- `npm install` (dashboard): 2-3 minutes  
- `npm run build` (dashboard): 25-30 seconds
- `uvx astrbot --help` (first run): 1-2 minutes
- Application startup: ~3 seconds
- Test suite: 5-10 seconds
- Ruff linting: <1 second

### Development Workflow
1. Install dependencies: `uv sync` (6-7 minutes)
2. Run tests: `uv run pytest --cov=. -v` (5-10 seconds)
3. Check code style: `uv run ruff check .` (<1 second)
4. Format code: `uv run ruff format .` (<1 second)
5. Run application: `uv run main.py` (starts in 3 seconds)
6. Build dashboard if needed: `cd dashboard && npm run build` (25-30 seconds)

### Key Configuration Files
- `pyproject.toml` - Python project configuration and dependencies
- `uv.lock` - Locked dependency versions
- `requirements.txt` - Legacy pip requirements (use UV instead)
- `dashboard/package.json` - Node.js dashboard dependencies
- `.pre-commit-config.yaml` - Pre-commit hooks configuration
- `data/cmd_config.json` - Application configuration (created on first run)

## Project Structure and Important Locations

### Core Codebase
- `astrbot/` - Main Python package
  - `core/` - Core framework functionality
  - `api/` - API endpoints
  - `cli/` - Command-line interface
  - `dashboard/` - Dashboard backend integration
- `dashboard/` - Vue.js frontend application
- `packages/` - Built-in plugins (python_interpreter, web_searcher, etc.)
- `tests/` - Test suite
- `main.py` - Application entry point

### Plugin Development
- Plugins load from `packages/` (built-in) and `data/plugins/` (user-installed)
- Plugin system supports function tools and message handlers
- Key plugins: python_interpreter, web_searcher, astrbot, reminder, session_controller

### Common Issues and Workarounds
- **Dashboard download fails**: Known issue with "division by zero" error - application still works
- **Test failures**: Some tests require API keys or specific configuration - focus on tests that pass
- **Import errors in tests**: Ensure `uv run` is used to run tests in proper environment
- **CLI hangs**: CLI commands often require user input - use with caution
- **Build timeouts**: Always set appropriate timeouts (10+ minutes for uv sync, 5+ minutes for npm install)

## CI/CD Integration
- GitHub Actions workflows in `.github/workflows/`
- Coverage testing: runs `pytest --cov=. -v` with 36% expected coverage
- Dashboard CI: builds frontend with `npm install && npm run build`
- Docker builds supported via `Dockerfile`
- Pre-commit hooks enforce ruff formatting and linting

## Docker Support
- Primary deployment method: `docker run soulter/astrbot:latest`
- Compose file available: `compose.yml`
- Exposes ports: 6185 (WebUI), 6195 (WeChat), 6199 (QQ), etc.
- Volume mount required: `./data:/AstrBot/data`

## Multi-language Support
- Documentation in Chinese (README.md), English (README_en.md), Japanese (README_ja.md)
- UI supports internationalization
- Default language is Chinese

Remember: This is a production chatbot framework with real users. Always test thoroughly and ensure changes don't break existing functionality.