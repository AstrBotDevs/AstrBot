// Author: elecvoid243
// Date: 2026-06-18
// Spec: docs/superpowers/specs/2026-06-18-git-worktree-switcher-design.md §3.3

import { ref, watch, type Ref } from 'vue'
import { pluginExtensionApi } from '@/api/v1'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'
import {
  parseSpcodeGitWorktrees,
  type SpcodeGitWorktreesSnapshot,
  type SpcodeGitWorktreesRawResponse,
  type SpcodeGitWorktreeRaw,
} from '@/composables/parseSpcodeWorktrees'
import {
  parseSpcodeWorktreeAdd,
  parseSpcodeWorktreeRemove,
  parseSpcodeWorktreeLock,
  parseSpcodeWorktreeUnlock,
} from '@/composables/parseSpcodeWorktreeManagement'

// ── Worktree management (spec 2026-06-27 §1.1) ──────────────

/** Parameters for the 4 mutation methods. All 4 share the same shape
 *  (path + optional context) so the consumer can pattern-match
 *  uniformly; the 4 parsers differ only in endpoint-specific
 *  response field interpretation. */
export interface WorktreeMgmtParams {
  /** Absolute path of the worktree to act on. For `add`, the new
   *  worktree's location; for the rest, the existing target. */
  path: string;
  /** Optional nested worktree context (rare; passed via ?worktree=
   *  query param to the backend). Aligns with §2.5 of the spcode spec. */
  worktree?: string | null;
  /** Session ID. Falls back to the composable's tracked umo if null. */
  umo?: string | null;
}

/** ADD-specific params (extends WorktreeMgmtParams with create/force/detach/base). */
export interface WorktreeAddParams extends WorktreeMgmtParams {
  branch?: string;
  create?: boolean;
  force?: boolean;
  detach?: boolean;
  base?: string;
}

/** REMOVE-specific params (extends with force for dirty bypass). */
export interface WorktreeRemoveParams extends WorktreeMgmtParams {
  force?: boolean;
}

/** LOCK-specific params (extends with reason). */
export interface WorktreeLockParams extends WorktreeMgmtParams {
  reason?: string;
}

/** Discriminated union return type for all 4 mutations. Mirrors the
 *  useSpcodeFileRestore pattern (ok / failure-with-reason+stderr). */
export type WorktreeMgmtResult =
  | { ok: true; snapshot: SpcodeGitWorktreesSnapshot }
  | { ok: false; reason: string; stderr?: string };

export type WorktreesFetchState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; snapshot: SpcodeGitWorktreesSnapshot }
  | {
      kind: 'error'
      reason: string
      previousSnapshot?: SpcodeGitWorktreesSnapshot
    }

export interface UseSpcodeWorktrees {
  state: Ref<WorktreesFetchState>
  refresh: () => Promise<void>
  /**
   * Start a polling timer that re-fetches the worktree list on a fixed
   * cadence. Used by the orchestrator (GitDiffSidebar) to surface
   * externally-driven worktree changes (e.g. the agent running
   * `git worktree add` while the user is staring at the sidebar).
   *
   * Idempotent: re-calling while a timer is already running is a no-op.
   */
  startPolling: (intervalMs?: number) => void
  /** Cancel the polling timer set by `startPolling`. Idempotent. */
  stopPolling: () => void
  /**
   * Add a new worktree. See `parseSpcodeWorktreeAdd` for the response
   * shape; on success, the returned snapshot's `worktrees` array is
   * the authoritative refreshed list and is swapped into `state` atomically.
   */
  add: (params: WorktreeAddParams) => Promise<WorktreeMgmtResult>
  /**
   * Remove an existing worktree. Frontend must NOT call this for the
   * main worktree (ui-side disabled); backend will refuse with
   * `cannot_remove_main` regardless. The `force` flag bypasses the
   * dirty check only (locked check is structural and is not bypassed).
   */
  remove: (params: WorktreeRemoveParams) => Promise<WorktreeMgmtResult>
  /** Lock a worktree. Optional `reason` is stored alongside the lock
   *  (git 2.30+); backend allows locking the main worktree but the
   *  UI hides the entry for it (see spec §11.2). */
  lock: (params: WorktreeLockParams) => Promise<WorktreeMgmtResult>
  /** Unlock a worktree. Non-idempotent: second unlock returns
   *  `not_locked`. UI should disable when `locked=false`. */
  unlock: (params: WorktreeMgmtParams) => Promise<WorktreeMgmtResult>
  dispose: () => void
}

