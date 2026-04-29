# Vendored Snapshot Notes

This directory is a minimized snapshot for the AstrBot main repository to import
via `git subtree`.

- The source of truth is this `astrbot-sdk` repository.
- `vendor/src/astrbot_sdk/` is synchronized from `src/astrbot_sdk/`.
- Vendored snapshots keep the runtime SDK plus the minimal testing helpers
  (`testing.py`, `_testing_support.py`, `_internal/testing_support.py`) because
  AstrBot and SDK-generated test templates still depend on them.
- Vendored snapshots retain the default `AGENTS.md` / `CLAUDE.md` project-note
  templates and the minimal `astrbot-plugin-dev` skill scaffold used by
  `astr init --agents`, but still exclude larger markdown reference assets that
  are not needed by the subtree consumer.
- `vendor/pyproject.toml` keeps src-layout package discovery, but strips
  test/dev-only sections so the subtree stays runtime-focused.
- Do not edit vendored files directly inside the AstrBot main repository.
- Tests and broader documentation remain only in the SDK source repository.
  The vendored snapshot only keeps the runtime-facing templates required by
  `astr init`.
- If the vendored copy needs changes, update the SDK source repository first and
  regenerate the `vendor/` snapshot.
