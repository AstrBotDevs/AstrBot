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

// ── Envelope helpers (copied & adapted from parseSpcodeGitWorkflow) ─

function unwrapEnvelope(raw: unknown): unknown {
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
  return env.data;
}

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
function asStringOrNull(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}
function asNumber(v: unknown, fallback = 0): number {
  return typeof v === "number" ? v : fallback;
}
function asBoolean(v: unknown, fallback = false): boolean {
  return typeof v === "boolean" ? v : fallback;
}

/** Build the snapshot's `meta` block + endpoint-specific fields.
 *  Pure function — takes the unwrapped `data` object and the consumer-
 *  facing field overrides. Centralizes the field-name mapping from
 *  snake_case (backend) to camelCase (frontend) so the 4 parsers
 *  share the same implementation. */
function buildSnapshot(
  d: SpcodeWorktreeMgmtRawData,
  overrides: Partial<{
    branch: string | null;
    removedPath: string | null;
    locked: boolean;
    lockReason: string | null;
  }> = {},
): SpcodeWorktreeMgmtSnapshot {
  return {
    meta: {
      directory: d.directory ?? null,
      umo: d.umo ?? null,
      loaded: Boolean(d.loaded),
      reason: d.reason ?? null,
      stderr: asString(d.stderr),
      elapsedMs: asNumber(d.elapsed_ms),
      fetchedAt: Date.now(),
    },
    worktree: asString(d.worktree),
    branch: overrides.branch !== undefined ? overrides.branch : asStringOrNull(d.branch),
    removedPath:
      overrides.removedPath !== undefined
        ? overrides.removedPath
        : (d.removed_path ?? null),
    locked: overrides.locked !== undefined ? overrides.locked : asBoolean(d.locked),
    lockReason:
      overrides.lockReason !== undefined
        ? overrides.lockReason
        : (d.lock_reason ?? null),
    // We reuse the raw worktrees array as-is; useSpcodeWorktrees will
    // re-parse via parseSpcodeGitWorktrees() before swapping state.
    // The double-parse is intentional: it keeps the parser pure (no
    // import of parseSpcodeWorktrees here) and avoids drifting the
    // two parsers' field mappings.
    worktrees: (d.worktrees ?? []) as SpcodeGitWorktreesSnapshot["worktrees"],
  };
}

// ── Endpoint-specific parsers ─────────────────────────────
//
// All 4 share the same envelope shape; only the endpoint-specific
// field overrides differ. Each parser is 4-6 lines.

/** Parse the envelope from POST /spcode/git-worktree-add. */
export function parseSpcodeWorktreeAdd(
  raw: unknown,
): ParseResult<SpcodeWorktreeMgmtSnapshot> {
  const d = unwrapEnvelope(raw) as SpcodeWorktreeMgmtRawData;
  return {
    kind: "ok",
    snapshot: buildSnapshot(d, { branch: d.branch ?? null }),
  };
}

/** Parse the envelope from POST /spcode/git-worktree-remove. */
export function parseSpcodeWorktreeRemove(
  raw: unknown,
): ParseResult<SpcodeWorktreeMgmtSnapshot> {
  const d = unwrapEnvelope(raw) as SpcodeWorktreeMgmtRawData;
  return {
    kind: "ok",
    snapshot: buildSnapshot(d, { removedPath: d.removed_path ?? d.worktree }),
  };
}

/** Parse the envelope from POST /spcode/git-worktree-lock. */
export function parseSpcodeWorktreeLock(
  raw: unknown,
): ParseResult<SpcodeWorktreeMgmtSnapshot> {
  const d = unwrapEnvelope(raw) as SpcodeWorktreeMgmtRawData;
  return {
    kind: "ok",
    snapshot: buildSnapshot(d, {
      locked: true,
      lockReason: d.lock_reason ?? null,
    }),
  };
}

/** Parse the envelope from POST /spcode/git-worktree-unlock. */
export function parseSpcodeWorktreeUnlock(
  raw: unknown,
): ParseResult<SpcodeWorktreeMgmtSnapshot> {
  const d = unwrapEnvelope(raw) as SpcodeWorktreeMgmtRawData;
  return {
    kind: "ok",
    snapshot: buildSnapshot(d, {
      locked: false,
      lockReason: null,
    }),
  };
}
