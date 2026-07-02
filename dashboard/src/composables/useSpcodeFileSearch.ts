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

export function useSpcodeFileSearch() {
  const state: Ref<SearchState> = ref({ kind: "idle" });
  const mode: Ref<SearchMode> = ref(loadSearchMode());
  let inflight: AbortController | null = null;

  // Persist mode changes to localStorage. Mirrors the pattern used by
  // GitDiffSidebar.vue (watch + safeSetItem, flush:"post" to coalesce
  // bursts). Watcher is not `immediate`, so the initial load from
  // localStorage does not trigger a redundant write.
  watch(mode, (v) => safeSetItem(STORAGE_KEYS.searchMode, v), {
    flush: "post",
  });

  function cancel(): void {
    if (inflight) {
      inflight.abort();
      inflight = null;
    }
  }

  function setMode(newMode: SearchMode): void {
    if (newMode === mode.value) return;
    cancel();
    state.value = { kind: "idle" };
    mode.value = newMode;
    // watch(mode) → safeSetItem handles persistence
  }

  async function search(opts: SearchOptions): Promise<void> {
    cancel();
    if (!opts.pattern || !opts.pattern.trim()) {
      state.value = { kind: "idle" };
      return;
    }
    const controller = new AbortController();
    inflight = controller;
    const currentMode = mode.value;
    state.value = { kind: "loading", query: opts.pattern };
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
        state.value = {
          kind: "error",
          query: opts.pattern,
          reason: "network_error",
          elapsedMs: 0,
        };
        return;
      }
      if (data.reason) {
        state.value = {
          kind: "error",
          query: opts.pattern,
          reason: data.reason,
          elapsedMs: data.elapsed_ms ?? 0,
        };
        return;
      }
      state.value = {
        kind: "ok",
        query: opts.pattern,
        results: _parseResults(currentMode, data),
        truncated: data.truncated ?? false,
        elapsedMs: data.elapsed_ms ?? 0,
      };
    } catch (err: unknown) {
      const e = err as { name?: string; code?: string };
      if (e?.name === "CanceledError" || controller.signal.aborted) return;
      state.value = {
        kind: "error",
        query: opts.pattern,
        reason: "network_error",
        elapsedMs: 0,
      };
    } finally {
      if (inflight === controller) inflight = null;
    }
  }

  return { state, mode, search, cancel, setMode };
}
