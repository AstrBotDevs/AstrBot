// Author: elecvoid243, 2026-07-02
// State machine for the in-sidebar search feature. Mirrors the
// useSpcodeGitLog pattern (kind: idle | loading | ok | error).
//
// 2026-07-02 revision: adds a Filename / Content mode toggle.
//   - "filename" mode → POST /spcode/file-name-search
//     response shape: {path, name, type: "file"|"dir", size}
//   - "content"  mode → POST /spcode/file-search
//     response shape: {path, line, column, snippet}
//
// 2026-07-02 revision (toolbar input): the search input now lives in
// the GitDiffSidebar toolbar (not in SearchPanel). The composable is
// implemented as a module-level singleton so the toolbar input and
// SearchPanel share the same `query` ref, the same 300ms debounce
// watcher, and the same in-flight AbortController. SearchPanel binds
// to the same `query` ref via destructuring (read + write), and the
// toolbar input writes to it via @input. close() is a one-call reset
// that SearchPanel uses to drop the panel state when the user closes
// the panel via Esc from a search result. The singleton shape is
// correct for this feature because only one search panel can be
// visible at a time.
//
// Mode persists in localStorage["spcode.searchMode"] (key defined
// co-located here; the STORAGE_KEYS object in GitDiffSidebar.vue
// covers panel open/closed state, which is a separate concern).
// SearchResult is now a discriminated union keyed by `mode` so
// SearchPanel can branch rendering with full type safety.
//
// Cancellation: every new search() call aborts the previous in-flight
// request via AbortController. setMode() also cancels any in-flight
// request and resets state to idle (mode change is a hard reset).
// The Vue ref `state` is the single source of truth for the
// SearchPanel UI.

import { ref, watch, type Ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";

export type SearchMode = "filename" | "content";

const STORAGE_KEYS = {
  // 2026-07-02 sidebar-search: persisted search mode for the in-sidebar
  // search panel. Default = "filename" (the new /spcode/file-name-search
  // endpoint). Pre-existing keys live in GitDiffSidebar.vue.
  searchMode: "spcode.searchMode",
} as const;

function loadSearchMode(): SearchMode {
  try {
    const v = localStorage.getItem(STORAGE_KEYS.searchMode);
    if (v === "filename" || v === "content") return v;
  } catch {
    /* localStorage may be unavailable (private browsing, SSR) */
  }
  return "filename";
}

function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* no-op */
  }
}

export type SearchState =
  | { kind: "idle" }
  | { kind: "loading"; query: string }
  | {
      kind: "ok";
      query: string;
      results: SearchResult[];
      truncated: boolean;
      elapsedMs: number;
    }
  | { kind: "error"; query: string; reason: string; elapsedMs: number };

export type SearchResult =
  | {
      mode: "filename";
      path: string;
      name: string;
      type: "file" | "dir";
      size: number;
    }
  | {
      mode: "content";
      path: string;
      line: number;
      column: number;
      snippet: string;
    };

export interface SearchOptions {
  umo: string | null;
  worktree: string | null;
  pattern: string;
  pathFilter?: string;
  globFilter?: string;
  caseSensitive?: boolean;
  regex?: boolean;
  maxResults?: number;
  contextChars?: number;
}

// Common fields shared by both endpoint responses. The `results` field
// shape is mode-specific and is parsed in _parseResults().
interface SearchResponseCommon {
  pattern: string;
  result_count: number;
  max_results: number;
  truncated: boolean;
  reason: string | null;
  elapsed_ms: number;
  results?: unknown;
}

// Parse the backend `results` array into a typed SearchResult[].
// Skips malformed entries silently (the backend is the source of truth
// for shape, but a defensive parse here keeps the UI from crashing on
// a schema drift).
function _parseResults(
  mode: SearchMode,
  data: SearchResponseCommon,
): SearchResult[] {
  const raw = Array.isArray(data.results) ? data.results : [];
  if (mode === "filename") {
    return raw
      .map((r): SearchResult | null => {
        if (!r || typeof r !== "object") return null;
        const o = r as Record<string, unknown>;
        if (
          typeof o.path !== "string" ||
          typeof o.name !== "string" ||
          (o.type !== "file" && o.type !== "dir") ||
          typeof o.size !== "number"
        ) {
          return null;
        }
        return {
          mode: "filename",
          path: o.path,
          name: o.name,
          type: o.type,
          size: o.size,
        };
      })
      .filter((r): r is SearchResult => r !== null);
  }
  // mode === "content"
  return raw
    .map((r): SearchResult | null => {
      if (!r || typeof r !== "object") return null;
      const o = r as Record<string, unknown>;
      if (
        typeof o.path !== "string" ||
        typeof o.line !== "number" ||
        typeof o.column !== "number" ||
        typeof o.snippet !== "string"
      ) {
        return null;
      }
      return {
        mode: "content",
        path: o.path,
        line: o.line,
        column: o.column,
        snippet: o.snippet,
      };
    })
    .filter((r): r is SearchResult => r !== null);
}

// ── Module-level singleton state ──────────────────────────────────
// 2026-07-02 toolbar input: the search <input> now lives in
// GitDiffSidebar (not inside SearchPanel), and both components need
// to read/write the same `query` ref + share the debounce watcher
// + share the in-flight cancellation. A per-call composable would
// create separate instances per component and the two refs would
// not be linked. Hoisting the state to module scope is the
// smallest change that gives both consumers the same backing
// store; only one search panel can be visible at a time anyway,
// so a singleton is semantically correct.
const _state: Ref<SearchState> = ref({ kind: "idle" });
const _mode: Ref<SearchMode> = ref(loadSearchMode());
const _query: Ref<string> = ref("");
let _debounceTimer: ReturnType<typeof setTimeout> | null = null;
// Last umo/worktree captured from the most recent search() call.
// The debounce watcher uses these to re-fire search() with the same
// routing context — callers no longer need to push context into
// the input's @input handler. Null until the first search() call.
let _lastUmo: string | null = null;
let _lastWorktree: string | null = null;
let _inflight: AbortController | null = null;