/**
 * Polling cadence for the worktree list. Picked deliberately slower
 * than the diff/status/log cadence (10s) for two reasons:
 *
 *   1. **Worktree churn is rare.** Most sessions add/remove worktrees
 *      only at task boundaries (`/project load`, agent bootstrapping).
 *      30s is frequent enough to catch that within one human attention
 *      span, infrequent enough to avoid hitting the spcode plugin on
 *      every tab switch.
 *   2. **`git worktree list` is not free.** It shells out to git
 *      (porcelain v1) and walks `.git/worktrees/` on every call. A
 *      cheap refresh every 30s is the right cost/value trade-off;
 *      running it every 10s would 3x the I/O for a list that changes
 *      on the order of minutes, not seconds.
 */
const DEFAULT_POLL_MS = 30_000

/**
 * Composable for the worktree list.
 *
 * Per spec §3.3, this composable does NOT watch umo — it operates on the
 * loaded project's directory at refresh time. If no project is loaded,
 * it sets state to { kind: 'error', reason: 'no_project_loaded' }.
 *
 * The composable is per-instance (NOT a module-level singleton), matching
 * the useSpcodeGitDiff pattern. GitDiffSidebar instantiates one and
 * disposes it in onBeforeUnmount.
 *
 * **Polling** (added 2026-06-25, elecvoid243): the composable exposes
 * `startPolling(intervalMs?)` / `stopPolling()` to support the
 * "agent runs `git worktree add` while the user is looking at the
 * sidebar" scenario. The orchestrator (GitDiffSidebar) starts
 * polling at 30s cadence when the sidebar opens and stops it when
 * the sidebar closes. We deliberately keep worktree polling
 * decoupled from viewMode: the worktree list powers the tab
 * switcher across all three tabs (diff / files / history), so
 * tying its refresh cadence to a specific tab would be wrong.
 */
