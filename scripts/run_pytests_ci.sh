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

PYTEST_TARGETS=("$@")

echo "[ci] syncing dependencies with uv"
uv sync --group dev --locked

if ((${#PYTEST_TARGETS[@]} > 0)); then
  echo "[ci] running tests: ${PYTEST_TARGETS[*]}"
else
  echo "[ci] running tests: <pytest testpaths>"
fi
uv run pytest "${PYTEST_TARGETS[@]}"
