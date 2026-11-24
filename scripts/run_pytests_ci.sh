#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export TESTING="${TESTING:-true}"
export ASTRBOT_TEST_MODE="true"

PYTEST_TARGETS=("$@")
if ((${#PYTEST_TARGETS[@]} == 0)); then
  PYTEST_TARGETS=(./tests)
fi

echo "[ci] running tests: ${PYTEST_TARGETS[*]}"
exec uv run --group dev python -m pytest \
  --durations=20 \
  -W error::pytest.PytestUnhandledThreadExceptionWarning \
  "${PYTEST_TARGETS[@]}"
