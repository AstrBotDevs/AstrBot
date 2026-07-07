// Author: elecvoid243
// Date: 2026-07-07
// Spec: docs/superpowers/specs/2026-07-07-hunk-discard-design.md §4.3
// API:  astrbot_plugin_spcode_toolkit/docs/api/webapi-file-discard-hunk-api.md §3.4

export interface SpcodeFileDiscardHunkSnapshot {
  discarded: boolean;
  directory: string | null;
  umo: string | null;
  worktree: string | null;
  file: string;
  scope: "unstaged" | "staged";
  hunksReverted: number;
  patchSha256: string;
  elapsedMs: number;
  stderr: string;
  reason: string | null;
}

export interface SpcodeFileDiscardHunkRawResponse {
  status: string;
  data: {
    discarded: boolean;
    directory: string | null;
    umo: string | null;
    worktree: string | null;
    file: string;
    scope: string;
    hunks_reverted: number;
    patch_sha256: string;
    elapsed_ms: number;
    stderr: string;
    reason: string | null;
  };
}

export type ReasonClass = "ok" | "fatal" | "user" | "retry" | "config" | "unknown";

/** Parse the raw API response into a typed snapshot. */
export function parseSpcodeFileDiscardHunk(
  raw: unknown,
): { kind: "ok"; snapshot: SpcodeFileDiscardHunkSnapshot }
 | { kind: "error"; reason: string } {
  if (typeof raw !== "object" || raw === null) {
    return { kind: "error", reason: "invalid_envelope" };
  }
  const resp = raw as Partial<SpcodeFileDiscardHunkRawResponse>;
  if (resp.status !== "ok" || typeof resp.data !== "object" || resp.data === null) {
    return { kind: "error", reason: "invalid_envelope" };
  }
  const d = resp.data;
  const scope: "unstaged" | "staged" = d.scope === "staged" ? "staged" : "unstaged";
  return {
    kind: "ok",
    snapshot: {
      discarded: !!d.discarded,
      directory: d.directory ?? null,
      umo: d.umo ?? null,
      worktree: d.worktree ?? null,
      file: d.file ?? "",
      scope,
      hunksReverted: typeof d.hunks_reverted === "number" ? d.hunks_reverted : 0,
      patchSha256: d.patch_sha256 ?? "",
      elapsedMs: typeof d.elapsed_ms === "number" ? d.elapsed_ms : 0,
      stderr: d.stderr ?? "",
      reason: d.reason ?? null,
    },
  };
}

/** 39 reason → 4-class (fatal/user/retry/config) + ok/unknown。 */
export function classifyDiscardHunkReason(reason: string | null): ReasonClass {
  if (reason === null) return "ok";
  const FATAL = new Set([
    "not_a_git_repo", "git_unavailable", "feature_disabled",
  ]);
  const USER = new Set([
    "not_modified", "untracked_file", "patch_malformed", "patch_unsafe_path",
    "multi_file_patch", "patch_file_mismatch", "patch_binary", "patch_too_large",
    "missing_file", "file_not_found", "path_unsafe",
  ]);
  const RETRY = new Set([
    "patch_apply_failed", "patch_check_failed", "git_error",
  ]);
  const CONFIG = new Set([
    "no_project_loaded", "worktree_invalid", "directory_missing", "invalid_body",
  ]);
  if (FATAL.has(reason)) return "fatal";
  if (USER.has(reason)) return "user";
  if (RETRY.has(reason)) return "retry";
  if (CONFIG.has(reason)) return "config";
  return "unknown";
}