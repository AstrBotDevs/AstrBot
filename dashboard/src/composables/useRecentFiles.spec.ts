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
