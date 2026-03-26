#!/usr/bin/env bash
set -euo pipefail

remote_name="${1:-sdk-remote}"
remote_branch="${2:-vendor-branch}"
prefix="${3:-astrbot-sdk}"

fail() {
  echo "$1" >&2
  exit 1
}

run_git() {
  git "$@" || fail "git $* failed."
}

test_git_object_path() {
  local revision="$1"
  local path="$2"

  git cat-file -e "${revision}:${path}" >/dev/null 2>&1
}

assert_remote_exists() {
  local name="$1"

  if ! git remote | grep -Fxq "$name"; then
    fail "Git remote '$name' is missing. Add it first, for example: git remote add $name https://github.com/united-pooh/astrbot-sdk.git"
  fi
}

assert_clean_worktree() {
  local status_output
  status_output="$(git status --porcelain=v1)"

  if [[ -n "$status_output" ]]; then
    fail "Worktree is not clean. Commit or stash changes before syncing the vendored SDK.
$status_output"
  fi
}

assert_local_path() {
  local path="$1"
  local reason="$2"

  [[ -e "$path" ]] || fail "Expected local path '$path' is missing. $reason"
}

assert_remote_path() {
  local revision="$1"
  local path="$2"
  local reason="$3"

  test_git_object_path "$revision" "$path" || fail "Remote snapshot '$revision' is missing '$path'. $reason"
}

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || fail "This script must run inside a git repository."
cd "$repo_root"

local_required_paths=(
  "${prefix}/pyproject.toml"
  "${prefix}/README.md"
  "${prefix}/src/astrbot_sdk/__init__.py"
)

for required_path in "${local_required_paths[@]}"; do
  assert_local_path "$required_path" "The current AstrBot workspace expects '$prefix' to keep the SDK's editable package layout."
done

assert_remote_exists "$remote_name"
assert_clean_worktree

echo "Fetching ${remote_name}/${remote_branch}..."
run_git fetch "$remote_name" "$remote_branch"

remote_ref="refs/remotes/${remote_name}/${remote_branch}"
remote_commit="$(git rev-parse "$remote_ref" 2>/dev/null)" || fail "Unable to resolve remote ref '$remote_ref' after fetch."
[[ -n "$remote_commit" ]] || fail "Unable to resolve remote ref '$remote_ref' after fetch."

# Fail fast if the source branch does not match the package layout the main repo
# currently installs via `astrbot-sdk = { path = "./astrbot-sdk", editable = true }`.
# Pulling an incompatible snapshot would silently break dependency resolution.
remote_required_paths=(
  "pyproject.toml"
  "README.md"
  "src/astrbot_sdk/__init__.py"
)

for required_path in "${remote_required_paths[@]}"; do
  assert_remote_path "$remote_ref" "$required_path" "The vendor branch must expose the full SDK package layout required by the main repo before subtree sync is allowed."
done

echo "Pulling ${remote_name}/${remote_branch} into ${prefix} with git subtree --squash..."
run_git subtree pull "--prefix=${prefix}" "$remote_name" "$remote_branch" --squash

for required_path in "${local_required_paths[@]}"; do
  assert_local_path "$required_path" "The subtree pull finished, but the local SDK layout is incomplete."
done

echo
echo "SDK sync completed successfully."
echo "Review the result with:"
echo "  git status --short"
echo "  ls ${prefix}"
echo "  test -e ${prefix}/pyproject.toml"
echo "  test -e ${prefix}/src/astrbot_sdk/__init__.py"
