// Author: elecvoid243
// Date: 2026-07-07
// Spec: docs/superpowers/specs/2026-07-07-hunk-discard-design.md §4.2

import { ref, type Ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeFileDiscardHunk,
  classifyDiscardHunkReason,
  type SpcodeFileDiscardHunkSnapshot,
} from "./parseSpcodeFileDiscardHunk";

export interface DiscardHunkParams {
  file: string;
  hunkIndex: number;
  patchText: string;
  worktree?: string | null;
  umo?: string | null;
}

export type DiscardHunkResult =
  | { ok: true; snapshot: SpcodeFileDiscardHunkSnapshot }
  | { ok: false; reason: string; stderr?: string };

export interface UseSpcodeFileDiscardHunk {
  /** Key format: `${file}#${hunkIndex}`. Per-hunk loading state. */
  isDiscardingHunk: Ref<Set<string>>;
  discard: (params: DiscardHunkParams) => Promise<DiscardHunkResult>;
  dispose: () => void;
}

export function useSpcodeFileDiscardHunk(): UseSpcodeFileDiscardHunk {
  const isDiscardingHunk = ref<Set<string>>(new Set());
  let abortController: AbortController | null = null;
  let isMounted = true;

  async function discard(params: DiscardHunkParams): Promise<DiscardHunkResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    abortController?.abort();
    abortController = new AbortController();
    const key = `${params.file}#${params.hunkIndex}`;
    const next = new Set(isDiscardingHunk.value);
    next.add(key);
    isDiscardingHunk.value = next;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/file-discard-hunk",
        {
          file: params.file,
          patch_text: params.patchText,
          ...(params.worktree ? { worktree: params.worktree } : {}),
          ...(params.umo ? { umo: params.umo } : {}),
        },
        { signal: abortController.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeFileDiscardHunk(resp.data);
      if (parsed.kind !== "ok") {
        return { ok: false, reason: classifyDiscardHunkReason(null) };
      }
      const snap = parsed.snapshot;
      if (snap.discarded) {
        return { ok: true, snapshot: snap };
      }
      return {
        ok: false,
        reason: classifyDiscardHunkReason(snap.reason),
        stderr: snap.stderr || undefined,
      };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      const anyErr = err as { code?: string; message?: string };
      if (
        anyErr.code === "ERR_NETWORK" ||
        /network/i.test(anyErr.message ?? "")
      ) {
        return { ok: false, reason: "network" };
      }
      return { ok: false, reason: "unknown" };
    } finally {
      if (isMounted) {
        const after = new Set(isDiscardingHunk.value);
        after.delete(key);
        isDiscardingHunk.value = after;
      }
    }
  }

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
  }

  return { isDiscardingHunk, discard, dispose };
}