// Author: elecvoid243, 2026-07-16
// Spec: docs/superpowers/specs/2026-07-16-git-repo-init-prompt-design.md §Architecture
//
// Parses the `GET /spcode/git-branches` response into a 3-state result
// relevant to the init-prompt feature. Only three things matter:
//   1. success + reason null → "is a Git repo" + the default branch name
//   2. reason === "not_a_git_repo" → show the init prompt
//   3. anything else → an error chip
// The full branch list is intentionally NOT extracted here; that will
// be owned by a future branch-management composable.

export type GitRepoProbeParseResult =
  | { kind: "ok"; defaultBranch: string | null }
  | { kind: "not_a_git_repo"; directory: string }
  | { kind: "error"; reason: string; stderr?: string };

/** Parse the `git-branches` envelope into the 3-state init-prompt result. */
export function parseSpcodeGitRepoProbe(raw: unknown): GitRepoProbeParseResult {
  if (!isObject(raw)) return { kind: "error", reason: "unknown" };
  const reason = typeof raw.reason === "string" ? raw.reason : null;
  const success = raw.success === true;
  const data = isObject(raw.data) ? raw.data : null;
  const stderr = typeof raw.stderr === "string" ? raw.stderr : undefined;

  if (success && reason === null) {
    const defaultBranch =
      data && typeof data.default === "string" ? data.default : null;
    return { kind: "ok", defaultBranch };
  }
  if (reason === "not_a_git_repo") {
    const directory =
      data && typeof data.directory === "string" ? data.directory : "";
    return { kind: "not_a_git_repo", directory };
  }
  return {
    kind: "error",
    reason: reason ?? "unknown",
    ...(stderr !== undefined ? { stderr } : {}),
  };
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}
