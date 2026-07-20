// Author: elecvoid243, 2026-07-20
// Spec: docs/superpowers/specs/2026-07-20-recent-files-design.md §10.1
// useRecentFiles unit tests — Task 1 covers types, storage helpers,
// and loadBucket (initial-load semantics). Later Tasks append suites
// for recordOpen / remove / clear / worktree-switching.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { useRecentFiles } from "@/composables/useRecentFiles";

const WT = "/tmp/worktrees/recent-files-demo";

beforeEach(() => {
  localStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("initial load", () => {
  it("returns an empty list when localStorage has no bucket", () => {
    const wt = ref<string | null>(WT);
    const { entries } = useRecentFiles(wt);
    expect(entries.value).toEqual([]);
  });

  it("returns an empty list when currentRoot is null", () => {
    const wt = ref<string | null>(null);
    const { entries } = useRecentFiles(wt);
    expect(entries.value).toEqual([]);
  });

  it("returns prior entries when the bucket exists and parses correctly", () => {
    const prior = [{ path: `${WT}/src/main.py`, openedAt: 1700000000000 }];
    localStorage.setItem(
      `spcode.recentFiles.${fnv1aHex(WT)}`,
      JSON.stringify({ entries: prior }),
    );
    const wt = ref<string | null>(WT);
    const { entries } = useRecentFiles(wt);
    expect(entries.value).toEqual(prior);
  });

  it("falls back to empty list when the stored JSON is malformed", () => {
    localStorage.setItem(`spcode.recentFiles.${fnv1aHex(WT)}`, "{not json");
    const wt = ref<string | null>(WT);
    const { entries } = useRecentFiles(wt);
    expect(entries.value).toEqual([]);
  });
});

describe("recordOpen", () => {
  it("appends a new entry to the head", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen(`${WT}/src/main.py`);
    expect(entries.value).toHaveLength(1);
    expect(entries.value[0].path).toBe(`${WT}/src/main.py`);
    expect(typeof entries.value[0].openedAt).toBe("number");
  });

  it("treats a repeat open of the same path as no new row, refreshed to head", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    recordOpen(`${WT}/b.py`);
    recordOpen(`${WT}/a.py`); // duplicate
    expect(entries.value.map((e) => e.path)).toEqual([
      `${WT}/a.py`,
      `${WT}/b.py`,
    ]);
    // head 'a' should have a newer openedAt than the bottom 'b'
    expect(entries.value[0].openedAt).toBeGreaterThanOrEqual(
      entries.value[1].openedAt,
    );
  });

  it("orders latest-open first across three distinct paths", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    recordOpen(`${WT}/b.py`);
    recordOpen(`${WT}/c.py`);
    expect(entries.value.map((e) => e.path)).toEqual([
      `${WT}/c.py`,
      `${WT}/b.py`,
      `${WT}/a.py`,
    ]);
  });

  it("rejects paths outside the current worktree (no pollution)", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen(`/some/other/project/x.py`);
    expect(entries.value).toEqual([]);
  });

  it("rejects when the current worktree root is null", () => {
    const wt = ref<string | null>(null);
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen("/anything");
    expect(entries.value).toEqual([]);
  });

  it("trims to MAX_ENTRIES (50), dropping the oldest entry", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen } = useRecentFiles(wt);
    for (let i = 0; i < 55; i++) {
      recordOpen(`${WT}/file-${String(i).padStart(2, "0")}.py`);
    }
    expect(entries.value).toHaveLength(50);
    // LIFO order: head = newest (file-54), tail = oldest survivor (file-05).
    // The first five (file-00 .. file-04) should have been dropped.
    expect(entries.value[0].path).toBe(`${WT}/file-54.py`);
    expect(entries.value.at(-1)?.path).toBe(`${WT}/file-05.py`);
  });

  it("persists to localStorage on every recordOpen", () => {
    const wt = ref<string | null>(WT);
    const { recordOpen } = useRecentFiles(wt);
    recordOpen(`${WT}/main.py`);
    const raw = localStorage.getItem(
      `spcode.recentFiles.${fnv1aHex(WT)}`,
    );
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.entries).toHaveLength(1);
    expect(parsed.entries[0].path).toBe(`${WT}/main.py`);
  });
});

