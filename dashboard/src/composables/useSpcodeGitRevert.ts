// Author: elecvoid243
// Date: 2026-07-17
// API: docs/api/webapi-git-revert-api.md (plugin v2.17.0)
//
// Vue composable wrapping POST /spcode/git-revert. Lifecycle mirrors
// useSpcodeGitCommit.ts: a single in-flight call (the user confirms
// one revert at a time from the History view), one boolean state
// surface, abort-on-reentry, dispose on unmount.
//
// The endpoint runs `git revert --no-edit <ref>`: it creates a NEW
// revert commit (history is NOT rewritten), is non-idempotent, and
// rejects `no_edit !== true` — so the request body always pins
// `no_edit: true` and the caller only supplies the ref.

import { ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";

export interface UseSpcodeGitRevert {
  isReverting: import("vue").Ref<boolean>;
  revert: (params: RevertParams) => Promise<RevertResult>;
  dispose: () => void;
}

export interface RevertParams {
  /** commit-ish to revert (SHA from the log row in practice). */
  ref: string;
  worktree?: string | null;
  umo?: string | null;
}

export interface RevertSnapshot {
  /** Full SHA of the newly created revert commit ("" if re-read failed). */
  revertSha: string;
  /** Subject of the new commit, e.g. `Revert "feat: ..."`. */
  revertMessage: string;
  /** Repo-relative files touched by the revert commit. */
  filesTouched: string[];
}

export type RevertResult =
  | { ok: true; snapshot: RevertSnapshot }
  | { ok: false; reason: string; stderr?: string };

export function useSpcodeGitRevert(): UseSpcodeGitRevert {
  const isReverting = ref(false);
  let abortController: AbortController | null = null;
  let isMounted = true;

  async function revert(params: RevertParams): Promise<RevertResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    abortController?.abort();
    abortController = new AbortController();
    isReverting.value = true;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-revert",
        {
          ref: params.ref,
          // Headless endpoint: the editor must never open; the backend
          // rejects any other value with `invalid_param`.
          no_edit: true,
          ...(params.worktree ? { worktree: params.worktree } : {}),
          ...(params.umo ? { umo: params.umo } : {}),
        },
        { signal: abortController.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      // Inline parse (no dedicated parser file — the envelope is
      // shallow): success ⇔ data.reason === null && data.reverted.
      const data = (
        resp.data as {
          data?: {
            reverted?: boolean;
            reason?: string | null;
            stderr?: string;
            revert_sha?: string;
            revert_message?: string;
            files_touched?: unknown;
          };
        }
      )?.data;
      if (data && data.reason == null && data.reverted === true) {
        return {
          ok: true,
          snapshot: {
            revertSha: typeof data.revert_sha === "string" ? data.revert_sha : "",
            revertMessage:
              typeof data.revert_message === "string"
                ? data.revert_message
                : "",
            filesTouched: Array.isArray(data.files_touched)
              ? data.files_touched.filter(
                  (f): f is string => typeof f === "string",
                )
              : [],
          },
        };
      }
      // Failure envelope: reason is guaranteed on every failure path.
      return {
        ok: false,
        reason:
          typeof data?.reason === "string" && data.reason
            ? data.reason
            : "unknown",
        stderr:
          typeof data?.stderr === "string" && data.stderr
            ? data.stderr
            : undefined,
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
      if (isReverting.value && isMounted) isReverting.value = false;
    }
  }

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
  }

  return { isReverting, revert, dispose };
}
