#!/usr/bin/env bash

set -euo pipefail

if (($# != 1)); then
  echo "Usage: scripts/make_dev.sh <run-backend|run-dashboard|stop-backend|stop-dashboard|status|clean>" >&2
  exit 2
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
run_dir="$repo_root/.make"
dashboard_dir="$repo_root/dashboard"
backend_pid_file="$run_dir/backend.pid"
dashboard_pid_file="$run_dir/dashboard.pid"
backend_log="$repo_root/backend_run.log"
backend_err_log="$repo_root/backend_run.err.log"
dashboard_log="$repo_root/frontend_run.log"
dashboard_err_log="$repo_root/frontend_run.err.log"

remove_if_exists() {
  if [[ -e "$1" || -L "$1" ]]; then
    rm -rf -- "$1"
  fi
}

stop_pid() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null || return 0

  local pgid
  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ "$pgid" == "$pid" ]]; then
    kill -TERM -- "-$pid" 2>/dev/null || true
  else
    kill -TERM "$pid" 2>/dev/null || true
  fi

  for _ in {1..20}; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.2
  done

  if [[ "$pgid" == "$pid" ]]; then
    kill -KILL -- "-$pid" 2>/dev/null || true
  else
    kill -KILL "$pid" 2>/dev/null || true
  fi
}

stop_from_pid_file() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 0
  local pid
  pid="$(<"$pid_file")"
  if [[ "$pid" =~ ^[0-9]+$ ]]; then
    stop_pid "$pid"
  fi
  rm -f -- "$pid_file"
}

pids_listening_on_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
  elif command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | sed -nE "s/.*[:.]${port}[[:space:]].*pid=([0-9]+).*/\\1/p" || true
  elif command -v netstat >/dev/null 2>&1; then
    netstat -ltnp 2>/dev/null | sed -nE "s/.*[:.]${port}[[:space:]].*[[:space:]]([0-9]+)\\/.*/\\1/p" || true
  else
    echo "Unable to inspect port $port: install lsof, iproute2, or net-tools." >&2
    return 1
  fi
}

stop_by_port() {
  local port="$1"
  local pid
  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] && stop_pid "$pid"
  done < <(pids_listening_on_port "$port")
}

start_managed_process() {
  local pid_file="$1"
  local working_directory="$2"
  local stdout_path="$3"
  local stderr_path="$4"
  local warmup_seconds="$5"
  shift 5

  mkdir -p "$run_dir"
  stop_from_pid_file "$pid_file"
  : >"$stdout_path"
  : >"$stderr_path"

  (
    cd "$working_directory"
    if command -v setsid >/dev/null 2>&1; then
      exec setsid "$@"
    fi
    exec "$@"
  ) >>"$stdout_path" 2>>"$stderr_path" &
  local pid=$!
  printf '%s\n' "$pid" >"$pid_file"
  sleep "$warmup_seconds"
}

show_dashboard_credentials() {
  local deadline=$((SECONDS + 30))
  local pattern='Initial username:|Initial password:|Change it after logging in|Username:'
  while ((SECONDS < deadline)); do
    if [[ -f "$backend_log" ]] && grep -E "$pattern" "$backend_log" >/dev/null 2>&1; then
      echo
      echo "Dashboard credentials (from $(basename "$backend_log")):"
      grep -E "$pattern" "$backend_log" | sed 's/^/  /'
      echo
      return
    fi
    sleep 0.5
  done
  echo "Dashboard credentials not found in $(basename "$backend_log") yet."
  echo "Check the log directly: $backend_log"
}

url_is_available() {
  curl --fail --silent --show-error --head --max-time 10 "$1" >/dev/null 2>&1 ||
    curl --fail --silent --show-error --max-time 10 "$1" >/dev/null 2>&1
}

case "$1" in
  run-backend)
    start_managed_process "$backend_pid_file" "$repo_root" "$backend_log" "$backend_err_log" 6 uv run main.py
    show_dashboard_credentials
    ;;
  run-dashboard)
    start_managed_process "$dashboard_pid_file" "$dashboard_dir" "$dashboard_log" "$dashboard_err_log" 8 pnpm dev
    ;;
  stop-backend)
    stop_from_pid_file "$backend_pid_file"
    stop_by_port 6185
    ;;
  stop-dashboard)
    stop_from_pid_file "$dashboard_pid_file"
    stop_by_port 3000
    ;;
  status)
    if url_is_available http://127.0.0.1:6185/api/v1/openapi.json; then backend_status=up; else backend_status=down; fi
    if url_is_available http://127.0.0.1:3000; then dashboard_status=up; else dashboard_status=down; fi
    printf 'Backend  : %s -> %s\n' "$(basename "$backend_pid_file")" "$backend_status"
    printf 'Dashboard: %s -> %s\n' "$(basename "$dashboard_pid_file")" "$dashboard_status"
    ;;
  clean)
    stop_from_pid_file "$dashboard_pid_file"
    stop_from_pid_file "$backend_pid_file"
    stop_by_port 3000
    stop_by_port 6185
    for path in \
      "$run_dir" "$backend_log" "$backend_err_log" "$dashboard_log" "$dashboard_err_log" \
      "$dashboard_dir/dist" "$dashboard_dir/node_modules/.vite" "$repo_root/.tmp" \
      "$repo_root/.pytest_cache" "$repo_root/.ruff_cache" "$repo_root/.mypy_cache" \
      "$repo_root/htmlcov" "$repo_root/.coverage" "$repo_root/build" "$repo_root/dist" \
      "$repo_root/data/dist" "$repo_root/logs" "$repo_root/temp"; do
      remove_if_exists "$path"
    done
    find "$repo_root" -type f \( -name '*.log' -o -name '*.pyc' -o -name '*.pyo' \) -delete
    find "$repo_root" -type d -name __pycache__ -prune -exec rm -rf {} +
    ;;
  *)
    echo "Unsupported action: $1" >&2
    exit 2
    ;;
esac
