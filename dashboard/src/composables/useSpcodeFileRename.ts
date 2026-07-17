// Author: elecvoid243
// Date: 2026-07-18
// Vue composable wrapping POST /spcode/file-rename — the generic
// same-dir rename endpoint backing the workspace file-browser editor
// toolbar (PATCH /spcode/docs is markdown-only by design, so code
// files go through this endpoint). Lifecycle mirrors useSpcodeFileWrite.

import { ref, toValue, type MaybeRef } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";

export type FileRenameResult = { ok: true } | { ok: false; reason: string };

export interface UseSpcodeFileRename {
  isRenaming: import("vue").Ref<boolean>;
  rename: (params: {
    path: string;
    newName: string;
  }) => Promise<FileRenameResult>;
  dispose: () => void;
}

export function useSpcodeFileRename(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeFileRename {
  const spcodeStatus = useSpcodeProjectStatus();
  const isRenaming = ref(false);
  let ctrl: AbortController | null = null;
  let isMounted = true;

  async function rename(params: {
    path: string;
    newName: string;
  }): Promise<FileRenameResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    ctrl?.abort();
    ctrl = new AbortController();
    isRenaming.value = true;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/file-rename",
        {
          path: params.path,
          new_name: params.newName,
          umo: spcodeStatus.status.value.umo ?? undefined,
          worktree: toValue(worktreeRef) ?? undefined,
        },
        { signal: ctrl.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      // Envelope semantics mirror useSpcodeFileWrite: `renamed === true`
      // is the success marker; a non-empty `reason` without the marker
      // is a genuine failure; anything unrecognized is treated as success.
      const data = (
        resp.data as {
          data?: { renamed?: boolean; reason?: string | null };
        }
      )?.data;
      if (
        data &&
        data.renamed !== true &&
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
      if (isMounted) isRenaming.value = false;
    }
  }

  function dispose(): void {
    isMounted = false;
    ctrl?.abort();
    ctrl = null;
  }

  return { isRenaming, rename, dispose };
}
