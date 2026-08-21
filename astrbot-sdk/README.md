# AstrBot SDK Vendor Snapshot

This directory is the minimized subtree payload consumed by the AstrBot main
repository.

- `src/astrbot_sdk/` keeps the runtime SDK package plus the minimal testing
  helpers that AstrBot and SDK-generated templates still treat as part of the
  vendored contract
- agent skill templates and embedded markdown reference files are excluded
- root project-note templates for `astr init` stay vendored because the CLI
  still generates `AGENTS.md` / `CLAUDE.md` by default
- `pyproject.toml` keeps the src-layout package discovery but drops dev/test-only metadata
- `VENDORED.md` describes the vendoring contract
- tests, docs, CI files, and other source-repo-only content stay outside this directory
