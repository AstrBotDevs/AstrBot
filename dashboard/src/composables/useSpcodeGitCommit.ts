// Author: elecvoid243
// Date: 2026-06-24
// Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §3, §5
//
// Vue composable wrapping POST /spcode/git-commit. Lifecycle mirrors
// useSpcodeFileRestore.ts. Unlike stage/unstage, commit has only ONE
// in-flight call at a time (the user types a message and confirms), so
// the state surface is a single boolean (isCommitting) instead of a
// Set<string>.

import { ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeGitCommit,
  type SpcodeCommitSnapshot,
} from "./parseSpcodeGitWorkflow";

export interface UseSpcodeGitCommit {
  isCommitting: import("vue").Ref<boolean>;
  commit: (params: CommitParams) => Promise<CommitResult>;
  dispose: () => void;
}

export interface CommitParams {
  message: string;
  worktree?: string | null;
  umo?: string | null;
}

export type CommitResult =
  | { ok: true; snapshot: SpcodeCommitSnapshot }
  | { ok: false; reason: string; stderr?: string };

export function useSpcodeGitCommit(): UseSpcodeGitCommit {
  const isCommitting = ref(false);
  let abortController: AbortController | null = null;
  let isMounted = true;

  async function commit(params: CommitParams): Promise<CommitResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    abortController?.abort();
    abortController = new AbortController();
    isCommitting.value = true;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-commit",
        {
          message: params.message,
          ...(params.worktree ? { worktree: params.worktree } : {}),
          ...(params.umo ? { umo: params.umo } : {}),
        },
        { signal: abortController.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeGitCommit(resp.data);
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
      if (isMounted) isCommitting.value = false;
    }
  }

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
  }

  return { isCommitting, commit, dispose };
}
