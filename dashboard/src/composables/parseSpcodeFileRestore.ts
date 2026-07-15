// Author: elecvoid243
// Date: 2026-06-22
// Spec: docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md §4-5
//
// Pure parser for POST /spcode/file-restore responses. No Vue / no axios —
// importable by node --test (see tests/parseSpcodeFileRestore.test.mjs).

/** All reason codes the spcode plugin can return (excluding `null` = success). */
export const RESTORE_REASON_CODES = [
  "invalid_body",
  "missing_file",
  "feature_disabled",
  "no_project_loaded",
  "directory_missing",
  "not_a_git_repo",
  "worktree_invalid",
  "git_unavailable",
  "path_unsafe",
  "file_not_found",
  "not_modified",
  "git_error",
] as const;

export type RestoreReason = (typeof RESTORE_REASON_CODES)[number] | "network" | "unknown";

/** Raw response shape from POST /spcode/file-restore. */
export interface SpcodeFileRestoreRawResponse {
  restored: boolean;
  reason: string | null;
  file: string;
  umo: string | null;
  worktree: string;
  directory: string | null;
  /**
   * Echoed by the plugin to indicate the restore scope it actually applied
   * (since the plugin auto-detects from `git status` since v3.6):
   *   - "unstaged": worktree was reset to index (file was modified but not staged)
   *   - "staged":   both index and worktree were reset to HEAD (file was staged)
   */
  scope: "unstaged" | "staged";
  elapsed_ms: number;
  stderr: string;
}

export interface SpcodeFileRestoreSnapshot {
  restored: boolean;
  reason: string | null;
  file: string;
  umo: string | null;
  worktree: string;
  directory: string | null;
  scope: "unstaged" | "staged";
  elapsedMs: number;
  stderr: string;
}

export type ParseResult =
  | { kind: "ok"; snapshot: SpcodeFileRestoreSnapshot }
  | { kind: "error"; reason: string };

/**
 * Parse the envelope returned by POST /spcode/file-restore.
 *
 * Throws if the envelope is malformed (caller catches and shows generic
 * error toast). Business-level failures (restored=false with a reason
 * code) are NOT thrown — they're returned as `kind: "ok"` with the
 * reason captured in the snapshot, matching the existing
 * parseSpcodeGitDiff convention.
 */
export function parseSpcodeFileRestore(
  raw: unknown,
): ParseResult {
  if (typeof raw !== "object" || raw === null) {
    throw new Error("missing status envelope");
  }
  const env = raw as { status?: unknown; data?: unknown };
  if (env.status !== "ok") {
    throw new Error("unexpected status envelope");
  }
  if (typeof env.data !== "object" || env.data === null) {
    throw new Error("missing data in response");
  }
  const d = env.data as Partial<SpcodeFileRestoreRawResponse>;
  // v3.6: scope can be "unstaged" or "staged"; default to "unstaged" to keep
  // forward-compat with older plugin versions that always echoed "unstaged".
  const rawScope = d.scope;
  const scope: "unstaged" | "staged" =
    rawScope === "staged" ? "staged" : "unstaged";
  return {
    kind: "ok",
    snapshot: {
      restored: Boolean(d.restored),
      reason: d.reason ?? null,
      file: typeof d.file === "string" ? d.file : "",
      umo: typeof d.umo === "string" ? d.umo : null,
      worktree: typeof d.worktree === "string" ? d.worktree : "",
      directory: typeof d.directory === "string" ? d.directory : null,
      scope,
      elapsedMs: typeof d.elapsed_ms === "number" ? d.elapsed_ms : 0,
      stderr: typeof d.stderr === "string" ? d.stderr : "",
    },
  };
}

/**
 * Classify a reason string to a known RestoreReason.
 * Returns the input unchanged if it's a known code; otherwise "unknown".
 * "network" is returned only when the caller passes it explicitly (used
 * by useSpcodeFileRestore to flag axios ERR_NETWORK before the parser
 * ever runs).
 */
export function classifyReason(raw: string | null | undefined): RestoreReason {
  if (raw === null || raw === undefined) return "unknown";
  if (raw === "network") return "network";
  if ((RESTORE_REASON_CODES as readonly string[]).includes(raw)) {
    return raw as RestoreReason;
  }
  return "unknown";
}