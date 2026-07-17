// Author: elecvoid243
// Date: 2026-07-18
// Vue composable wrapping POST /spcode/file-remove — the generic
// file-delete endpoint backing the workspace file-browser editor
// toolbar (DELETE /spcode/docs is markdown-only by design, so code
// files go through this endpoint). Lifecycle mirrors useSpcodeFileWrite.

import { ref, toValue, type MaybeRef } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";

export type FileRemoveResult = { ok: true } | { ok: false; reason: string };

export interface UseSpcodeFileRemove {
  isRemoving: import("vue").Ref<boolean>;
  remove: (params: { path: string }) => Promise<FileRemoveResult>;
  dispose: () => void;
}

export function useSpcodeFileRemove(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeFileRemove {
  const spcodeStatus = useSpcodeProjectStatus();
  const isRemoving = ref(false);
  let ctrl: AbortController | null = null;
  let isMounted = true;

  async function remove(params: { path: string }): Promise<FileRemoveResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    ctrl?.abort();
    ctrl = new AbortController();
    isRemoving.value = true;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/file-remove",
        {
          path: params.path,
          umo: spcodeStatus.status.value.umo ?? undefined,
          worktree: toValue(worktreeRef) ?? undefined,
        },
        { signal: ctrl.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      // Envelope semantics mirror useSpcodeFileWrite: `deleted === true`
      // is the success marker; a non-empty `reason` without the marker
      // is a genuine failure; anything unrecognized is treated as success.
      const data = (
        resp.data as {
          data?: { deleted?: boolean; reason?: string | null };
        }
      )?.data;
      if (
        data &&
        data.deleted !== true &&
        typeof data.reason === "string" &&
        data.reason
      ) {
        return { ok: false, reason: data.reason };
      }
      return { ok: true };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      const e = err as { name?: string; code?: string; message?: string };
      if (e?.name === "CanceledError") return { ok: false, reason: "aborted" };
      if (e?.code === "ERR_NETWORK" || /network/i.test(e?.message ?? "")) {
        return { ok: false, reason: "network" };
      }
      return { ok: false, reason: "unknown" };
    } finally {
      if (isMounted) isRemoving.value = false;
    }
  }

  function dispose(): void {
    isMounted = false;
    ctrl?.abort();
    ctrl = null;
  }

  return { isRemoving, remove, dispose };
}
