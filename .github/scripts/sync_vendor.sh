#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  python_bin="python3"
elif command -v python >/dev/null 2>&1; then
  python_bin="python"
else
  echo "error: python interpreter is required to run sync_vendor" >&2
  exit 1
fi

exec "${python_bin}" "${script_dir}/sync_vendor.py" "$@"
