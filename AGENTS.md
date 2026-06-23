## Setup commands

### Core

```
uv sync
uv run main.py
```

Exposed an API server on `http://localhost:6185` by default.

### Dashboard(WebUI)

```
cd dashboard
pnpm install # First time only. Use npm install -g pnpm if pnpm is not installed.
pnpm dev
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

### Basic

1. When modifying the WebUI, be sure to maintain componentization and clean code. Avoid duplicate code.
2. Do not add any report files such as xxx_SUMMARY.md.
3. After finishing, use `ruff format .` and `ruff check .` to format and check the code.
4. When committing, ensure to use conventional commits messages, such as `feat: add new agent for data analysis` or `fix: resolve bug in provider manager`.
5. Use English for all new comments.
6. For path handling, use `pathlib.Path` instead of string paths, and use `astrbot.core.utils.path_utils` to get the AstrBot data and temp directory.
7. When backend API routes, request/response schemas, or OpenAPI definitions change, regenerate the frontend API client by running `cd dashboard && pnpm generate:api`.
8. When updating the project version, keep `[project].version` in `pyproject.toml` and `__version__` in `astrbot/__init__.py` in sync. `VERSION` in `astrbot/core/config/default.py` should derive from `astrbot.__version__` instead of hardcoding a separate version string.

### KISS and First Principles

Follow the KISS principle and reason from first principles during development. Start by identifying the real problem, required behavior, and smallest useful change before adding code. Do not pile on features, configuration switches, abstractions, dependencies, or compatibility layers unless they directly solve the current problem and have clear evidence of need.

Prefer the simplest implementation that is correct, maintainable, and consistent with the existing codebase. If a broader design seems attractive, reduce it to the essential behavior needed now and leave optional expansion for a later, explicit requirement.

### No Unnecessary Helpers

Prioritize inline implementation over abstraction. Avoid over-engineering and do not create helper functions unless absolutely necessary.

1. **Inline-First Rule**: If a logic block can be implemented directly within the main function without breaking overall readability, **do not** extract it into a new helper function.
2. **Strict Justification for Helpers**: You may only create a separate helper function if it meets at least one of these criteria:
   - **High Reuse**: The exact same logic is repeated across **3 or more** different locations.
   - **Extreme Complexity**: Inlining the logic makes the main function too long (e.g., >50 lines) or severely derails the main execution flow.
3. **No Fragmentation**: Do not split continuous linear logic (e.g., a single API call, simple form validation, or one-time data formatting) into tiny functions just for the sake of "clean code."
4. **Keep Context Compact**: Handle edge cases, error catching, and logging directly inside the main function block instead of offloading them.
5. **Refactoring Constraint**: When modifying existing code, do not alter the current function structure or extract code into new helpers unless the existing code already violates the complexity or reuse rules above.

### Mandatory Google-Style Docstrings
* **Comment the complex**: Add clear comments to any non-obvious function, method, or parameter.
* **Google Format**: All docstrings must strictly use the Google format (`Args:`, `Returns:`, `Raises:`).

#### Example:

```py
def calculate_metrics(user_id: int, force_refresh: bool = False) -> dict:
    """Brief description of the function.

    Args:
        user_id: Description of the ID.
        force_refresh: Description of the flag.

    Returns:
        Description of the returned dict.

    Raises:
        ValueError: Description of when this occurs.
    """
    # Inline implementation here...
```


## PR instructions

1. Title format: use conventional commit messages
2. Use English to write PR title and descriptions.

## Release versions

Use a short-lived `release/*` branch for each release. The release branch is the stabilization area for version bumps, changelog updates, release-blocking fixes, and final validation only. Do not add unrelated features or broad refactors to a release branch.

Prepare a release from a clean worktree with:

```bash
uv run python scripts/prepare_release.py 4.25.0
```

The script updates `pyproject.toml` and `astrbot/__init__.py`, creates `changelogs/v4.25.0.md`, runs the required Python checks, and prints the remaining steps. Use these flags when needed:

```bash
uv run python scripts/prepare_release.py 4.25.0 --generate-api-client
uv run python scripts/prepare_release.py 4.25.0 --dashboard-build
uv run python scripts/prepare_release.py 4.25.0 --commit --push
```

Open a PR from `release/4.25.0` to `master`. The PR title must use the conventional commit format, for example `chore: bump version to 4.25.0`. After the release PR is merged, create and push the tag from the updated `master` branch so the tag points to the exact code that was merged:

```bash
git checkout master
git pull --ff-only origin master
git tag v4.25.0
git push origin v4.25.0
```

For one-off release candidate branches, delete the release branch after the tag is pushed and verified. For maintained release lines, use a branch such as `release/4.25` and keep it until that line reaches EOL.

```bash
git branch -d release/4.25.0
git push origin --delete release/4.25.0
```
