// Author: elecvoid243
// Date: 2026-06-27
// Spec: docs/superpowers/specs/2026-06-27-git-worktree-frontend-management-design.md §1.2
//
// Pure parser for the 4 git worktree management endpoints (git-worktree-add
// / git-worktree-remove / git-worktree-lock / git-worktree-unlock). No Vue /
// no axios. Mirrors parseSpcodeGitWorkflow.ts split.
//
// All 4 endpoints return the SAME envelope shape:
//   { status: "ok", data: { loaded, directory, umo, worktree, [endpoint-specific], worktrees, reason, stderr, elapsed_ms } }
// The `worktrees` field is the **refreshed complete list** of worktrees,
// which the consumer (useSpcodeWorktrees) uses to atomically replace
// its state — no extra GET roundtrip needed.

import type { SpcodeGitWorktreesSnapshot } from "./parseSpcodeWorktrees";

// ── Endpoint id union ──────────────────────────────────────
export type WorktreeMgmtEndpoint = "add" | "remove" | "lock" | "unlock";

// ── Raw envelope shape (shared by all 4 endpoints) ────────
export interface SpcodeWorktreeMgmtRawData {
  loaded: boolean;
  directory: string | null;
  umo: string | null;
  worktree: string;
  // Endpoint-specific (optional in raw shape; present per endpoint).
  branch?: string | null;
  removed_path?: string;
  locked?: boolean;
  lock_reason?: string | null;
  // The refreshed worktree list.
  worktrees: unknown[];
  reason: string | null;
  stderr: string;
  elapsed_ms: number;
}

export interface SpcodeWorktreeMgmtRawResponse {
  loaded?: boolean;
  directory?: string | null;
  umo?: string | null;
  worktree?: string;
  branch?: string | null;
  removed_path?: string;
  locked?: boolean;
  lock_reason?: string | null;
  worktrees?: unknown[];
  reason?: string | null;
  stderr?: string;
  elapsed_ms?: number;
}

export type ParseResult<T> =
  | { kind: "ok"; snapshot: T }
  | { kind: "error"; reason: string };

// ── Snapshot (consumer-facing) ────────────────────────────
//
// We embed the same `meta` shape SpcodeGitWorktreesSnapshot uses, so
// the useSpcodeWorktrees consumer can swap state with the refreshed
// list atomically.
export interface SpcodeWorktreeMgmtSnapshot {
  meta: {
    directory: string | null;
    umo: string | null;
    loaded: boolean;
    reason: string | null;
    stderr: string;
    elapsedMs: number;
    fetchedAt: number;
  };
  worktree: string;
  branch: string | null;
  removedPath: string | null;
  locked: boolean;
  lockReason: string | null;
  worktrees: SpcodeGitWorktreesSnapshot["worktrees"];
}
