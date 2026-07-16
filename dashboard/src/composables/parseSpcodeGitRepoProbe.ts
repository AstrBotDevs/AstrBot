// Author: elecvoid243, 2026-07-16 (updated 2026-07-16 for git-repo-check)
// Spec: docs/api/webapi-git-repo-check-api.md
//
// Parses the `GET /spcode/git-repo-check` response into a 3-state result
// relevant to the init-prompt feature. Only three things matter:
//   1. is_git_repo === true -> "is a Git repo"
//   2. reason === "not_a_git_repo" -> show the init prompt
//   3. anything else -> an error chip
//
// Wire shape (the INNER payload after the composable has unwrapped the
// OpenAPI envelope via `resp.data?.data`):
//   { is_git_repo: boolean | null, git_available: boolean | null,
//     directory: string, reason: string | null, stderr: string,
//     elapsed_ms: number }
// The backend's `_make_envelope` factory never emits an explicit
// `success` field; success is conveyed solely by `reason: null`.

export type GitRepoProbeParseResult =
  | { kind: "ok"; directory: string }
  | { kind: "not_a_git_repo"; directory: string }
  | { kind: "error"; reason: string; stderr?: string };

/** Parse the `git-repo-check` envelope into the 3-state init-prompt result. */
export function parseSpcodeGitRepoProbe(raw: unknown): GitRepoProbeParseResult {
  if (!isObject(raw)) return { kind: "error", reason: "unknown" };
  const reason = typeof raw.reason === "string" ? raw.reason : null;
  const stderr =
    typeof raw.stderr === "string" && raw.stderr !== "" ? raw.stderr : undefined;
  const directory = typeof raw.directory === "string" ? raw.directory : "";

  // is_git_repo === true -> confirmed Git repo (reason is null).
  // An empty object {} has no `reason` key, so guard with `in` check
  // to avoid treating a malformed/empty envelope as success.
  if ("reason" in raw && reason === null) {
    return { kind: "ok", directory };
  }
  if (reason === "not_a_git_repo") {
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
