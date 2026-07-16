// Author: elecvoid243
// Date: 2026-06-17 (updated 2026-06-20 to thread the `scope` parameter)
// Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.1.2
//      + docs/superpowers/specs/2026-06-20-git-diff-scope-switcher-design.md §4.1

import { ref, toValue, watch, type Ref, type MaybeRef } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import {
  parseSpcodeGitDiff,
  type GitDiffScope,
  type SpcodeGitDiffSnapshot,
  type SpcodeGitDiffRawResponse,
} from "@/composables/parseSpcodeGitDiff";

export type { GitDiffScope } from "@/composables/parseSpcodeGitDiff";

/** Default scope matches spcode plugin v3.1 (unstaged = plain `git diff`). */
export const DEFAULT_SCOPE: GitDiffScope = "unstaged";

export type GitDiffFetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; snapshot: SpcodeGitDiffSnapshot }
  | { kind: "error"; reason: string; previousSnapshot?: SpcodeGitDiffSnapshot };

export interface UseSpcodeGitDiff {
  state: Ref<GitDiffFetchState>;
  refresh: () => Promise<void>;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
  dispose: () => void;
}

const DEFAULT_POLL_MS = 10_000;

export function useSpcodeGitDiff(
  worktreeRef: MaybeRef<string | null> = null,
  scopeRef: MaybeRef<GitDiffScope> = DEFAULT_SCOPE,
): UseSpcodeGitDiff {
  const state = ref<GitDiffFetchState>({ kind: "idle" });
  const spcodeStatus = useSpcodeProjectStatus();
  let abortController: AbortController | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let isMounted = true;

  async function refresh(): Promise<void> {
    if (!isMounted) return;
    const umo = spcodeStatus.status.value.umo;
    if (!umo) {
      const prev = state.value.kind === "ok" ? state.value.snapshot : undefined;
      state.value = {
        kind: "error",
        reason: "no_project_loaded",
        previousSnapshot: prev,
      };
      return;
    }
    abortController?.abort();
    abortController = new AbortController();
    const isFirst = state.value.kind !== "ok";
    if (isFirst) state.value = { kind: "loading" };
    try {
      const worktree = toValue(worktreeRef);
      const scope = toValue(scopeRef);
      const resp = await pluginExtensionApi.get<SpcodeGitDiffRawResponse>(
        "spcode/git-diff",
        {
          params: {
            umo,
            scope,
            ...(worktree ? { worktree } : {}),
          },
          signal: abortController.signal,
        },
      );
      if (!isMounted) return;
      const data = resp.data?.data;
      if (!data) throw new Error("empty response data");
      const snapshot = parseSpcodeGitDiff(data);
      // Drift detection: if the server echoed a different scope than
      // the user just selected, log it and let the next poll realign
      // the UI. We do NOT throw — the snapshot is still valid, just
      // potentially stale (e.g. a slow request was overtaken by a
      // newer one with a different scope).
      if (snapshot.meta.scope && snapshot.meta.scope !== scope) {
        console.warn(
          `[useSpcodeGitDiff] scope drift: requested=${scope} echoed=${snapshot.meta.scope}`,
        );
      }
      state.value = { kind: "ok", snapshot };
    } catch (err) {
      if (!isMounted) return;
      if ((err as { name?: string })?.name === "CanceledError") return;
      const prev = state.value.kind === "ok" ? state.value.snapshot : undefined;
      state.value = {
        kind: "error",
        reason: classifyError(err),
        previousSnapshot: prev,
      };
    }
  }

  function startPolling(intervalMs: number = DEFAULT_POLL_MS): void {
    if (pollTimer) return;
    pollTimer = setInterval(() => {
      void refresh();
    }, intervalMs);
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  // Re-fetch when the user picks a different worktree OR a different
  // scope. Watching both in a single watcher keeps the request order
  // deterministic (only one in-flight at a time, controlled by the
  // abortController inside refresh()).
  watch(
    [() => toValue(worktreeRef), () => toValue(scopeRef)],
    () => {
      if (isMounted) void refresh();
    },
    { flush: "post" },
  );

  watch(
    () => spcodeStatus.status.value.umo,
    (newUmo, oldUmo) => {
      if (!isMounted) return;
      if (newUmo && newUmo !== oldUmo) {
        void refresh();
      }
    },
  );
  watch(
    () => spcodeStatus.status.value.directory,
    (newDir, oldDir) => {
      if (!isMounted) return;
      if (newDir && newDir !== oldDir && spcodeStatus.status.value.umo) {
        void refresh();
      }
    },
  );

  function dispose(): void {
    isMounted = false;
    stopPolling();
    abortController?.abort();
    abortController = null;
  }

  return { state, refresh, startPolling, stopPolling, dispose };
}

function classifyError(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const anyErr = err as { code?: string; message?: string };
    if (
      anyErr.code === "ERR_NETWORK" ||
      /network/i.test(anyErr.message ?? "")
    ) {
      return "network";
    }
  }
  return "unknown";
}
