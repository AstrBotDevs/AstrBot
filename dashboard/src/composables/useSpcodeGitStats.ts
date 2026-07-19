// Author: elecvoid243
// Date: 2026-07-18
// Spec: docs/superpowers/specs/2026-07-18-git-stats-heatmap-design.md
//
// Vue composable wrapping GET /spcode/git-stats. Single-snapshot
// (whole-repo stats for the active worktree) mirroring the
// useSpcodeGitLog state machine, minus polling / loadMore / filters:
// the stats request has no varying query dimensions in v1 (always
// ref=HEAD, whole repo), so the ETag key is umo|worktree only.

import { ref, toValue, type MaybeRef, type Ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import {
  parseSpcodeGitStats,
  type GitStatsData,
} from "./parseSpcodeGitStats";

export type GitStatsFetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; snapshot: GitStatsData; notModified?: boolean }
  | { kind: "error"; reason: string; previousSnapshot?: GitStatsData };

export interface UseSpcodeGitStats {
  state: Ref<GitStatsFetchState>;
  refresh: (options?: {
    forceLoading?: boolean;
    since?: string;
    until?: string;
    /** Server-side hot-files cap. Backend allows 1..50; UI clamps 5..50. */
    topFiles?: number;
  }) => Promise<void>;
  /** Clear the ETag map (worktree / umo switch). */
  invalidateEtag: () => void;
  dispose: () => void;
}

export function useSpcodeGitStats(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeGitStats {
  const state = ref<GitStatsFetchState>({ kind: "idle" });
  const spcodeStatus = useSpcodeProjectStatus();
  // ETag + previous snapshot keyed by umo|worktree|topFiles so a
  // user changing the hot-files cap in the panel gets a fresh fetch
  // instead of replaying the previous cap's snapshot.
  const etagMap = new Map<string, string>();
  const prevSnapshotMap = new Map<string, GitStatsData>();
  let abortController: AbortController | null = null;
  let isMounted = true;

  function etagKey(
    umo: string,
    worktree: string | null,
    since: string,
    until: string,
    topFiles: number,
  ): string {
    return [umo, worktree ?? "", since, until, topFiles].join("|");
  }

  async function refresh(options?: {
    forceLoading?: boolean;
    since?: string;
    until?: string;
    topFiles?: number;
  }): Promise<void> {
    if (!isMounted) return;
    const umo = spcodeStatus.status.value.umo;
    if (!umo) {
      state.value = { kind: "error", reason: "no_project_loaded" };
      return;
    }
    abortController?.abort();
    abortController = new AbortController();
    // loading only on the first fetch (or when the caller explicitly
    // wants visual feedback); 304 short-circuits never enter loading.
    if (state.value.kind !== "ok" || options?.forceLoading) {
      state.value = { kind: "loading" };
    }
    const worktree = toValue(worktreeRef);
    const since = options?.since ?? "";
    const until = options?.until ?? "";
    // The backend's hard cap is 50; the UI's user-facing cap is 50
    // (5..50). Clamp here too so a misbehaving caller can't trigger
    // a 400 INVALID_PARAM envelope on every refresh.
    const requestedTop = options?.topFiles ?? 10;
    const topFiles = Math.min(50, Math.max(1, Math.floor(requestedTop)));
    const key = etagKey(umo, worktree, since, until, topFiles);
    const etag = etagMap.get(key);
    try {
      const resp = await pluginExtensionApi.get<unknown>("spcode/git-stats", {
        params: {
          umo,
          ...(worktree ? { worktree } : {}),
          ...(since ? { since } : {}),
          ...(until ? { until } : {}),
          top_files: topFiles,
        },
        headers: etag ? { "If-None-Match": etag } : {},
        // Surface 304 as a valid response (default axios would throw).
        validateStatus: (s) => (s >= 200 && s < 300) || s === 304,
        signal: abortController.signal,
      });
      if (!isMounted) return;

      if (resp.status === 304) {
        const cached = prevSnapshotMap.get(key);
        if (cached) {
          state.value = { kind: "ok", snapshot: cached, notModified: true };
        }
        return;
      }

      const parsed = parseSpcodeGitStats(resp.data);
      if (parsed.kind !== "ok") {
        state.value = {
          kind: "error",
          reason: parsed.reason,
          previousSnapshot: prevSnapshotMap.get(key) ?? undefined,
        };
        return;
      }
      const snap = parsed.snapshot;
      // Business failure (git_error / not_a_git_repo / empty_repository
      // / ...) rides a 200 envelope with success=false — route to the
      // error state with the raw ReasonCode (mirrors useSpcodeGitLog).
      if (!snap.success) {
        state.value = {
          kind: "error",
          reason: snap.reason ?? "unknown",
          previousSnapshot: prevSnapshotMap.get(key) ?? undefined,
        };
        return;
      }
      prevSnapshotMap.set(key, snap);
      const newEtag =
        (resp.headers as Record<string, string> | undefined)?.["etag"] ??
        (resp.headers as Record<string, string> | undefined)?.["ETag"];
      if (newEtag) etagMap.set(key, newEtag);
      state.value = { kind: "ok", snapshot: snap, notModified: false };
    } catch (err) {
      if (!isMounted) return;
      if ((err as { name?: string })?.name === "CanceledError") return;
      const anyErr = err as { code?: string; message?: string };
      state.value = {
        kind: "error",
        reason:
          anyErr.code === "ERR_NETWORK" ||
          /network/i.test(anyErr.message ?? "")
            ? "network"
            : "unknown",
        previousSnapshot: prevSnapshotMap.get(key) ?? undefined,
      };
    }
  }

  function invalidateEtag(): void {
    etagMap.clear();
  }

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
    etagMap.clear();
    prevSnapshotMap.clear();
  }

  return { state, refresh, invalidateEtag, dispose };
}
