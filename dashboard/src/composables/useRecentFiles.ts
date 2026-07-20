// Author: elecvoid243, 2026-07-20
// Spec: docs/superpowers/specs/2026-07-20-recent-files-design.md §4
// useRecentFiles: Recent files data layer for the Files view.
//
// One bucket per worktree (localStorage key derived from worktreeRoot
// via FNV-1a 32-bit hash), 50-entry LIFO cap, same-path dedupe,
// no-op when currentRoot is null. Pure data — no knowledge of the
// sidebar or FileBrowser — so this composable can be reused by
// future Quick-Open (A1) and any other feature that needs the list.

import { ref, watch, type Ref } from "vue";

const MAX_ENTRIES = 50;

/** One row in the Recent list. LIFO ordered by openedAt desc. */
export interface RecentEntry {
  path: string;
  /** Unix milliseconds. */
  openedAt: number;
}

export interface UseRecentFiles {
  entries: Ref<RecentEntry[]>;
  recordOpen(path: string): void;
  remove(path: string): void;
  clear(): void;
}

interface RecentBucket {
  entries: RecentEntry[];
}

/** FNV-1a 32-bit hash, lowercase hex, zero-padded to 8 chars.
 *  NOT cryptographic — only used to keep localStorage keys short and
 *  free of filesystem separators / unicode quirks. ~10 lines, sync,
 *  zero deps (mirrors the same function in useRecentFiles.spec.ts;
 *  keep the two byte-identical). */
export function fnv1aHex(input: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}

/** localStorage wrapper matching the safe-get/safe-set pattern used in
 *  GitDiffSidebar.vue. Returns "" / no-ops on any exception so quota
 *  / private-mode failures degrade to no-op without throwing. */
function safeGetItem(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}
function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* no-op */
  }
}

/** Resolve current bucket key. Returns "" when no worktree is set so
 *  callers can early-out uniformly. */
function bucketKey(worktreeRoot: string | null): string {
  if (!worktreeRoot) return "";
  try {
    return `spcode.recentFiles.${fnv1aHex(worktreeRoot)}`;
  } catch {
    // Extreme fallback: pathological string inputs. Encode and slice.
    const fallback = encodeURIComponent(worktreeRoot).slice(0, 32);
    return `spcode.recentFiles.rt-${fallback}`;
  }
}

/** Read + JSON.parse a bucket; returns empty list on any error. */
function loadBucket(key: string): RecentEntry[] {
  const raw = safeGetItem(key);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as RecentBucket;
    if (!parsed || !Array.isArray(parsed.entries)) return [];
    return parsed.entries;
  } catch {
    return [];
  }
}

/** Persist a bucket. */
function saveBucket(key: string, entries: RecentEntry[]): void {
  safeSetItem(key, JSON.stringify({ entries } satisfies RecentBucket));
}

/** Worktree-separator detection: Windows root contains '\', others '/'.
 *  Mirrors the spec §6.1 logic exactly. */
function sepOf(root: string): string {
  return root.includes("\\") ? "\\" : "/";
}

export function useRecentFiles(worktree: Ref<string | null>): UseRecentFiles {
  const entries = ref<RecentEntry[]>([]);

  function persist(): void {
    if (!worktree.value) return;
    saveBucket(bucketKey(worktree.value), entries.value);
  }

  /** Load + replace entries from localStorage for the current bucket.
   *  Called on mount and on every worktree-ref change (Task 4 wires
   *  that watcher with `flush: "sync"`). */
  function loadForCurrent(): void {
    if (!worktree.value) {
      entries.value = [];
      return;
    }
    entries.value = loadBucket(bucketKey(worktree.value));
  }

  function recordOpen(path: string): void {
    // Stub — implemented in Task 2.
  }
  function remove(path: string): void {
    // Stub — implemented in Task 3.
  }
  function clear(): void {
    // Stub — implemented in Task 3.
  }

  // Initial load.
  loadForCurrent();

  // Re-load whenever the worktree ref changes. `flush: "sync"` keeps
  // the load deterministic — loadBucket is a single JSON.parse
  // bounded by MAX_ENTRIES, no observable cost.
  watch(worktree, () => loadForCurrent(), { flush: "sync" });

  return { entries, recordOpen, remove, clear };
}
