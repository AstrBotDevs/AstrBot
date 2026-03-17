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

## Dev environment tips

1. When modifying the WebUI, be sure to maintain componentization and clean code. Avoid duplicate code.
2. Do not add any report files such as xxx_SUMMARY.md.
3. After finishing, use `ruff format .` and `ruff check .` to format and check the code.
4. When committing, ensure to use conventional commits messages, such as `feat: add new agent for data analysis` or `fix: resolve bug in provider manager`.
5. Use English for all new comments.
6. For path handling, use `pathlib.Path` instead of string paths, and use `astrbot.core.utils.path_utils` to get the AstrBot data and temp directory.
7. Use Python 3.12+ type hinting syntax (e.g., `list[str]` over `List[str]`, `int | None` over `Optional[int]`). Avoid using `Any` and ensure comprehensive type annotations are provided.


## PR instructions

1. Title format: use conventional commit messages
2. Use English to write PR title and descriptions.
