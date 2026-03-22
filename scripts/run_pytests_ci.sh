#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p ./data/plugins ./data/config ./data/temp

export TESTING="${TESTING:-true}"

# Keep backward compatibility with existing test code that reads ZHIPU_API_KEY.
if [[ -n "${OPENAI_API_KEY:-}" && -z "${ZHIPU_API_KEY:-}" ]]; then
  export ZHIPU_API_KEY="$OPENAI_API_KEY"
fi

PYTEST_TARGETS=("${@:-./tests}")

 echo "[ci] syncing dependencies with uv"
uv sync --dev

echo "[ci] running tests: ${PYTEST_TARGETS[*]}"
# Some tests may leave non-daemon worker threads alive (e.g. aiosqlite warning path),
# which can block pytest process exit in CI. Run pytest via python and force process exit
# with pytest's return code to avoid hanging workflow jobs.
uv run python - "${PYTEST_TARGETS[@]}" <<'PY'
import os
import sys

import pytest

exit_code = int(pytest.main(sys.argv[1:]))
sys.stdout.flush()
sys.stderr.flush()
os._exit(exit_code)
PY
