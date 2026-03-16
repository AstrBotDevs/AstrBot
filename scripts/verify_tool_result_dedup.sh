#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/3] Running targeted dedup tests"
uv run pytest -q tests/test_tool_loop_agent_runner.py -m tool_dedup

echo "[2/3] Verifying default config exposes dedup toggle"
uv run python - <<'PY'
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.config.tool_loop_defaults import (
    DEFAULT_DEDUPLICATE_REPEATED_TOOL_RESULTS,
    DEFAULT_TOOL_ERROR_REPEAT_GUARD_THRESHOLD,
    DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES,
)

provider_settings = DEFAULT_CONFIG.get("provider_settings", {})
assert "deduplicate_repeated_tool_results" in provider_settings
assert (
    provider_settings["deduplicate_repeated_tool_results"]
    is DEFAULT_DEDUPLICATE_REPEATED_TOOL_RESULTS
)
assert "tool_result_dedup_max_entries" in provider_settings
assert provider_settings["tool_result_dedup_max_entries"] == DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES
assert "tool_error_repeat_guard_threshold" in provider_settings
assert (
    provider_settings["tool_error_repeat_guard_threshold"]
    == DEFAULT_TOOL_ERROR_REPEAT_GUARD_THRESHOLD
)
print(
    "DEFAULT_CONFIG.provider_settings.deduplicate_repeated_tool_results="
    f"{DEFAULT_DEDUPLICATE_REPEATED_TOOL_RESULTS}"
)
print(
    "DEFAULT_CONFIG.provider_settings.tool_result_dedup_max_entries="
    f"{DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES}"
)
print(
    "DEFAULT_CONFIG.provider_settings.tool_error_repeat_guard_threshold="
    f"{DEFAULT_TOOL_ERROR_REPEAT_GUARD_THRESHOLD}"
)
PY

echo "[3/3] Optional runtime config check (data/cmd_config.json)"
if [[ -f "data/cmd_config.json" ]]; then
  uv run python - <<'PY'
import json
from pathlib import Path

cfg_path = Path("data/cmd_config.json")
cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
value = cfg.get("provider_settings", {}).get("deduplicate_repeated_tool_results")
max_entries = cfg.get("provider_settings", {}).get("tool_result_dedup_max_entries")
guard_threshold = cfg.get("provider_settings", {}).get("tool_error_repeat_guard_threshold")
print(f"{cfg_path}: provider_settings.deduplicate_repeated_tool_results={value!r}")
print(f"{cfg_path}: provider_settings.tool_result_dedup_max_entries={max_entries!r}")
print(f"{cfg_path}: provider_settings.tool_error_repeat_guard_threshold={guard_threshold!r}")
PY
else
  echo "data/cmd_config.json not found, skip runtime check."
fi

echo "Verification completed."
