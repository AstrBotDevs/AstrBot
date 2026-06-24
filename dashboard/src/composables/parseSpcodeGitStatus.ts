// Author: elecvoid243
// Date: 2026-06-24
// Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md
//      (extension: merge git-status untracked/intent_to_add into the
//      unstaged view).
//
// Parser + types for GET /spcode/git-status (spcode plugin v2.13+).
// Response contract is defined in
// `astrbot_plugin_spcode_toolkit/docs/webapi-git-workflow-api.md §5.1`.
//
// The git-status endpoint is **complementary** to git-diff: it answers
// "which files have changed (+ scope classification)" without shipping
// the patch text. The dashboard merges `untracked` + `intent_to_add`
// entries from git-status into the unstaged diff view so users see
// brand-new files alongside modifications in one place.

/**
 * Scope classification derived by the backend from porcelain v1 X/Y
 * columns (see tools/webapi/git_status.py::_classify_file_scope).
 */
export type GitStatusScope =
  | "staged"
  | "unstaged"
  | "intent_to_add"
  | "untracked"
  | "conflict"
  | "modified_both";

const VALID_SCOPES: ReadonlySet<GitStatusScope> = new Set([
  "staged",
  "unstaged",
  "intent_to_add",
  "untracked",
  "conflict",
  "modified_both",
]);

export function normalizeStatusScope(raw: unknown): GitStatusScope | null {
  return VALID_SCOPES.has(raw as GitStatusScope) ? (raw as GitStatusScope) : null;
}

/**
 * A single file entry from `git status --porcelain`, classified into a
 * logical scope. The raw `x_status` / `y_status` are preserved so the UI
 * can render faithful badges without re-deriving them.
 */
export interface SpcodeGitStatusFile {
  /** Repository-relative POSIX path (rename/copy uses the new path). */
  path: string;
  /** Porcelain X column (index action). `?` / ` ` for untracked. */
  x_status: string;
  /** Porcelain Y column (worktree action). `?` / ` ` for untracked. */
  y_status: string;
  /** Backend-derived logical scope. */
  scope: GitStatusScope;
}

/**
 * True when the scope represents a brand-new file that has no diff
 * content yet. Used to decide whether the sidebar should render the
 * entry as a "new file" (no patch) vs. a regular diff row.
 *
 * - `untracked`    → `?? path` (never seen by git)
 * - `intent_to_add` → `git add -N` placeholder
 */
export function isNewFileScope(scope: GitStatusScope | null | undefined): boolean {
  return scope === "untracked" || scope === "intent_to_add";
}

export interface SpcodeGitStatusUpstream {
  branch: string;
  ahead: number;
  behind: number;
}

export interface SpcodeGitStatusSummary {
  staged: number;
  unstaged: number;
  untracked: number;
  conflicts: number;
  total: number;
}

export interface SpcodeGitStatusMeta {
  directory: string | null;
  umo: string | null;
  loaded: boolean;
  /** Current branch; `null` for detached HEAD or non-git dirs. */
  branch: string | null;
  /** Upstream sync info; `null` when no upstream is set up. */
  upstream: SpcodeGitStatusUpstream | null;
  /** `reason` mirrors the failure codes used by the rest of git-status. */
  reason: string | null;
  elapsedMs: number;
  /** Server wall-clock for the snapshot; used to display "X seconds ago". */
  fetchedAt: number;
}

export interface SpcodeGitStatusSnapshot {
  meta: SpcodeGitStatusMeta;
  files: SpcodeGitStatusFile[];
  summary: SpcodeGitStatusSummary;
  /** `true` when the file list was hard-truncated at MAX_FILES. */
  truncated: boolean;
  maxFiles: number;
}

/** Loose shape of the `data` envelope returned by GET /spcode/git-status. */
export interface SpcodeGitStatusRawResponse {
  loaded: boolean;
  directory: string | null;
  umo: string | null;
  worktree: string | null;
  branch?: string | null;
  upstream?: SpcodeGitStatusUpstream | null;
  files?: Array<{
    path: string;
    x_status: string;
    y_status: string;
    scope: GitStatusScope | string;
  }>;
  summary?: Partial<SpcodeGitStatusSummary>;
  truncated?: boolean;
  max_files?: number;
  reason?: string | null;
  elapsed_ms?: number;
}

function parseUpstream(raw: unknown): SpcodeGitStatusUpstream | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const branch = obj.branch;
  const ahead = obj.ahead;
  const behind = obj.behind;
  if (typeof branch !== "string" || !branch) return null;
  return {
    branch,
    ahead: typeof ahead === "number" ? ahead : 0,
    behind: typeof behind === "number" ? behind : 0,
  };
}

function parseSummary(raw: unknown): SpcodeGitStatusSummary {
  const empty: SpcodeGitStatusSummary = {
    staged: 0,
    unstaged: 0,
    untracked: 0,
    conflicts: 0,
    total: 0,
  };
  if (!raw || typeof raw !== "object") return empty;
  const obj = raw as Record<string, unknown>;
  return {
    staged: typeof obj.staged === "number" ? obj.staged : 0,
    unstaged: typeof obj.unstaged === "number" ? obj.unstaged : 0,
    untracked: typeof obj.untracked === "number" ? obj.untracked : 0,
    conflicts: typeof obj.conflicts === "number" ? obj.conflicts : 0,
    total: typeof obj.total === "number" ? obj.total : 0,
  };
}

export function parseSpcodeGitStatus(
  data: SpcodeGitStatusRawResponse,
): SpcodeGitStatusSnapshot {
  const rawFiles = Array.isArray(data.files) ? data.files : [];
  const files: SpcodeGitStatusFile[] = rawFiles
    .map((f): SpcodeGitStatusFile | null => {
      if (!f || typeof f !== "object") return null;
      const path = typeof f.path === "string" ? f.path : "";
      if (!path) return null;
      const scope = normalizeStatusScope(f.scope);
      if (!scope) return null;
      return {
        path,
        x_status: typeof f.x_status === "string" ? f.x_status : "",
        y_status: typeof f.y_status === "string" ? f.y_status : "",
        scope,
      };
    })
    .filter((f): f is SpcodeGitStatusFile => f !== null);

  return {
    meta: {
      directory: data.directory ?? null,
      umo: data.umo ?? null,
      loaded: Boolean(data.loaded),
      branch: typeof data.branch === "string" ? data.branch : null,
      upstream: parseUpstream(data.upstream),
      reason: data.reason ?? null,
      elapsedMs: typeof data.elapsed_ms === "number" ? data.elapsed_ms : 0,
      fetchedAt: Date.now(),
    },
    files,
    summary: parseSummary(data.summary),
    truncated: Boolean(data.truncated),
    maxFiles: typeof data.max_files === "number" ? data.max_files : 1000,
  };
}