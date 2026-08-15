#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROFILE="neo"
RUN_SYNC=true
RUN_LINT=true
RUN_QUALITY=false
RUN_SMOKE=true
RUN_DASHBOARD=false
DASHBOARD_MODE="auto"

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
  --with-quality        Run focused type, security, dependency, and complexity checks
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
      DASHBOARD_MODE="force-on"
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
    --with-quality)
      RUN_QUALITY=true
      shift
      ;;
    --skip-smoke)
      RUN_SMOKE=false
      shift
      ;;
    --no-dashboard)
      RUN_DASHBOARD=false
      DASHBOARD_MODE="force-off"
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

if [[ "$PROFILE" == "full" && "$DASHBOARD_MODE" == "auto" ]]; then
  RUN_DASHBOARD=true
fi

echo "==> Profile: $PROFILE"
echo "==> Sync dependencies: $RUN_SYNC"
echo "==> Run lint: $RUN_LINT"
echo "==> Run quality checks: $RUN_QUALITY"
echo "==> Run smoke test: $RUN_SMOKE"
echo "==> Build dashboard: $RUN_DASHBOARD"

if [[ "$RUN_SYNC" == true ]]; then
  echo "==> Syncing dependencies with uv"
  uv sync --group dev --locked
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

if [[ "$RUN_QUALITY" == true ]]; then
  echo "==> Running focused Pyright quality checks"
  uv run pyright --project pyrightconfig.quality.json
  echo "==> Running focused Bandit security checks"
  PYTHONIOENCODING=utf-8 uv run bandit -r \
    astrbot/api \
    astrbot/cli \
    astrbot/core/backup \
    astrbot/core/knowledge_base \
    astrbot/core/skills \
    astrbot/utils \
    -c pyproject.toml
  echo "==> Running dependency vulnerability audit"
  uv run pip-audit
  echo "==> Running complexity reports"
  uv run radon cc \
    astrbot/api \
    astrbot/cli \
    astrbot/core/backup \
    astrbot/core/config \
    astrbot/core/knowledge_base \
    astrbot/core/skills \
    astrbot/utils \
    -s -n C
  uv run radon mi \
    astrbot/api \
    astrbot/cli \
    astrbot/core/backup \
    astrbot/core/config \
    astrbot/core/knowledge_base \
    astrbot/core/skills \
    astrbot/utils \
    -s
fi

echo "==> Running pytest"
pytest_args=()
if [[ -n "${PYTEST_ARGS:-}" ]]; then
  while IFS= read -r -d '' argument; do
    pytest_args+=("$argument")
  done < <(
    python3 -c 'import os, shlex, sys; sys.stdout.buffer.write(b"\0".join(arg.encode() for arg in shlex.split(os.environ["PYTEST_ARGS"])))'
  )
fi
if [[ "$PROFILE" == "neo" ]]; then
  NEO_TESTS=(
    "tests/test_neo_skill_sync.py"
    "tests/test_neo_skill_tools.py"
    "tests/test_computer_skill_sync.py"
    "tests/test_skill_manager_sandbox_cache.py"
    "tests/test_dashboard.py::test_neo_skills_routes"
  )
  uv run pytest -q "${NEO_TESTS[@]}" "${pytest_args[@]}"
else
  uv run pytest --cov=. -v -o log_cli=true -o log_level=DEBUG "${pytest_args[@]}"
fi

run_smoke_test() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required for smoke test." >&2
    return 1
  fi

  local smoke_port="6185"
  local smoke_log smoke_err_log
  smoke_log="$(mktemp -t astrbot-smoke.XXXXXX.log)"
  smoke_err_log="$(mktemp -t astrbot-smoke.XXXXXX.err.log)"

  echo "==> Starting smoke test on http://127.0.0.1:${smoke_port}"
  uv run main.py >"$smoke_log" 2>"$smoke_err_log" &
  local app_pid=$!

  for _ in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${smoke_port}" >/dev/null 2>&1; then
      echo "==> Smoke test passed"
      kill "$app_pid" 2>/dev/null || true
      wait "$app_pid" 2>/dev/null || true
      rm -f "$smoke_log" "$smoke_err_log"
      return 0
    fi

    if ! kill -0 "$app_pid" 2>/dev/null; then
      echo "AstrBot process exited before becoming healthy." >&2
      tail -n 60 "$smoke_log" || true
      tail -n 60 "$smoke_err_log" || true
      rm -f "$smoke_log" "$smoke_err_log"
      return 1
    fi

    sleep 1
  done

  echo "Smoke test failed: health endpoint did not become ready in time." >&2
  tail -n 60 "$smoke_log" || true
  tail -n 60 "$smoke_err_log" || true
  kill "$app_pid" 2>/dev/null || true
  wait "$app_pid" 2>/dev/null || true
  rm -f "$smoke_log" "$smoke_err_log"
  return 1
}

if [[ "$RUN_SMOKE" == true ]]; then
  run_smoke_test
fi

if [[ "$RUN_DASHBOARD" == true ]]; then
  if ! command -v pnpm >/dev/null 2>&1; then
    echo "pnpm 11.21 is required for dashboard builds." >&2
    exit 1
  fi
  echo "==> Building dashboard"
  (
    cd dashboard
    pnpm install --frozen-lockfile
    pnpm run build
  )
fi

echo "==> PR checks completed successfully"
