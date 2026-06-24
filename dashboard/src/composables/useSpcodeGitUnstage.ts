// Author: elecvoid243
// Date: 2026-06-24
// Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §3, §5
//
// Symmetric counterpart to useSpcodeGitStage.ts. POST /spcode/git-unstage.
// See useSpcodeGitStage for state-surface docs (Set<string> 行级状态
// + refreshTick 触发响应式更新)。

import { ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeGitUnstage,
  type SpcodeStageSnapshot,
} from "./parseSpcodeGitWorkflow";

export interface UseSpcodeGitUnstage {
  isUnstagingAll: import("vue").Ref<boolean>;
  isUnstaging: import("vue").Ref<Set<string>>;
  refreshTick: import("vue").Ref<number>;
  unstage: (params: UnstageParams) => Promise<UnstageResult>;
  unstageAll: (
    params: Omit<UnstageParams, "files" | "all">,
  ) => Promise<UnstageResult>;
  dispose: () => void;
}

export interface UnstageParams {
  files?: string[];
  all?: boolean;
  worktree?: string | null;
  umo?: string | null;
}

export type UnstageResult =
  | { ok: true; snapshot: SpcodeStageSnapshot }
  | { ok: false; reason: string; stderr?: string };

export function useSpcodeGitUnstage(): UseSpcodeGitUnstage {
  const isUnstagingAll = ref(false);
  const isUnstaging = ref<Set<string>>(new Set<string>());
  const refreshTick = ref(0);
  let abortController: AbortController | null = null;
  let isMounted = true;

  function bump(): void {
    refreshTick.value = refreshTick.value + 1;
  }

  async function unstage(params: UnstageParams): Promise<UnstageResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    abortController?.abort();
    abortController = new AbortController();
    // Reassign `.value` (not in-place .add) so Vue 3 picks up the
    // change — Sets are not natively reactive. `bump()` stays as a
    // safety net for consumers that wire `refreshTick` into a
    // computed as a second dependency.
    const tracked = new Set<string>(params.files ?? []);
    isUnstaging.value = new Set([...isUnstaging.value, ...tracked]);
    bump();

    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-unstage",
        {
          ...(params.files ? { files: params.files } : {}),
          ...(params.all ? { all: params.all } : {}),
          ...(params.worktree ? { worktree: params.worktree } : {}),
          ...(params.umo ? { umo: params.umo } : {}),
        },
        { signal: abortController.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeGitUnstage(resp.data);
      if (parsed.kind !== "ok") {
        return { ok: false, reason: "unknown" };
      }
      const snap = parsed.snapshot;
      if (snap.success) {
        return { ok: true, snapshot: snap };
      }
      // Return the raw ReasonCode string — see useSpcodeGitStage for
      // the rationale (caller runs `classifyReason` exactly once).
      return {
        ok: false,
        reason: snap.reason ?? "unknown",
        stderr: snap.stderr || undefined,
      };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      const anyErr = err as { code?: string; message?: string };
      if (anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")) {
        return { ok: false, reason: "network" };
      }
      return { ok: false, reason: "unknown" };
    } finally {
      // Reassign (see comment above the `tracked` declaration).
      const next = new Set(isUnstaging.value);
      for (const p of tracked) next.delete(p);
      isUnstaging.value = next;
      bump();
    }
  }

  async function unstageAll(
    params: Omit<UnstageParams, "files" | "all">,
  ): Promise<UnstageResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    isUnstagingAll.value = true;
    try {
      return await unstage({ ...params, all: true });
    } finally {
      if (isMounted) isUnstagingAll.value = false;
    }
  }

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
    // Reassign so Vue 3 picks up the clear (Sets are not reactive).
    isUnstaging.value = new Set<string>();
    bump();
  }

  return {
    isUnstagingAll,
    isUnstaging,
    refreshTick,
    unstage,
    unstageAll,
    dispose,
  };
}
