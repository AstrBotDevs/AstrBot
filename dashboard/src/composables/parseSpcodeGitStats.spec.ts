// Author: elecvoid243, 2026-07-18
// Spec: docs/superpowers/specs/2026-07-18-git-stats-heatmap-design.md
// Tests exercise the parser with the actual wire shape produced by the
// plugin's GET /spcode/git-stats endpoint (envelope: {status, data}).

import { describe, expect, it } from "vitest";
import {
  parseSpcodeGitStats,
  rangeForPreset,
  STATS_PRESETS,
} from "./parseSpcodeGitStats";

function envelope(data: Record<string, unknown>) {
  return { status: "ok", data };
}

function fullData(overrides: Record<string, unknown> = {}) {
  return {
    loaded: true,
    umo: "webchat:FriendMessage:x",
    worktree: null,
    directory: "F:/repo",
    ref: "HEAD",
    resolved_sha: "abc123",
    days: [
      { date: "2026-07-10", commits: 2, additions: 8, deletions: 2 },
      { date: "2026-07-12", commits: 1, additions: 3, deletions: 3 },
    ],
    hot_files: [
      { path: "a.py", commits: 3, additions: 9, deletions: 5 },
      { path: "b.py", commits: 1, additions: 2, deletions: 0 },
    ],
    totals: { commits: 3, additions: 11, deletions: 5, files_changed: 2 },
    range: { first: "2026-07-10", last: "2026-07-12" },
    truncated: false,
    max_commits: 5000,
    reason: null,
    stderr: "",
    elapsed_ms: 230,
    ...overrides,
  };
}

describe("parseSpcodeGitStats", () => {
  it("parses a full success envelope", () => {
    const r = parseSpcodeGitStats(envelope(fullData()));
    expect(r.kind).toBe("ok");
    if (r.kind !== "ok") return;
    const s = r.snapshot;
    expect(s.success).toBe(true);
    expect(s.reason).toBeNull();
    expect(s.days).toEqual([
      { date: "2026-07-10", commits: 2, additions: 8, deletions: 2 },
      { date: "2026-07-12", commits: 1, additions: 3, deletions: 3 },
    ]);
    expect(s.hotFiles).toEqual([
      { path: "a.py", commits: 3, additions: 9, deletions: 5 },
      { path: "b.py", commits: 1, additions: 2, deletions: 0 },
    ]);
    expect(s.totals).toEqual({
      commits: 3,
      additions: 11,
      deletions: 5,
      filesChanged: 2,
    });
    expect(s.range).toEqual({ first: "2026-07-10", last: "2026-07-12" });
    expect(s.truncated).toBe(false);
    expect(s.maxCommits).toBe(5000);
    expect(s.resolvedSha).toBe("abc123");
    expect(s.elapsedMs).toBe(230);
  });

  it("derives success=false from a non-null reason (deriveSuccess)", () => {
    const r = parseSpcodeGitStats(
      envelope(fullData({ reason: "git_error", loaded: false })),
    );
    expect(r.kind).toBe("ok");
    if (r.kind !== "ok") return;
    expect(r.snapshot.success).toBe(false);
    expect(r.snapshot.reason).toBe("git_error");
  });

  it("preserves an explicit success field when present", () => {
    const r = parseSpcodeGitStats(
      envelope(fullData({ success: true, reason: "weird" })),
    );
    expect(r.kind).toBe("ok");
    if (r.kind !== "ok") return;
    expect(r.snapshot.success).toBe(true);
  });

  it("falls back to defaults for missing optional fields", () => {
    const r = parseSpcodeGitStats(envelope({ reason: null }));
    expect(r.kind).toBe("ok");
    if (r.kind !== "ok") return;
    const s = r.snapshot;
    expect(s.days).toEqual([]);
    expect(s.hotFiles).toEqual([]);
    expect(s.totals).toEqual({
      commits: 0,
      additions: 0,
      deletions: 0,
      filesChanged: 0,
    });
    expect(s.range).toEqual({ first: null, last: null });
    expect(s.ref).toBe("HEAD");
    expect(s.truncated).toBe(false);
    expect(s.maxCommits).toBe(5000);
    expect(s.umo).toBeNull();
  });

  it("coerces non-array days / hot_files to empty arrays", () => {
    const r = parseSpcodeGitStats(
      envelope(fullData({ days: "oops", hot_files: 42 })),
    );
    expect(r.kind).toBe("ok");
    if (r.kind !== "ok") return;
    expect(r.snapshot.days).toEqual([]);
    expect(r.snapshot.hotFiles).toEqual([]);
  });

  it("returns error on a malformed envelope (missing data)", () => {
    const r = parseSpcodeGitStats({ status: "ok" });
    expect(r.kind).toBe("error");
  });

  it("returns error on a non-ok status envelope", () => {
    const r = parseSpcodeGitStats({ status: "error", data: {} });
    expect(r.kind).toBe("error");
  });
});


describe("GitStatsRange helpers", () => {
  it("STATS_PRESETS contains exactly the 5 documented presets in order", () => {
    expect(STATS_PRESETS.map((p) => p.key)).toEqual([
      "1w",
      "1mo",
      "3mo",
      "6mo",
      "1y",
    ]);
  });

  it("rangeForPreset('6mo') produces 26-week since anchored at today's Sunday", () => {
    // Fixed today = Wed 2026-07-15 (getDay() === 3)
    const today = new Date(2026, 6, 15);
    const { since, until } = rangeForPreset("6mo", today);
    expect(until).toBe("2026-07-15");
    // 26 weeks -> since = today.Sunday - 25 weeks
    // today.Sunday = 2026-07-12, minus 25*7 days = 2026-01-18
    expect(since).toBe("2026-01-18");
  });

  it("rangeForPreset('1w') produces since === the preceding Sunday (1-column)", () => {
    const today = new Date(2026, 1, 18); // Wed Feb 18
    const { since, until } = rangeForPreset("1w", today);
    expect(until).toBe("2026-02-18");
    expect(since).toBe("2026-02-15"); // the preceding Sunday
  });

  it("rangeForPreset always yields since <= until", () => {
    for (const p of STATS_PRESETS) {
      const { since, until } = rangeForPreset(p.key, new Date(2026, 6, 15));
      expect(since <= until).toBe(true);
    }
  });
});
