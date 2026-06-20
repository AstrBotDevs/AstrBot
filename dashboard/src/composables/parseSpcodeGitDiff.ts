// Author: elecvoid243
// Date: 2026-06-17 (updated 2026-06-20 for scope echo)
// Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.1.1
//      + docs/superpowers/specs/2026-06-20-git-diff-scope-switcher-design.md §4.2

export type GitDiffScope = "unstaged" | "staged" | "all";

const VALID_SCOPES: ReadonlySet<GitDiffScope> = new Set([
  "unstaged",
  "staged",
  "all",
]);

/**
 * Narrow a free-form `scope` value (e.g. from the spcode response) to
 * the ``GitDiffScope`` union. Anything outside the three legal values
 * collapses to ``null`` so the UI never displays a phantom selection.
 */
function normalizeScope(raw: unknown): GitDiffScope | null {
  return VALID_SCOPES.has(raw as GitDiffScope) ? (raw as GitDiffScope) : null;
}

export interface SpcodeGitDiffRawResponse {
  loaded: boolean;
  directory: string | null;
  umo: string | null;
  scope?: GitDiffScope;
  diff: string | null;
  stat: string | null;
  files_changed: Array<{
    path: string;
    status: string;
    additions: number;
    deletions: number;
  }>;
  truncated: boolean;
  truncated_at_bytes: number;
  max_bytes: number;
  elapsed_ms: number;
  reason: string | null;
}

export type FileStatus = "M" | "A" | "D" | "R" | "C" | "T" | "unknown";

export interface SpcodeGitDiffFile {
  path: string;
  status: FileStatus;
  additions: number;
  deletions: number;
  slice: string | null;
  isBinary: boolean;
}

export interface SpcodeGitDiffMeta {
  directory: string | null;
  umo: string | null;
  loaded: boolean;
  /**
   * Server-echoed scope (only present when ``loaded=true``). Use this
   * to verify the requested ``scope`` reached the backend intact.
   */
  scope: GitDiffScope | null;
  truncated: boolean;
  truncatedAtBytes: number;
  maxBytes: number;
  reason: string | null;
  elapsedMs: number;
  fetchedAt: number;
}

export interface SpcodeGitDiffSnapshot {
  meta: SpcodeGitDiffMeta;
  files: SpcodeGitDiffFile[];
  rawDiff: string | null;
}

const VALID_STATUSES: ReadonlySet<FileStatus> = new Set([
  "M",
  "A",
  "D",
  "R",
  "C",
  "T",
]);

/** Normalize a raw git status code to the FileStatus union. */
function normalizeStatus(raw: string): FileStatus {
  const s = raw[0] as FileStatus;
  return VALID_STATUSES.has(s) ? s : "unknown";
}

export function parseSpcodeGitDiff(
  data: SpcodeGitDiffRawResponse,
): SpcodeGitDiffSnapshot {
  return {
    meta: {
      directory: data.directory,
      umo: data.umo,
      loaded: data.loaded,
      scope: normalizeScope(data.scope),
      truncated: data.truncated,
      truncatedAtBytes: data.truncated_at_bytes,
      maxBytes: data.max_bytes,
      reason: data.reason,
      elapsedMs: data.elapsed_ms,
      fetchedAt: Date.now(),
    },
    files: (() => {
      if (!data.diff || !Array.isArray(data.files_changed)) return [];
      const byPath = new Map<string, SpcodeGitDiffFile>();
      for (const f of data.files_changed) {
        byPath.set(f.path, {
          path: f.path,
          status: normalizeStatus(f.status),
          additions: f.additions ?? 0,
          deletions: f.deletions ?? 0,
          slice: null,
          isBinary: false,
        });
      }
      const segments = data.diff.split(/^diff --git /m);
      for (let i = 1; i < segments.length; i++) {
        const seg = "diff --git " + segments[i];
        const m = seg.match(/^diff --git a\/\S+ b\/(\S+)/m);
        if (!m) continue;
        const path = m[1];
        const existing = byPath.get(path);
        if (!existing) continue;
        if (seg.includes("Binary files")) {
          existing.isBinary = true;
        } else {
          existing.slice = seg;
        }
      }
      return data.files_changed.map(
        (f) =>
          byPath.get(f.path) ?? {
            path: f.path,
            status: normalizeStatus(f.status),
            additions: f.additions ?? 0,
            deletions: f.deletions ?? 0,
            slice: null,
            isBinary: false,
          },
      );
    })(),
    rawDiff: data.diff,
  };
}
