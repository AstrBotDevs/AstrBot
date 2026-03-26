# Vendored Snapshot Notes

This directory is a minimized snapshot for the AstrBot main repository to import
via `git subtree`.

- The source of truth is this `astrbot-sdk` repository.
- `vendor/src/astrbot_sdk/` is synchronized from `src/astrbot_sdk/`.
- Vendored snapshots keep the runtime SDK plus the minimal testing helpers
  (`testing.py`, `_testing_support.py`, `_internal/testing_support.py`) because
  AstrBot and SDK-generated test templates still depend on them.
- Vendored snapshots exclude agent skill templates and markdown reference
  assets that are not needed by the subtree consumer, but retain the default
  `AGENTS.md` / `CLAUDE.md` project-note templates used by `astr init`.
- `vendor/pyproject.toml` keeps src-layout package discovery, but strips
  test/dev-only sections so the subtree stays runtime-focused.
- Do not edit vendored files directly inside the AstrBot main repository.
- Tests and documentation remain only in the SDK source repository and are not
  copied into the vendored snapshot.
- If the vendored copy needs changes, update the SDK source repository first and
  regenerate the `vendor/` snapshot.
