// Author: elecvoid243, 2026-07-16
// Spec: docs/superpowers/specs/2026-07-16-git-repo-init-prompt-design.md §State Machine
//
// Single-purpose composable that owns the "is the loaded directory a Git
// repo?" question. State is intentionally minimal — branch lists, files,
// and the rest are owned by other composables. This one only knows about
// `ok` / `not_a_git_repo` / `error` and the `defaultBranch` name.

import { ref, watch, type Ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { parseSpcodeGitRepoProbe, type GitRepoProbeParseResult } from "./parseSpcodeGitRepoProbe";

export type GitRepoProbeState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; defaultBranch: string | null }
  | { kind: "not_a_git_repo"; directory: string }
  | { kind: "error"; reason: string; stderr?: string };

export interface GitInitParams {
  path: string;
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

const ETAG_KEY_PREFIX = "astrbot.spcode.gitRepoProbe.etag";
const SNAPSHOT_KEY_PREFIX = "astrbot.spcode.gitRepoProbe.snapshot";

/** Composable for the "is this a Git repo?" probe + init mutation. */
export function useSpcodeGitRepoProbe(): UseSpcodeGitRepoProbe {
  const state = ref<GitRepoProbeState>({ kind: "idle" });
  const spcodeStatus = useSpcodeProjectStatus();
  let abortController: AbortController | null = null;
  let initAbort: AbortController | null = null;
  let isMounted = true;

  function cacheKey(umo: string, worktree: string | null | undefined): string {
    return `${umo}.${worktree ?? ""}`;
  }

  function readCachedEtag(key: string): string | null {
    try {
      return localStorage.getItem(`${ETAG_KEY_PREFIX}.${key}`);
    } catch {
      return null;
    }
  }
  function writeCachedEtag(key: string, etag: string): void {
    try {
      localStorage.setItem(`${ETAG_KEY_PREFIX}.${key}`, etag);
    } catch {
      /* no-op */
    }
  }
  function clearCachedEtag(key: string): void {
    try {
      localStorage.removeItem(`${ETAG_KEY_PREFIX}.${key}`);
      localStorage.removeItem(`${SNAPSHOT_KEY_PREFIX}.${key}`);
    } catch {
      /* no-op */
    }
  }
  function readCachedSnapshot<T>(key: string): T | null {
    try {
      const raw = localStorage.getItem(`${SNAPSHOT_KEY_PREFIX}.${key}`);
      return raw ? (JSON.parse(raw) as T) : null;
    } catch {
      return null;
    }
  }
  function writeCachedSnapshot(key: string, value: unknown): void {
    try {
      localStorage.setItem(`${SNAPSHOT_KEY_PREFIX}.${key}`, JSON.stringify(value));
    } catch {
      /* no-op */
    }
  }

  async function refresh(): Promise<void> {
    if (!isMounted) return;
    const umo = spcodeStatus.status.value.umo;
    if (!umo) {
      state.value = { kind: "error", reason: "no_project_loaded" };
      return;
    }
    const key = cacheKey(umo, null);
    const cachedEtag = readCachedEtag(key);

    abortController?.abort();
    abortController = new AbortController();
    state.value = { kind: "loading" };
    try {
      // Axios treats 304 as an error by default (`validateStatus` accepts
      // 2xx only). ETag-driven 304 is a normal cache hit for the probe
      // endpoint, so we widen the accepted range to include 304 and let
      // the 304 path below handle it explicitly.
      const resp = await pluginExtensionApi.get<unknown>("spcode/git-branches", {
        params: { umo },
        signal: abortController.signal,
        validateStatus: (s) => (s >= 200 && s < 300) || s === 304,
        ...(cachedEtag ? { headers: { "If-None-Match": cachedEtag } } : {}),
      });
      if (!isMounted) return;

      // 304 path: server confirmed the cached ETag is still valid.
      const httpStatus = (resp as { status?: number }).status;
      if (httpStatus === 304) {
        const cached = readCachedSnapshot<{ defaultBranch: string | null }>(key);
        state.value = {
          kind: "ok",
          defaultBranch: cached?.defaultBranch ?? null,
        };
        return;
      }

      // AxiosResponse.headers is a wide union (RawAxiosRequestHeaders |
      // AxiosHeaders | string | number | ...). Narrow at runtime: only
      // the AxiosHeaders variant has a `.get()` method, so the optional
      // chain `?.get?.()` is the safest access.
      const headers = resp.headers as
        | { get?: (name: string) => string | null }
        | undefined;
      const newEtag = headers?.get?.("etag") ?? null;
      if (newEtag) {
        writeCachedEtag(key, newEtag);
      }
      // The OpenAPI client (configured with `throwOnError: true`) returns
      // the raw AxiosResponse — its `.data` is the JSON body the plugin
      // sent, which is `{ status, data: T }` for our endpoints. Unwrap
      // `.data.data` to hand the parser the inner payload. This matches
      // the convention used by every other composable in this codebase
      // (useSpcodeGitDiff, useSpcodeGitStatus, useSpcodeFileBrowser, …).
      const inner = (resp as { data?: { data?: unknown } }).data?.data;
      const parsed: GitRepoProbeParseResult =
        parseSpcodeGitRepoProbe(inner);
      applyParsed(parsed, key);
    } catch (err) {
      if (!isMounted) return;
      if ((err as { name?: string })?.name === "CanceledError") return;
      state.value = {
        kind: "error",
        reason: classifyNetworkError(err),
      };
    }
  }

  function applyParsed(parsed: GitRepoProbeParseResult, cacheKey_: string): void {
    if (parsed.kind === "ok") {
      writeCachedSnapshot(cacheKey_, { defaultBranch: parsed.defaultBranch });
      state.value = { kind: "ok", defaultBranch: parsed.defaultBranch };
    } else if (parsed.kind === "not_a_git_repo") {
      clearCachedEtag(cacheKey_);
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
    const umo = spcodeStatus.status.value.umo;
    if (!umo) return { ok: false, reason: "no_project_loaded" };

    initAbort?.abort();
    initAbort = new AbortController();
    state.value = { kind: "loading" };
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-init",
        { path: params.path, initial_branch: "main", bare: false },
        { signal: initAbort.signal, params: { umo } },
      );
      if (!isMounted || initAbort.signal.aborted) {
        return { ok: false, reason: "aborted" };
      }
      // Unwrap the OpenAPI envelope (see same comment in refresh()).
      // Without this, parseGitInitResponse sees `{status: "ok", data: …}`
      // and never matches `reason === null` because `reason` lives one
      // level deeper inside `data`.
      const envelope = (resp as { data?: { data?: unknown } }).data?.data;
      const result = parseGitInitResponse(envelope);
      if (!result.ok) {
        // Failure: the directory is still not a Git repo. Restore the
        // `not_a_git_repo` state synchronously so the prompt stays
        // visible; do NOT re-probe (the result is already authoritative).
        state.value = { kind: "not_a_git_repo", directory: params.path };
        return result;
      }
      // Success: invalidate cache and re-probe.
      clearCachedEtag(cacheKey(umo, null));
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

  // Re-probe when umo or directory changes.
  watch(
    () => [spcodeStatus.status.value.umo, spcodeStatus.status.value.directory] as const,
    ([newUmo, newDir], [oldUmo, oldDir]) => {
      if (!isMounted) return;
      if (newUmo && (newUmo !== oldUmo || newDir !== oldDir)) {
        void refresh();
      }
    },
  );

  return { state, refresh, gitInit, dispose };
}

function parseGitInitResponse(raw: unknown): GitInitResult {
  // `raw` here is the INNER payload of the OpenAPI envelope
  // `{ status, data: T }`, after the composable has unwrapped via
  // `resp.data?.data`. The backend's `_make_envelope` never emits a
  // `success` field; success is conveyed solely by `reason: null` at
  // the top level of this inner payload. Endpoint-specific fields
  // such as `initial_branch` also live at the top level of THIS inner
  // object, not under another nested `data` key.
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
