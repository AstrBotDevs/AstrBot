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

1. Replace current version name to specific version name.
2. Write changelog in `changelogs/`, you can refer to the full commit messages between the latest tag to the latest commit.
3. Make and push a commit into master branch with message format like: `chore: bump version to 4.25.0`
4. Create a tag and push the tag. For example: `git tag v4.25.0 && git push origin v4.25.0`
