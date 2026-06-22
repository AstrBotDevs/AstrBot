// Author: elecvoid243
// Date: 2026-06-22
// Spec: docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md §4, §6.5
//
// Vue composable wrapping POST /spcode/file-restore. Mirrors the lifecycle
// pattern of useSpcodeGitDiff.ts (single instance per consumer, AbortController
// for cancellation, isMounted guard).

import { ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeFileRestore,
  classifyReason,
  type SpcodeFileRestoreSnapshot,
} from "./parseSpcodeFileRestore";

export interface UseSpcodeFileRestore {
  isRestoring: import("vue").Ref<boolean>;
  restore: (params: RestoreParams) => Promise<RestoreResult>;
  dispose: () => void;
}

export interface RestoreParams {
  file: string;
  worktree?: string | null;
  umo?: string | null;
}

export type RestoreResult =
  | { ok: true; snapshot: SpcodeFileRestoreSnapshot }
  | { ok: false; reason: string; stderr?: string };

export function useSpcodeFileRestore(): UseSpcodeFileRestore {
  const isRestoring = ref(false);
  let abortController: AbortController | null = null;
  let isMounted = true;

  async function restore(params: RestoreParams): Promise<RestoreResult> {
    if (!isMounted) {
      return { ok: false, reason: "aborted" };
    }
    abortController?.abort();
    abortController = new AbortController();
    isRestoring.value = true;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/file-restore",
        {
          file: params.file,
          ...(params.worktree ? { worktree: params.worktree } : {}),
          ...(params.umo ? { umo: params.umo } : {}),
        },
        { signal: abortController.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeFileRestore(resp.data);
      if (parsed.kind !== "ok") {
        return { ok: false, reason: "unknown" };
      }
      const snap = parsed.snapshot;
      if (snap.restored) {
        return { ok: true, snapshot: snap };
      }
      return {
        ok: false,
        reason: classifyReason(snap.reason),
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
      if (isMounted) isRestoring.value = false;
    }
  }

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
  }

  return { isRestoring, restore, dispose };
}