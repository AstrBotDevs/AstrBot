// Author: elecvoid243
// Date: 2026-06-24
// Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md
//      (extension: merge git-status untracked/intent_to_add into the
//      unstaged view).
//
// Vue composable wrapping GET /spcode/git-status (spcode plugin v2.13+).
// Lifecycle mirrors useSpcodeGitDiff.ts so the orchestrator
// (GitDiffSidebar.vue) can manage a single refresh/poll timer per
// sidebar instance. ETag handling is NOT needed here because the
// sidebar refreshes git-status together with git-diff (same cadence,
// same abort controller isn't strictly required but reduces flicker).

import {
  ref,
  toValue,
  watch,
  type Ref,
  type MaybeRef,
} from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import {
  parseSpcodeGitStatus,
  type SpcodeGitStatusSnapshot,
  type SpcodeGitStatusRawResponse,
} from "./parseSpcodeGitStatus";

export type GitStatusFetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; snapshot: SpcodeGitStatusSnapshot }
  | { kind: "error"; reason: string; previousSnapshot?: SpcodeGitStatusSnapshot };

export interface UseSpcodeGitStatus {
  state: Ref<GitStatusFetchState>;
  refresh: () => Promise<void>;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
  dispose: () => void;
}

const DEFAULT_POLL_MS = 10_000;

export function useSpcodeGitStatus(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeGitStatus {
  const state = ref<GitStatusFetchState>({ kind: "idle" });
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
      const resp = await pluginExtensionApi.get<SpcodeGitStatusRawResponse>(
        "spcode/git-status",
        {
          params: {
            umo,
            ...(worktree ? { worktree } : {}),
          },
          signal: abortController.signal,
        },
      );
      if (!isMounted) return;
      const data = resp.data?.data;
      if (!data) throw new Error("empty response data");
      const snapshot = parseSpcodeGitStatus(data);
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

  // Refetch when worktree changes; umo changes are handled by the
  // orchestrator (which calls refresh() after project-switch).
  watch(
    () => toValue(worktreeRef),
    () => {
      if (isMounted) void refresh();
    },
    { flush: "post" },
  );

  // Refetch when the project umo or directory changes (e.g. initial
  // project load, project switch). Without these, git-status stays
  // "idle" on first open when no (additional) worktrees exist,
  // causing diffBodyState to skip the untracked-files merge.
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