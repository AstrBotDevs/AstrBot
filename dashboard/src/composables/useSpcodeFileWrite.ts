// Author: elecvoid243
// Date: 2026-07-17
// Vue composable wrapping POST /spcode/file-write — the generic
// text-file overwrite endpoint backing the workspace file-browser
// editor (POST /spcode/docs is markdown-only by design, so code files
// go through this endpoint). Lifecycle mirrors useSpcodeDocs.save.

import { ref, toValue, type MaybeRef } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";

export type FileWriteResult = { ok: true } | { ok: false; reason: string };

export interface UseSpcodeFileWrite {
  isSaving: import("vue").Ref<boolean>;
  save: (params: { path: string; content: string }) => Promise<FileWriteResult>;
  dispose: () => void;
}

export function useSpcodeFileWrite(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeFileWrite {
  const spcodeStatus = useSpcodeProjectStatus();
  const isSaving = ref(false);
  let ctrl: AbortController | null = null;
  let isMounted = true;

  async function save(params: {
    path: string;
    content: string;
  }): Promise<FileWriteResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    ctrl?.abort();
    ctrl = new AbortController();
    isSaving.value = true;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/file-write",
        {
          path: params.path,
          content: params.content,
          umo: spcodeStatus.status.value.umo ?? undefined,
          worktree: toValue(worktreeRef) ?? undefined,
        },
        { signal: ctrl.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      // Envelope semantics mirror extractFailureReason in
      // useSpcodeDocs: `saved === true` is the success marker; a
      // non-empty `reason` without the marker is a genuine failure;
      // anything unrecognized is treated as success.
      const data = (
        resp.data as {
          data?: { saved?: boolean; reason?: string | null };
        }
      )?.data;
      if (
        data &&
        data.saved !== true &&
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
      if (isMounted) isSaving.value = false;
    }
  }

  function dispose(): void {
    isMounted = false;
    ctrl?.abort();
    ctrl = null;
  }

  return { isSaving, save, dispose };
}
