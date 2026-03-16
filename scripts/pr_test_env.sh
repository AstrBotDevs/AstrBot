#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROFILE="neo"
RUN_SYNC=true
RUN_LINT=true
RUN_SMOKE=true
RUN_DASHBOARD=false

usage() {
  cat <<'EOF'
Usage:
  scripts/pr_test_env.sh [options]

Options:
  --profile <neo|full>  Test profile. Default: neo
  --with-dashboard      Build dashboard before finishing checks
  --no-dashboard        Disable dashboard build (even for full profile)
  --skip-sync           Skip `uv sync`
  --skip-lint           Skip `ruff format --check` and `ruff check`
  --skip-smoke          Skip startup smoke test
  -h, --help            Show this help message

Environment:
  PYTEST_ARGS           Extra args appended to pytest command
EOF
}

while (($# > 0)); do
  case "$1" in
    --profile)
      PROFILE="${2:-}"
      if [[ "$PROFILE" != "neo" && "$PROFILE" != "full" ]]; then
        echo "Unsupported profile: $PROFILE" >&2
        exit 1
      fi
      shift 2
      ;;
    --with-dashboard)
      RUN_DASHBOARD=true
      shift
      ;;
    --skip-sync)
      RUN_SYNC=false
      shift
      ;;
    --skip-lint)
      RUN_LINT=false
      shift
      ;;
    --skip-smoke)
      RUN_SMOKE=false
      shift
      ;;
    --no-dashboard)
      RUN_DASHBOARD=false
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$PROFILE" == "full" && "$RUN_DASHBOARD" == false ]]; then
  RUN_DASHBOARD=true
fi

echo "==> Profile: $PROFILE"
echo "==> Sync dependencies: $RUN_SYNC"
echo "==> Run lint: $RUN_LINT"
echo "==> Run smoke test: $RUN_SMOKE"
echo "==> Build dashboard: $RUN_DASHBOARD"

if [[ "$RUN_SYNC" == true ]]; then
  echo "==> Syncing dependencies with uv"
  uv sync --group dev
fi

echo "==> Preparing test directories"
mkdir -p data/plugins data/config data/temp data/skills
export TESTING="${TESTING:-true}"
export ZHIPU_API_KEY="${ZHIPU_API_KEY:-test-api-key}"

if [[ "$RUN_LINT" == true ]]; then
  echo "==> Running Ruff format check"
  uv run ruff format --check .
  echo "==> Running Ruff lint check"
  uv run ruff check .
fi

echo "==> Running pytest"
if [[ "$PROFILE" == "neo" ]]; then
  NEO_TESTS=(
    "tests/test_neo_skill_sync.py"
    "tests/test_neo_skill_tools.py"
    "tests/test_computer_skill_sync.py"
    "tests/test_skill_manager_sandbox_cache.py"
    "tests/test_dashboard.py::test_neo_skills_routes"
  )
  uv run pytest -q "${NEO_TESTS[@]}" ${PYTEST_ARGS:-}
else
  uv run pytest --cov=. -v -o log_cli=true -o log_level=DEBUG ${PYTEST_ARGS:-}
fi

run_smoke_test() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required for smoke test." >&2
    return 1
  fi

  local smoke_port="6185"
  local smoke_log
  smoke_log="$(mktemp -t astrbot-smoke.XXXXXX.log)"

  echo "==> Starting smoke test on http://localhost:${smoke_port}"
  uv run main.py >"$smoke_log" 2>&1 &
  local app_pid=$!

  for _ in $(seq 1 60); do
    if curl -sf "http://localhost:${smoke_port}" >/dev/null 2>&1; then
      echo "==> Smoke test passed"
      kill "$app_pid" 2>/dev/null || true
      wait "$app_pid" 2>/dev/null || true
      rm -f "$smoke_log"
      return 0
    fi

    if ! kill -0 "$app_pid" 2>/dev/null; then
      echo "AstrBot process exited before becoming healthy." >&2
      tail -n 60 "$smoke_log" || true
      rm -f "$smoke_log"
      return 1
    fi

    sleep 1
  done

  echo "Smoke test failed: health endpoint did not become ready in time." >&2
  tail -n 60 "$smoke_log" || true
  kill "$app_pid" 2>/dev/null || true
  wait "$app_pid" 2>/dev/null || true
  rm -f "$smoke_log"
  return 1
}

if [[ "$RUN_SMOKE" == true ]]; then
  run_smoke_test
fi

if [[ "$RUN_DASHBOARD" == true ]]; then
  if ! command -v pnpm >/dev/null 2>&1; then
    echo "pnpm is required for dashboard build. Install it with: npm install -g pnpm" >&2
    exit 1
  fi
  echo "==> Building dashboard"
  pnpm --dir dashboard install --frozen-lockfile
  pnpm --dir dashboard run build
fi

echo "==> PR checks completed successfully"
