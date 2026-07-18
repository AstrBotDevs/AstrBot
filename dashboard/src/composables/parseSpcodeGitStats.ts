// Author: elecvoid243
// Date: 2026-07-18
// Spec: docs/superpowers/specs/2026-07-18-git-stats-heatmap-design.md
//
// Parser for GET /spcode/git-stats. Mirrors parseSpcodeGitShow.ts:
// envelope unwrap + field normalization into a discriminated result.

export interface GitStatsDay {
  /** "YYYY-MM-DD" author-local date. */
  date: string;
  commits: number;
  additions: number;
  deletions: number;
}

export interface GitStatsHotFile {
  path: string;
  commits: number;
  additions: number;
  deletions: number;
}

export interface GitStatsData {
  // Envelope fields
  success: boolean;
  reason: string | null;
  loaded: boolean;
  stderr: string;
  elapsedMs: number;
  umo: string | null;
  worktree: string | null;
  directory: string | null;

  // Stats payload
  ref: string;
  resolvedSha: string;
  days: GitStatsDay[];
  hotFiles: GitStatsHotFile[];
  totals: {
    commits: number;
    additions: number;
    deletions: number;
    filesChanged: number;
  };
  range: { first: string | null; last: string | null };
  truncated: boolean;
  maxCommits: number;
}

export type ParseResult<T> =
  | { kind: "ok"; snapshot: T }
  | { kind: "error"; reason: string };

// ─── Helpers ───────────────────────────────────────────────────────

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
function asNumber(v: unknown, fallback = 0): number {
  return typeof v === "number" ? v : fallback;
}
function asBoolean(v: unknown, fallback = false): boolean {
  return typeof v === "boolean" ? v : fallback;
}
function asStringOrNull(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

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

/** Mirror parseSpcodeGitShow.deriveSuccess: backend never writes
 *  `success`; the canonical indicator is `reason === null`. */
function deriveSuccess(d: { success?: unknown; reason?: unknown }): boolean {
  if (d.success !== undefined) return asBoolean(d.success);
  return d.reason === null;
}

// ─── Public parser ─────────────────────────────────────────────────

/** Parse the envelope from GET /spcode/git-stats. */
export function parseSpcodeGitStats(raw: unknown): ParseResult<GitStatsData> {
  try {
    const d = unwrapEnvelope(raw) as Record<string, unknown>;

    const rawDays = Array.isArray(d.days) ? d.days : [];
    const days: GitStatsDay[] = rawDays.map((x) => {
      const d0 = x as Record<string, unknown>;
      return {
        date: asString(d0.date),
        commits: asNumber(d0.commits),
        additions: asNumber(d0.additions),
        deletions: asNumber(d0.deletions),
      };
    });

    const rawHot = Array.isArray(d.hot_files) ? d.hot_files : [];
    const hotFiles: GitStatsHotFile[] = rawHot.map((x) => {
      const f0 = x as Record<string, unknown>;
      return {
        path: asString(f0.path),
        commits: asNumber(f0.commits),
        additions: asNumber(f0.additions),
        deletions: asNumber(f0.deletions),
      };
    });

    const t = (d.totals ?? {}) as Record<string, unknown>;
    const rg = (d.range ?? {}) as Record<string, unknown>;

    return {
      kind: "ok",
      snapshot: {
        success: deriveSuccess(d),
        reason: asStringOrNull(d.reason),
        loaded: asBoolean(d.loaded),
        stderr: asString(d.stderr),
        elapsedMs: asNumber(d.elapsed_ms),
        umo: asStringOrNull(d.umo),
        worktree: asStringOrNull(d.worktree),
        directory: asStringOrNull(d.directory),
        ref: asString(d.ref, "HEAD"),
        resolvedSha: asString(d.resolved_sha),
        days,
        hotFiles,
        totals: {
          commits: asNumber(t.commits),
          additions: asNumber(t.additions),
          deletions: asNumber(t.deletions),
          filesChanged: asNumber(t.files_changed),
        },
        range: {
          first: asStringOrNull(rg.first),
          last: asStringOrNull(rg.last),
        },
        truncated: asBoolean(d.truncated),
        maxCommits: asNumber(d.max_commits, 5000),
      },
    };
  } catch (e) {
    return {
      kind: "error",
      reason: e instanceof Error ? e.message : "parse_error",
    };
  }
}
