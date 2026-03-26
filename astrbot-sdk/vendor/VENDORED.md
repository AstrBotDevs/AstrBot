# Vendored Snapshot Notes

This directory is a minimized snapshot for the AstrBot main repository to import
via `git subtree`.

- The source of truth is this `astrbot-sdk` repository.
- `vendor/src/astrbot_sdk/` is synchronized from `src/astrbot_sdk/`.
- `vendor/pyproject.toml` is copied from the root so the vendored branch keeps
  the same src-layout packaging metadata.
- Do not edit vendored files directly inside the AstrBot main repository.
- Tests and documentation remain only in the SDK source repository and are not
  copied into the vendored snapshot.
- If the vendored copy needs changes, update the SDK source repository first and
  regenerate the `vendor/` snapshot.
