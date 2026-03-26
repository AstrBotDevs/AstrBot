# Vendored Snapshot Notes

This directory is a minimized snapshot for the AstrBot main repository to import
via `git subtree`.

- The source of truth is this `astrbot-sdk` repository.
- `vendor/src/astrbot_sdk/` is synchronized from `src/astrbot_sdk/`, but only for
  the runtime SDK subset consumed by AstrBot.
- vendored snapshots exclude testing helpers, developer skill templates, and
  markdown reference assets that are not needed at runtime.
- `vendor/pyproject.toml` keeps src-layout package discovery, but strips
  test/dev-only sections so the subtree stays runtime-focused.
- Do not edit vendored files directly inside the AstrBot main repository.
- Tests and documentation remain only in the SDK source repository and are not
  copied into the vendored snapshot.
- If the vendored copy needs changes, update the SDK source repository first and
  regenerate the `vendor/` snapshot.
