// Author: elecvoid243, 2026-07-16 (updated 2026-07-16 for git-repo-check)
// Spec: docs/api/webapi-git-repo-check-api.md
//
// Single-purpose composable that owns the "is the loaded directory a Git
// repo?" question. State is intentionally minimal - branch lists, files,
// and the rest are owned by other composables. This one only knows about
// `ok` / `not_a_git_repo` / `error`.
//
// v2.18.0: switched from `GET /spcode/git-branches` (umo-dependent) to
// `GET /spcode/git-repo-check` (path-dependent). The new endpoint is a
// pure function of `path` - no umo, no project-load state, no ETag. This
// eliminates the timing gap where `setLoaded()` flips `loaded=true` but
// `umo` is still null (the backend's `git-branches` preflight required
// umo, so the probe short-circuited and `isGitRepo` stayed false).

import { ref, watch, type Ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { parseSpcodeGitRepoProbe, type GitRepoProbeParseResult } from "./parseSpcodeGitRepoProbe";

export type GitRepoProbeState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; directory: string }
  | { kind: "not_a_git_repo"; directory: string }
  | { kind: "error"; reason: string; stderr?: string };

export interface GitInitParams {
  path: string;
  /**
   * v2.17.1: when true, the backend skips the "non-empty directory"
   * check and runs `git init` in-place, turning an existing project
   * directory into a Git-managed repo. Defaults to false at the
   * transport layer so the same composable still works for the
   * "create a brand-new empty repo" case if it ever needs to.
   * Callers that target a loaded spcode project should pass `true`:
   * the directory already exists, so "init" really means "convert".
   */
  force?: boolean;
}

export type GitInitResult =
  | { ok: true; defaultBranch: string }
  | { ok: false; reason: string; stderr?: string };

export interface UseSpcodeGitRepoProbe {
  state: Ref<GitRepoProbeState>;
  refresh: () => Promise<void>;
  gitInit: (params: GitInitParams) => Promise<GitInitResult>;
  dispose: () => void;
}

/** Composable for the "is this a Git repo?" probe + init mutation. */
export function useSpcodeGitRepoProbe(): UseSpcodeGitRepoProbe {
  const state = ref<GitRepoProbeState>({ kind: "idle" });
  const spcodeStatus = useSpcodeProjectStatus();
  let abortController: AbortController | null = null;
  let initAbort: AbortController | null = null;
  let isMounted = true;

  async function refresh(): Promise<void> {
    if (!isMounted) return;
    const directory = spcodeStatus.status.value.directory;
    if (!directory) {
      state.value = { kind: "idle" };
      return;
    }

    abortController?.abort();
    abortController = new AbortController();
    state.value = { kind: "loading" };
    try {
      const resp = await pluginExtensionApi.get<unknown>(
        "spcode/git-repo-check",
        {
          params: { path: directory },
          signal: abortController.signal,
        },
      );
      if (!isMounted) return;
      const inner = (resp as { data?: { data?: unknown } }).data?.data;
      const parsed: GitRepoProbeParseResult = parseSpcodeGitRepoProbe(inner);
      applyParsed(parsed);
    } catch (err) {
      if (!isMounted) return;
      if ((err as { name?: string })?.name === "CanceledError") return;
      state.value = {
        kind: "error",
        reason: classifyNetworkError(err),
      };
    }
  }

  function applyParsed(parsed: GitRepoProbeParseResult): void {
    if (parsed.kind === "ok") {
      state.value = { kind: "ok", directory: parsed.directory };
    } else if (parsed.kind === "not_a_git_repo") {
      state.value = { kind: "not_a_git_repo", directory: parsed.directory };
    } else {
      state.value = {
        kind: "error",
        reason: parsed.reason,
        ...(parsed.stderr !== undefined ? { stderr: parsed.stderr } : {}),
      };
    }
  }

  async function gitInit(params: GitInitParams): Promise<GitInitResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };

    initAbort?.abort();
    initAbort = new AbortController();
    state.value = { kind: "loading" };
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-init",
        {
          path: params.path,
          initial_branch: "main",
          bare: false,
          force: params.force ?? false,
        },
        { signal: initAbort.signal },
      );
      if (!isMounted || initAbort.signal.aborted) {
        return { ok: false, reason: "aborted" };
      }
      const envelope = (resp as { data?: { data?: unknown } }).data?.data;
      const result = parseGitInitResponse(envelope);
      if (!result.ok) {
        state.value = { kind: "not_a_git_repo", directory: params.path };
        return result;
      }
      // Success: re-probe via git-repo-check to confirm.
      await refresh();
      return result;
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      return { ok: false, reason: classifyNetworkError(err) };
    }
  }

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
    initAbort?.abort();
    initAbort = null;
  }

  // Re-probe when the loaded directory changes. The new endpoint is a
  // pure function of `path`, so we only need to watch `directory` (not
  // `umo`). This covers both initial project load and project switches.
  watch(
    () => spcodeStatus.status.value.directory,
    (newDir, oldDir) => {
      if (!isMounted) return;
      if (newDir && newDir !== oldDir) {
        void refresh();
      }
    },
  );

  return { state, refresh, gitInit, dispose };
}

function parseGitInitResponse(raw: unknown): GitInitResult {
  if (typeof raw !== "object" || raw === null) {
    return { ok: false, reason: "unknown" };
  }
  const env = raw as Record<string, unknown>;
  const reason = typeof env.reason === "string" ? env.reason : null;
  const stderr = typeof env.stderr === "string" ? env.stderr : undefined;
  if (reason === null) {
    const initialBranch =
      typeof env.initial_branch === "string" ? env.initial_branch : "main";
    return { ok: true, defaultBranch: initialBranch };
  }
  return {
    ok: false,
    reason,
    ...(stderr !== undefined ? { stderr } : {}),
  };
}

function classifyNetworkError(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const anyErr = err as { code?: string; message?: string };
    if (anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")) {
      return "network";
    }
  }
  return "unknown";
}
