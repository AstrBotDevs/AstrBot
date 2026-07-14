// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.6
//
// Vue composable wrapping the 3 docs CRUD endpoints:
//   POST   /spcode/docs        — create/upsert
//   PATCH  /spcode/docs        — rename
//   DELETE /spcode/docs        — delete
//
// All three share the standard envelope (status + data). The
// composable surfaces an isSaving / isDeleting / isRenaming
// boolean each (mutually exclusive in practice — the UI does
// not trigger overlapping writes — but kept as 3 separate
// refs for clarity). Mirrors useSpcodeFileRestore's lifecycle.

import { ref, toValue, type MaybeRef } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";

export type DocsWriteResult =
  | { ok: true }
  | { ok: false; reason: string; stderr?: string };

export interface SaveParams {
  path: string;
  content: string;
}
export interface RenameParams {
  path: string;
  newPath: string;
}

export interface UseSpcodeDocs {
  isSaving: import("vue").Ref<boolean>;
  isDeleting: import("vue").Ref<boolean>;
  isRenaming: import("vue").Ref<boolean>;
  save(params: SaveParams): Promise<DocsWriteResult>;
  remove(path: string): Promise<DocsWriteResult>;
  rename(params: RenameParams): Promise<DocsWriteResult>;
  dispose(): void;
}

function extractFailureReason(
  envelope: unknown,
): { reason: string; stderr?: string } | null {
  if (!envelope || typeof envelope !== "object") return null;
  // Backend `_make_envelope` (webapi/_helpers.py:233) consumes the
  // `success` kwarg as a logical flag but does NOT echo it into the
  // response data — each endpoint instead sets its own success marker
  // (POST → `saved`, PATCH → `renamed`, DELETE → `deleted`). The
  // legacy `data.success` field is kept in the signature for forward
  // compatibility but should not be required.
  const env = envelope as {
    data?: {
      success?: boolean;
      saved?: boolean;
      renamed?: boolean;
      deleted?: boolean;
      reason?: string | null;
      stderr?: string;
    };
  };
  const data = env.data;
  if (!data) return { reason: "unknown" };
  if (data.success === true) return null;
  // Endpoint-specific success markers. If any of them is true the
  // backend wrote/renamed/deleted the file even when the rest of the
  // envelope looks unfamiliar (e.g. older or in-flight additions).
  if (data.saved === true || data.renamed === true || data.deleted === true) {
    return null;
  }
  // No explicit success marker and a non-null `reason` → genuine
  // failure: surface the backend's reason code to the UI.
  if (typeof data.reason === "string" && data.reason) {
    return {
      reason: data.reason,
      stderr:
        typeof data.stderr === "string" && data.stderr ? data.stderr : undefined,
    };
  }
  // No success marker, no reason — treat as success rather than
  // introducing false-positive "unknown" failures. Matches the
  // semantics of every other parseSpcode* helper (unwrapEnvelope
  // returns `null` for unrecognized envelopes, not an error).
  return null;
}

function networkReason(err: unknown): string {
  const e = err as { name?: string; code?: string; message?: string };
  if (e?.name === "CanceledError") return "aborted";
  if (e?.code === "ERR_NETWORK" || /network/i.test(e?.message ?? "")) {
    return "network";
  }
  return "unknown";
}

export function useSpcodeDocs(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeDocs {
  const spcodeStatus = useSpcodeProjectStatus();
  const isSaving = ref(false);
  const isDeleting = ref(false);
  const isRenaming = ref(false);
  let saveCtrl: AbortController | null = null;
  let deleteCtrl: AbortController | null = null;
  let renameCtrl: AbortController | null = null;
  let isMounted = true;

  function commonParams() {
    return {
      umo: spcodeStatus.status.value.umo ?? undefined,
      worktree: toValue(worktreeRef) ?? undefined,
    };
  }

  async function save(params: SaveParams): Promise<DocsWriteResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    saveCtrl?.abort();
    saveCtrl = new AbortController();
    isSaving.value = true;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/docs",
        { path: params.path, content: params.content, ...commonParams() },
        { signal: saveCtrl.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const fail = extractFailureReason(resp.data);
      if (fail) return { ok: false, reason: fail.reason, stderr: fail.stderr };
      return { ok: true };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      return { ok: false, reason: networkReason(err) };
    } finally {
      if (isMounted) isSaving.value = false;
    }
  }

  async function remove(path: string): Promise<DocsWriteResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    deleteCtrl?.abort();
    deleteCtrl = new AbortController();
    isDeleting.value = true;
    try {
      // DELETE /spcode/docs accepts only {"path"} per contract §5.3
      // (umo/worktree are not in the handler signature; passing them
      // triggers invalid_params).
      const resp = await pluginExtensionApi.delete<unknown>("spcode/docs", {
        data: { path },
        signal: deleteCtrl.signal,
      });
      if (!isMounted) return { ok: false, reason: "aborted" };
      const fail = extractFailureReason(resp.data);
      if (fail) return { ok: false, reason: fail.reason, stderr: fail.stderr };
      return { ok: true };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      return { ok: false, reason: networkReason(err) };
    } finally {
      if (isMounted) isDeleting.value = false;
    }
  }

  async function rename(params: RenameParams): Promise<DocsWriteResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    renameCtrl?.abort();
    renameCtrl = new AbortController();
    isRenaming.value = true;
    try {
      // PATCH /spcode/docs accepts only {"path", "new_path"} per §5.2
      // (umo/worktree are not in the handler signature).
      const resp = await pluginExtensionApi.patch<unknown>(
        "spcode/docs",
        { path: params.path, new_path: params.newPath },
        { signal: renameCtrl.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const fail = extractFailureReason(resp.data);
      if (fail) return { ok: false, reason: fail.reason, stderr: fail.stderr };
      return { ok: true };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      return { ok: false, reason: networkReason(err) };
    } finally {
      if (isMounted) isRenaming.value = false;
    }
  }

  function dispose(): void {
    isMounted = false;
    saveCtrl?.abort();
    deleteCtrl?.abort();
    renameCtrl?.abort();
  }

  return { isSaving, isDeleting, isRenaming, save, remove, rename, dispose };
}
