// Author: elecvoid243, 2026-07-16
// Spec: docs/superpowers/specs/2026-07-16-git-repo-init-prompt-design.md §Architecture
//
// Parses the `GET /spcode/git-branches` response into a 3-state result
// relevant to the init-prompt feature. Only three things matter:
//   1. reason === null → "is a Git repo" + the active branch name
//   2. reason === "not_a_git_repo" → show the init prompt
//   3. anything else → an error chip
// The full branch list is intentionally NOT extracted here; that will
// be owned by a future branch-management composable.
//
// Wire shape (after axios auto-unwraps the outer `data` key):
//   { reason: string | null, stderr: string, elapsed_ms: number,
//     current?: string, default?: string, branches?: unknown[], ... }
// The backend's `_make_envelope` factory never emits an explicit
// `success` field; success is conveyed solely by `reason: null`.
// `directory` and `current` are the relevant endpoint-specific fields.
// This file is called with the value of `resp.data`, so it must NOT
// expect a nested `data` key.

export type GitRepoProbeParseResult =
  | { kind: "ok"; defaultBranch: string | null }
  | { kind: "not_a_git_repo"; directory: string }
  | { kind: "error"; reason: string; stderr?: string };

/** Parse the `git-branches` envelope into the 3-state init-prompt result. */
export function parseSpcodeGitRepoProbe(raw: unknown): GitRepoProbeParseResult {
  if (!isObject(raw)) return { kind: "error", reason: "unknown" };
  // The backend's `_make_envelope` always sets `reason` (either `null`
  // for success or a reason code for failure). A missing `reason` field
  // means the envelope is malformed (e.g. an empty `{}` body) and must
  // surface as an error rather than be silently treated as a success.
  const reason = typeof raw.reason === "string" ? raw.reason : null;
  const stderr = typeof raw.stderr === "string" && raw.stderr !== "" ? raw.stderr : undefined;

  if ("reason" in raw && reason === null) {
    // Backend uses `current` for the active branch; `default` is
    // accepted as a fallback for any future endpoint that follows the
    // spec's original field name.
    const defaultBranch =
      typeof raw.current === "string"
        ? raw.current
        : typeof raw.default === "string"
          ? raw.default
          : null;
    return { kind: "ok", defaultBranch };
  }
  if (reason === "not_a_git_repo") {
    const directory = typeof raw.directory === "string" ? raw.directory : "";
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