// Persist mode changes to localStorage. Mirrors the pattern used by
// GitDiffSidebar.vue (watch + safeSetItem, flush:"post" to coalesce
// bursts). Watcher is not `immediate`, so the initial load from
// localStorage does not trigger a redundant write. Registered once
// at module load — a singleton watcher covers all consumers.
watch(_mode, (v) => safeSetItem(STORAGE_KEYS.searchMode, v), {
  flush: "post",
});

// 2026-07-02 toolbar input: debounced auto-search on query change.
// Empty query short-circuits to idle (no API call). Non-empty
// schedules a search 300ms later — multiple keystrokes coalesce
// into one network request, matching the spec's §4.4 timing.
//
// Lives at module scope (singleton) so the toolbar input and
// SearchPanel share the same debounce state. Without this, typing
// in the toolbar wouldn't trigger any search at all (SearchPanel
// would be using a separate `query` ref that the toolbar never
// writes to).
watch(_query, (v) => {
  if (_debounceTimer) {
    clearTimeout(_debounceTimer);
    _debounceTimer = null;
  }
  if (!v.trim()) {
    _cancel();
    _state.value = { kind: "idle" };
    return;
  }
  _debounceTimer = setTimeout(() => {
    void _search({ umo: _lastUmo, worktree: _lastWorktree, pattern: v });
  }, 300);
});

function _cancel(): void {
  if (_inflight) {
    _inflight.abort();
    _inflight = null;
  }
}

// 2026-07-02 toolbar input: full reset. Called when the user
// closes the panel (Esc from a search result, etc.). Clears the
// debounce timer, cancels any in-flight request, empties the
// query (which itself triggers the watcher → state idle), and
// forces state to idle in case the watcher short-circuit didn't
// fire (e.g. query was already empty when close() was called).
function _close(): void {
  if (_debounceTimer) {
    clearTimeout(_debounceTimer);
    _debounceTimer = null;
  }
  _cancel();
  _query.value = "";
  _state.value = { kind: "idle" };
}

function _setMode(newMode: SearchMode): void {
  if (newMode === _mode.value) return;
  _cancel();
  _state.value = { kind: "idle" };
  _mode.value = newMode;
  // watch(_mode) → safeSetItem handles persistence
}

async function _search(opts: SearchOptions): Promise<void> {
  // 2026-07-02 toolbar input: capture the routing context so the
  // debounced watcher can re-fire search() with the same umo/
  // worktree after a later query edit. Done before _cancel() so
  // the captured values survive a synchronous abort.
  _lastUmo = opts.umo;
  _lastWorktree = opts.worktree;
  _cancel();
  if (!opts.pattern || !opts.pattern.trim()) {
    _state.value = { kind: "idle" };
    return;
  }
  const controller = new AbortController();
  _inflight = controller;
  const currentMode = _mode.value;
  _state.value = { kind: "loading", query: opts.pattern };
  const endpoint =
    currentMode === "filename"
      ? "spcode/file-name-search"
      : "spcode/file-search";
  try {
    // pluginExtensionApi.post<T> wraps the response in ApiEnvelope<T>
    // (status, data: T), so T is the inner search-result payload — NOT
    // another { status, data } envelope. The brief draft double-nested
    // the wrapper, which produced TS2339 on data.reason / data.results.
    const res = await pluginExtensionApi.post<SearchResponseCommon>(
      endpoint,
      {
        umo: opts.umo,
        worktree: opts.worktree,
        pattern: opts.pattern,
        path_filter: opts.pathFilter ?? null,
        glob_filter: opts.globFilter ?? null,
        case_sensitive: opts.caseSensitive ?? false,
        regex: opts.regex ?? false,
        max_results: opts.maxResults ?? 200,
        context_chars: opts.contextChars ?? 60,
      },
      { signal: controller.signal },
    );
    // If a newer search already started, drop this response
    if (controller.signal.aborted) return;
    const data = res.data?.data;
    if (!data) {
      _state.value = {
        kind: "error",
        query: opts.pattern,
        reason: "network_error",
        elapsedMs: 0,
      };
      return;
    }
    if (data.reason) {
      _state.value = {
        kind: "error",
        query: opts.pattern,
        reason: data.reason,
        elapsedMs: data.elapsed_ms ?? 0,
      };
      return;
    }
    _state.value = {
      kind: "ok",
      query: opts.pattern,
      results: _parseResults(currentMode, data),
      truncated: data.truncated ?? false,
      elapsedMs: data.elapsed_ms ?? 0,
    };
  } catch (err: unknown) {
    const e = err as { name?: string; code?: string };
    if (e?.name === "CanceledError" || controller.signal.aborted) return;
    _state.value = {
      kind: "error",
      query: opts.pattern,
      reason: "network_error",
      elapsedMs: 0,
    };
  } finally {
    if (_inflight === controller) _inflight = null;
  }
}

export function useSpcodeFileSearch() {
  // 2026-07-02 toolbar input: thin accessor around the module-level
  // singleton state above. Both GitDiffSidebar (toolbar input) and
  // SearchPanel (results UI) destructure from this return value, so
  // they share the same `query` ref, debounce watcher, and in-flight
  // AbortController. Keep the call-site shape identical to a normal
  // composable so neither consumer needs to know it's a singleton.
  return {
    state: _state,
    mode: _mode,
    query: _query,
    search: _search,
    cancel: _cancel,
    setMode: _setMode,
    close: _close,
  };
}
