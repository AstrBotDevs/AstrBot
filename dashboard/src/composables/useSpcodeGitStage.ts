// Author: elecvoid243
// Date: 2026-06-24
// Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §3, §5
//
// Vue composable wrapping POST /spcode/git-stage. Mirrors
// useSpcodeFileRestore.ts lifecycle (AbortController + isMounted guard).
//
// State surface:
//   - isStagingAll: boolean (单 sidebar 级的全部暂存 flag)
//   - isStaging:    Set<string> (行级 in-flight 集合,父级派生 has(path))
//   - refreshTick:  number (force response trigger for Set-derived computed)
//
// The Set isn't reactive by default; we bump refreshTick on add/delete
// so callers' `computed` blocks re-evaluate `set.has(path)`.

import { ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeGitStage,
  type SpcodeStageSnapshot,
} from "./parseSpcodeGitWorkflow";

export interface UseSpcodeGitStage {
  isStagingAll: import("vue").Ref<boolean>;
  isStaging: import("vue").Ref<Set<string>>;
  refreshTick: import("vue").Ref<number>;
  stage: (params: StageParams) => Promise<StageResult>;
  stageAll: (params: Omit<StageParams, "files" | "all">) => Promise<StageResult>;
  dispose: () => void;
}

export interface StageParams {
  files?: string[];
  all?: boolean;
  worktree?: string | null;
  umo?: string | null;
}

export type StageResult =
  | { ok: true; snapshot: SpcodeStageSnapshot }
  | { ok: false; reason: string; stderr?: string };

export function useSpcodeGitStage(): UseSpcodeGitStage {
  const isStagingAll = ref(false);
  const isStaging = ref<Set<string>>(new Set<string>());
  const refreshTick = ref(0);
  let abortController: AbortController | null = null;
  let isMounted = true;

  function bump(): void {
    // Force Set-derived computed to re-evaluate; Set itself is not reactive.
    refreshTick.value = refreshTick.value + 1;
  }

  async function stage(params: StageParams): Promise<StageResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    abortController?.abort();
    abortController = new AbortController();

    // Track per-file in-flight for the rows that requested it.
    // Spec §3.2: 同文件 stage+unstage 互斥;不同文件可并发。
    // The orchestrator enforces the mutual exclusion by not calling
    // both at once for the same path; we just track what's in flight.
    // Reassign `.value` (not in-place .add) so Vue 3 picks up the
    // change — Sets are not natively reactive. `bump()` stays as a
    // safety net for consumers that wire `refreshTick` into a
    // computed as a second dependency.
    const tracked = new Set<string>(params.files ?? []);
    isStaging.value = new Set([...isStaging.value, ...tracked]);
    bump();

    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-stage",
        {
          ...(params.files ? { files: params.files } : {}),
          ...(params.all ? { all: params.all } : {}),
          ...(params.worktree ? { worktree: params.worktree } : {}),
          ...(params.umo ? { umo: params.umo } : {}),
        },
        { signal: abortController.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeGitStage(resp.data);
      if (parsed.kind !== "ok") {
        return { ok: false, reason: "unknown" };
      }
      const snap = parsed.snapshot;
      if (snap.success) {
        return { ok: true, snapshot: snap };
      }
      // Return the raw ReasonCode string. The caller (GitDiffSidebar)
      // runs `classifyReason` exactly once to derive the i18n key,
      // color, withStderr, and withReason flags. Returning the i18n
      // key here would cause a second classification that misroutes
      // every reason to the `unknown` fallback and breaks the
      // `withStderr` block for `git_error` / `hook_rejected`.
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
      const next = new Set(isStaging.value);
      for (const p of tracked) next.delete(p);
      isStaging.value = next;
      bump();
    }
  }

  async function stageAll(
    params: Omit<StageParams, "files" | "all">,
  ): Promise<StageResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    isStagingAll.value = true;
    try {
      return await stage({ ...params, all: true });
    } finally {
      // Spec §3.3.3 invariant (IDLE/STAGING_ALL 状态机):STAGING_ALL → IDLE
      // 必须 reset isStagingAll(无论 success / failure / abort 路径)。
      // 注意:这里不需要清 `isStaging` Set —— 内部 stage() 用空 tracked
      // (`params.files` 为 undefined),Set 内容不变;`stage` 自己的 finally
      // 仍会执行(无副作用,因为 tracked 为空)。
      // isMounted guard 防止 dispose 后写入已卸载的 ref。
      if (isMounted) isStagingAll.value = false;
    }
  }

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
    // Reassign so Vue 3 picks up the clear (Sets are not reactive).
    isStaging.value = new Set<string>();
    bump();
  }

  return { isStagingAll, isStaging, refreshTick, stage, stageAll, dispose };
}
