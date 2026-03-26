# AstrBot SDK Vendor Snapshot

This directory is the minimized subtree payload consumed by the AstrBot main
repository.

- `src/astrbot_sdk/` keeps only the runtime SDK package contents required by AstrBot
- testing helpers, developer templates, and embedded markdown reference files are excluded
- `pyproject.toml` keeps the src-layout package discovery but drops dev/test-only metadata
- `VENDORED.md` describes the vendoring contract
- tests, docs, CI files, and other source-repo-only content stay outside this directory
