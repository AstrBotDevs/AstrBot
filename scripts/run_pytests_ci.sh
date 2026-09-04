#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ASTRBOT_TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$ASTRBOT_TEST_ROOT"' EXIT

export TESTING="true"
export ASTRBOT_TEST_MODE="true"
export ASTRBOT_ROOT="$ASTRBOT_TEST_ROOT"

# Keep backward compatibility with existing test code that reads ZHIPU_API_KEY.
if [[ -n "${OPENAI_API_KEY:-}" && -z "${ZHIPU_API_KEY:-}" ]]; then
  export ZHIPU_API_KEY="$OPENAI_API_KEY"
fi

PYTEST_TARGETS=("${@:-./tests}")

echo "[ci] syncing dependencies with uv"
uv sync --locked --group dev

echo "[ci] running tests: ${PYTEST_TARGETS[*]}"
uv run pytest "${PYTEST_TARGETS[@]}"
