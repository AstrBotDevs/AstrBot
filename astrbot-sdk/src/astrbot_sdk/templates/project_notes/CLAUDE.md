# CLAUDE.md

## AstrBot Plugin Notes

- Prefer raising `AstrBotError` from `astrbot_sdk.errors` for expected failures.
- Reuse stable `ErrorCodes` and factory helpers instead of inventing ad-hoc `{"error": ...}` payloads.
- Validate the generated plugin with `astrbot-sdk validate --plugin-dir .` before packaging or sharing it.
- Run `python -m pytest tests/test_plugin.py -v` after changing plugin behavior so the sample harness contract stays honest.
- `astrbot-sdk build --plugin-dir .` should create the release zip without development-only files such as `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.agents/`, or `.opencode/`.
- Exported capabilities should use `<plugin_id>.<action>`, and HTTP routes should use `/{plugin_id}` or `/{plugin_id}/...` so the plugin stays collision-safe inside `GroupWorkerRuntime`.

- 除非有充分理由，插件的直接依赖应声明已验证的最低兼容版本。若已知存在不兼容的大版本或问题版本，应同时补充上界或排除约束
