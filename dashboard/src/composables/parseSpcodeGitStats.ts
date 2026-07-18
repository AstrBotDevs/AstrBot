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

// ── Range types (2026-07-18: spec §"GitStatsRange type") ────────
export type GitStatsRangePreset = "1w" | "1mo" | "3mo" | "6mo" | "1y";

export type GitStatsRange =
  | { kind: "preset"; preset: GitStatsRangePreset }
  | { kind: "custom"; since: string; until: string };

export const STATS_PRESETS: ReadonlyArray<{
  key: GitStatsRangePreset;
  weeks: number;
  days: number;
}> = [
  { key: "1w", weeks: 1, days: 7 },
  { key: "1mo", weeks: 5, days: 35 },
  { key: "3mo", weeks: 13, days: 91 },
  { key: "6mo", weeks: 26, days: 182 },
  { key: "1y", weeks: 52, days: 364 },
];

function fmtYmd(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

export function rangeForPreset(
  p: GitStatsRangePreset,
  today: Date = new Date(),
): { since: string; until: string } {
  const cfg = STATS_PRESETS.find((x) => x.key === p);
  if (!cfg) throw new Error(`unknown preset: ${p}`);
  const todayStart = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate(),
  );
  const sinceDate = new Date(todayStart);
  if (p === "1w") {
    // 2026-07-19 last-7-days fix: the Sunday-anchored math collapses
    // to a 1-day range on Sunday (`endSunday === today`, weeks-1 = 0),
    // so the API returns one day and the heatmap renders one cell +
    // six future-dimmed cells. "最近一周" should always mean the last
    // 7 days, so anchor 6 days back regardless of today's weekday.
    sinceDate.setDate(sinceDate.getDate() - 6);
  } else {
    // Multi-week presets keep the Sunday-anchored "this-and-N-previous
    // weeks" semantic so each column is a Sun–Sat week and the right
    // edge snaps to today's weekday. The future cells past today are
    // dimmed, which is fine because 1mo/3mo/6mo/1y still show many
    // populated columns on Sunday.
    const endSunday = new Date(todayStart);
    endSunday.setDate(endSunday.getDate() - endSunday.getDay());
    sinceDate.setDate(endSunday.getDate() - (cfg.weeks - 1) * 7);
  }
  return { since: fmtYmd(sinceDate), until: fmtYmd(todayStart) };
}

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