export function useSpcodeWorktrees(): UseSpcodeWorktrees {
  const state = ref<WorktreesFetchState>({ kind: 'idle' })
  const spcodeStatus = useSpcodeProjectStatus()
  let abortController: AbortController | null = null
  // Single-flight guard for mutation methods (separate from the read
  // path's `abortController` so a read in progress doesn't cancel a
  // pending write or vice versa).
  let mutationAbort: AbortController | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let isMounted = true

  async function refresh(): Promise<void> {
    if (!isMounted) return

    const umo = spcodeStatus.status.value.umo
    if (!umo) {
      const prev = state.value.kind === 'ok' ? state.value.snapshot : undefined
      state.value = {
        kind: 'error',
        reason: 'no_project_loaded',
        previousSnapshot: prev,
      }
      return
    }

    abortController?.abort()
    abortController = new AbortController()
    const isFirst = state.value.kind !== 'ok'
    if (isFirst) state.value = { kind: 'loading' }
    try {
      const resp = await pluginExtensionApi.get<SpcodeGitWorktreesRawResponse>(
        'spcode/git-worktrees',
        {
          params: { umo },
          signal: abortController.signal,
        },
      )
      if (!isMounted) return
      const data = resp.data?.data
      if (!data) throw new Error('empty response data')
      state.value = { kind: 'ok', snapshot: parseSpcodeGitWorktrees(data) }
    } catch (err) {
      if (!isMounted) return
      if ((err as { name?: string })?.name === 'CanceledError') return
      const prev = state.value.kind === 'ok' ? state.value.snapshot : undefined
      state.value = {
        kind: 'error',
        reason: classifyError(err),
        previousSnapshot: prev,
      }
    }
  }

  // Bug fix (2026-06-18): setLoaded() in useSpcodeProjectStatus does NOT
  // set `umo` (it only optimistically flips `loaded` and `directory`).
  // The authoritative umo arrives later via spcodeStatus.refresh() —
  // typically fired from Chat.vue's onStreamEnd after the bot processes
  // the /project load command. If the user opens GitDiffSidebar before
  // that refresh, our onMounted() call hits `umo = null` and short-circuits
  // (no network request is made). Without a watcher, the worktree list
  // would never load. Watch the module-level status ref and re-fetch as
  // soon as umo becomes available; the same hook also covers project
  // switches (directory change) so the tabs refresh on `/project load`.
  watch(
    () => spcodeStatus.status.value.umo,
    (newUmo, oldUmo) => {
      if (!isMounted) return
      if (newUmo && newUmo !== oldUmo) {
        void refresh()
      }
    },
  )
  watch(
    () => spcodeStatus.status.value.directory,
    (newDir, oldDir) => {
      if (!isMounted) return
      // Skip the very first assignment (handled by the umo watcher) and
      // skip empty transitions. Only re-fetch when the directory actually
      // changes from one non-null value to another.
      if (newDir && newDir !== oldDir && spcodeStatus.status.value.umo) {
        void refresh()
      }
    },
  )

  function startPolling(intervalMs: number = DEFAULT_POLL_MS): void {
    if (pollTimer) return
    pollTimer = setInterval(() => {
      void refresh()
    }, intervalMs)
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  // ── Worktree management methods (spec 2026-06-27 §3) ────────
  //
  // All 4 share the same shape: build a new AbortController (cancel
  // any in-flight read), POST to the endpoint, parse the response,
  // atomically swap `state.value` with the refreshed snapshot. The
  // parsers are imported from parseSpcodeWorktreeManagement.ts.
  //
  // **Single-flight policy**: each call aborts the previous
  // AbortController. This means rapid double-click → the first call
  // resolves as `aborted` (handled by the `isMounted` guard), the
  // second runs to completion. The orchestrator (GitDiffSidebar)
  // guards UI buttons with `isXxx` flags to make double-clicks
  // impossible at the UI level too (defense in depth).

  async function add(params: WorktreeAddParams): Promise<WorktreeMgmtResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    const umo = params.umo ?? spcodeStatus.status.value.umo;
    if (!umo) return { ok: false, reason: "no_project_loaded" };
    const ctrl = new AbortController();
    mutationAbort?.abort();
    mutationAbort = ctrl;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-worktree-add",
        {
          path: params.path,
          branch: params.branch,
          create: params.create,
          force: params.force,
          detach: params.detach,
          base: params.base,
        },
        {
          signal: ctrl.signal,
          params: { umo, worktree: params.worktree ?? undefined },
        },
      );
      if (!isMounted || ctrl.signal.aborted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeWorktreeAdd(resp.data);
      // Propagate the parser's reason+stderr verbatim. Previously this
      // branch hardcoded reason="unknown", which made every backend
      // failure look identical to the user and dropped the actual
      // git error message (relevant for failures like non-existent
      // base ref → "fatal: not a tree object: <base>").
      if (parsed.kind !== "ok") {
        return { ok: false, reason: parsed.reason, stderr: parsed.stderr };
      }
      // Atomically replace state with the refreshed list.
      // The cast is safe: parseSpcodeWorktreeManagement stored the
      // raw snake_case array verbatim (Chunk 1 leaves re-naming to
      // parseSpcodeGitWorktrees), so the data still has `head_sha` /
      // `is_main` at runtime even though the TS type says camelCase.
      const refreshed = parseSpcodeGitWorktrees({
        loaded: parsed.snapshot.meta.loaded,
        directory: parsed.snapshot.meta.directory,
        umo: parsed.snapshot.meta.umo,
        worktrees: parsed.snapshot.worktrees as unknown as SpcodeGitWorktreeRaw[],
        reason: parsed.snapshot.meta.reason,
        stderr: parsed.snapshot.meta.stderr,
        elapsed_ms: parsed.snapshot.meta.elapsedMs,
      });
      state.value = { kind: "ok", snapshot: refreshed };
      return { ok: true, snapshot: refreshed };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      return { ok: false, reason: classifyMutationError(err) };
    }
  }

  async function remove(params: WorktreeRemoveParams): Promise<WorktreeMgmtResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    const umo = params.umo ?? spcodeStatus.status.value.umo;
    if (!umo) return { ok: false, reason: "no_project_loaded" };
    const ctrl = new AbortController();
    mutationAbort?.abort();
    mutationAbort = ctrl;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-worktree-remove",
        { path: params.path, force: params.force },
        {
          signal: ctrl.signal,
          params: { umo, worktree: params.worktree ?? undefined },
        },
      );
      if (!isMounted || ctrl.signal.aborted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeWorktreeRemove(resp.data);
      if (parsed.kind !== "ok") {
        return { ok: false, reason: parsed.reason, stderr: parsed.stderr };
      }
      const refreshed = parseSpcodeGitWorktrees({
        loaded: parsed.snapshot.meta.loaded,
        directory: parsed.snapshot.meta.directory,
        umo: parsed.snapshot.meta.umo,
        worktrees: parsed.snapshot.worktrees as unknown as SpcodeGitWorktreeRaw[],
        reason: parsed.snapshot.meta.reason,
        stderr: parsed.snapshot.meta.stderr,
        elapsed_ms: parsed.snapshot.meta.elapsedMs,
      });
      state.value = { kind: "ok", snapshot: refreshed };
      return { ok: true, snapshot: refreshed };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      return { ok: false, reason: classifyMutationError(err) };
    }
  }

  async function lock(params: WorktreeLockParams): Promise<WorktreeMgmtResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    const umo = params.umo ?? spcodeStatus.status.value.umo;
    if (!umo) return { ok: false, reason: "no_project_loaded" };
    const ctrl = new AbortController();
    mutationAbort?.abort();
    mutationAbort = ctrl;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-worktree-lock",
        { path: params.path, reason: params.reason },
        {
          signal: ctrl.signal,
          params: { umo, worktree: params.worktree ?? undefined },
        },
      );
      if (!isMounted || ctrl.signal.aborted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeWorktreeLock(resp.data);
      if (parsed.kind !== "ok") {
        return { ok: false, reason: parsed.reason, stderr: parsed.stderr };
      }
      const refreshed = parseSpcodeGitWorktrees({
        loaded: parsed.snapshot.meta.loaded,
        directory: parsed.snapshot.meta.directory,
        umo: parsed.snapshot.meta.umo,
        worktrees: parsed.snapshot.worktrees as unknown as SpcodeGitWorktreeRaw[],
        reason: parsed.snapshot.meta.reason,
        stderr: parsed.snapshot.meta.stderr,
        elapsed_ms: parsed.snapshot.meta.elapsedMs,
      });
      state.value = { kind: "ok", snapshot: refreshed };
      return { ok: true, snapshot: refreshed };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      return { ok: false, reason: classifyMutationError(err) };
    }
  }

  async function unlock(params: WorktreeMgmtParams): Promise<WorktreeMgmtResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    const umo = params.umo ?? spcodeStatus.status.value.umo;
    if (!umo) return { ok: false, reason: "no_project_loaded" };
    const ctrl = new AbortController();
    mutationAbort?.abort();
    mutationAbort = ctrl;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-worktree-unlock",
        { path: params.path },
        {
          signal: ctrl.signal,
          params: { umo, worktree: params.worktree ?? undefined },
        },
      );
      if (!isMounted || ctrl.signal.aborted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeWorktreeUnlock(resp.data);
      if (parsed.kind !== "ok") {
        return { ok: false, reason: parsed.reason, stderr: parsed.stderr };
      }
      const refreshed = parseSpcodeGitWorktrees({
        loaded: parsed.snapshot.meta.loaded,
        directory: parsed.snapshot.meta.directory,
        umo: parsed.snapshot.meta.umo,
        worktrees: parsed.snapshot.worktrees as unknown as SpcodeGitWorktreeRaw[],
        reason: parsed.snapshot.meta.reason,
        stderr: parsed.snapshot.meta.stderr,
        elapsed_ms: parsed.snapshot.meta.elapsedMs,
      });
      state.value = { kind: "ok", snapshot: refreshed };
      return { ok: true, snapshot: refreshed };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      return { ok: false, reason: classifyMutationError(err) };
    }
  }

  function dispose(): void {
    isMounted = false
    stopPolling()
    abortController?.abort()
    abortController = null
    mutationAbort?.abort()
    mutationAbort = null
  }

  return { state, refresh, startPolling, stopPolling, add, remove, lock, unlock, dispose }
}

function classifyError(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const anyErr = err as { code?: string; message?: string }
    if (anyErr.code === 'ERR_NETWORK' || /network/i.test(anyErr.message ?? '')) {
      return 'network'
    }
  }
  return 'unknown'
}

function classifyMutationError(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const anyErr = err as { code?: string; message?: string };
    if (anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")) {
      return "network";
    }
  }
  return "unknown";
}