describe("remove", () => {
  it("drops the row whose path matches exactly", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen, remove } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    recordOpen(`${WT}/b.py`);
    remove(`${WT}/a.py`);
    expect(entries.value.map((e) => e.path)).toEqual([`${WT}/b.py`]);
  });

  it("is a no-op when the path is not present", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen, remove } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    remove(`${WT}/nope.py`);
    expect(entries.value.map((e) => e.path)).toEqual([`${WT}/a.py`]);
  });

  it("persists the trimmed list", () => {
    const wt = ref<string | null>(WT);
    const { recordOpen, remove } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    recordOpen(`${WT}/b.py`);
    remove(`${WT}/a.py`);
    const raw = JSON.parse(
      localStorage.getItem(`spcode.recentFiles.${fnv1aHex(WT)}`)!,
    );
    expect(raw.entries.map((e: { path: string }) => e.path)).toEqual([
      `${WT}/b.py`,
    ]);
  });
});

describe("clear", () => {
  it("empties the current bucket", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen, clear } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    recordOpen(`${WT}/b.py`);
    clear();
    expect(entries.value).toEqual([]);
  });

  it("persists the empty list", () => {
    const wt = ref<string | null>(WT);
    const { recordOpen, clear } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    clear();
    const raw = JSON.parse(
      localStorage.getItem(`spcode.recentFiles.${fnv1aHex(WT)}`)!,
    );
    expect(raw.entries).toEqual([]);
  });

  it("does not affect other buckets", () => {
    const wtA = ref<string | null>("/worktrees/A");
    const wtB = ref<string | null>("/worktrees/B");
    const a = useRecentFiles(wtA);
    const b = useRecentFiles(wtB);
    a.recordOpen("/worktrees/A/foo.py");
    b.recordOpen("/worktrees/B/bar.py");

    a.clear();
    expect(a.entries.value).toEqual([]);
    expect(b.entries.value.map((e) => e.path)).toEqual(["/worktrees/B/bar.py"]);
  });
});

describe("worktree switching", () => {
  it("reloads the bucket when worktree ref changes", async () => {
    const wt = ref<string | null>("/worktrees/A");
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen("/worktrees/A/a.py");

    // Pre-seed B's bucket so we can confirm we read B and discard A.
    localStorage.setItem(
      `spcode.recentFiles.${fnv1aHex("/worktrees/B")}`,
      JSON.stringify({
        entries: [{ path: "/worktrees/B/b.py", openedAt: 123 }],
      }),
    );

    wt.value = "/worktrees/B";
    await Promise.resolve(); // flush watcher microtask
    expect(entries.value.map((e) => e.path)).toEqual(["/worktrees/B/b.py"]);
  });

  it("shows an empty list when switching to a brand-new worktree", async () => {
    const wt = ref<string | null>("/worktrees/A");
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen("/worktrees/A/a.py");

    wt.value = "/worktrees/C"; // never seen
    await Promise.resolve();
    expect(entries.value).toEqual([]);
  });

  it("writing to a new worktree after switching does not touch the old bucket", async () => {
    const wt = ref<string | null>("/worktrees/A");
    const { recordOpen } = useRecentFiles(wt);
    recordOpen("/worktrees/A/a.py");
    const aRawBefore = localStorage.getItem(
      `spcode.recentFiles.${fnv1aHex("/worktrees/A")}`,
    );
    const parsedA = JSON.parse(aRawBefore!);
    expect(parsedA.entries[0].path).toBe("/worktrees/A/a.py");

    wt.value = "/worktrees/B";
    await Promise.resolve();
    const { recordOpen: recB } = useRecentFiles(wt);
    recB("/worktrees/B/b.py");

    const aRawAfter = localStorage.getItem(
      `spcode.recentFiles.${fnv1aHex("/worktrees/A")}`,
    );
    expect(aRawAfter).toBe(aRawBefore);
  });
});

// Mirror of the composable's FNV-1a — duplicated here so the test file
// is self-contained and not coupled to internals. The two
// implementations MUST stay byte-identical for the spec to hold.
function fnv1aHex(input: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}
