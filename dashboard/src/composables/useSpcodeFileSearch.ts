// Author: elecvoid243, 2026-07-02
// State machine for the in-sidebar search feature. Mirrors the
// useSpcodeGitLog pattern (kind: idle | loading | ok | error).
//
// Cancellation: every new search() call aborts the previous in-flight
// request via AbortController. The Vue ref `state` is the single source
// of truth for the SearchPanel UI.

import { ref, type Ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";

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

export interface SearchResult {
  path: string;
  line: number;
  column: number;
  snippet: string;
}

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

export function useSpcodeFileSearch() {
  const state: Ref<SearchState> = ref({ kind: "idle" });
  let inflight: AbortController | null = null;

  function cancel(): void {
    if (inflight) {
      inflight.abort();
      inflight = null;
    }
  }

  async function search(opts: SearchOptions): Promise<void> {
    cancel();
    if (!opts.pattern || !opts.pattern.trim()) {
      state.value = { kind: "idle" };
      return;
    }
    const controller = new AbortController();
    inflight = controller;
    state.value = { kind: "loading", query: opts.pattern };
    try {
      // pluginExtensionApi.post<T> wraps the response in ApiEnvelope<T>
      // (status, data: T), so T is the inner search-result payload — NOT
      // another { status, data } envelope. The brief draft double-nested
      // the wrapper, which produced TS2339 on data.reason / data.results.
      const res = await pluginExtensionApi.post<{
        pattern: string;
        result_count: number;
        max_results: number;
        truncated: boolean;
        results: SearchResult[];
        reason: string | null;
        elapsed_ms: number;
      }>(
        "spcode/file-search",
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
        results: data.results ?? [],
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

  return { state, search, cancel };
}
