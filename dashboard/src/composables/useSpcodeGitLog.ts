// Author: elecvoid243
// Date: 2026-06-24
// Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §3, §5
//
// Vue composable wrapping GET /spcode/git-log. Lifecycle mirrors
// useSpcodeGitDiff.ts. Adds two spcode-specific concerns on top:
//
//   1. **ETag 1.5s cache** — keyed by `umo + worktree + ref + path +
//      author + since + until + n` (spec decision #5 / #25). On a hit
//      (status 304) we return the previous successful snapshot and
//      do not transition to `loading`.
//
//   2. **10s polling** — like useSpcodeGitDiff; only started by the
//      orchestrator (GitDiffSidebar) when the user is in the
//      History view AND the sidebar is open.

import {
  ref,
  watch,
  toValue,
  type Ref,
  type MaybeRef,
} from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import {
  parseSpcodeGitLog,
  type SpcodeLogSnapshot,
  type SpcodeLogCommit,
} from "./parseSpcodeGitWorkflow";

export type LogFilter = {
  ref?: string;
  path?: string;
  author?: string;
  since?: string;
  until?: string;
  n?: number;
};

/** Spec §3.3.5:完整状态机
 *   idle ─refresh──> loading
 *   loading ─200──> ok { snapshot, notModified: false }
 *   loading ─304──> ok { snapshot, notModified: true } (snapshot 来自 prevSnapshot)
 *   loading ─err──> error { reason, previousSnapshot? }
 *
 * `notModified` 字段(spec 公开 API 表面,§3.3.5):UI 端**当前**通过
 * `state.kind === "loading"` 即可正确实现 "304 不显示 loading" 的需求
 * (state 不会进 loading,见 refresh 里的 304 短路),不读 notModified。
 * 该字段保留为公开 spec 契约,供未来 UI 实现 "fresh 时间戳 / 数据未变
 * 指示" 之类的派生(例如 commit 时间线缓存指示器)。删它会与 spec
 * §3.3.5 的状态机定义产生 drift,所以保留。
 */
export type LogFetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; snapshot: SpcodeLogSnapshot; notModified?: boolean }
  | { kind: "error"; reason: string; previousSnapshot?: SpcodeLogSnapshot };

export interface UseSpcodeGitLog {
  state: Ref<LogFetchState>;
  filter: Ref<LogFilter>;
  refresh: (
    override?: Partial<LogFilter>,
    options?: { forceLoading?: boolean },
  ) => Promise<void>;
  loadMore: () => Promise<void>;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
  /** Spec §3.4 决策 #24:切 worktree / 切 umo 时清空 ETag Map */
  invalidateEtag: () => void;
  /** Drop the ETag entry for one filter tuple only. Used by the
   *  GitLogView "Reset" button so a reset doesn't 304 against a
   *  stale ETag and replay an older (e.g. author=alice-filtered)
   *  snapshot — the reset URL matches the original history-load
   *  URL bit-for-bit, so without this the 304 branch wins and
   *  commits come back filtered. Spec §6.5.1 reset behavior. */
  invalidateEtagFor: (filter: LogFilter) => void;
  dispose: () => void;
}

const DEFAULT_N = 20;
const MAX_N = 200;
const DEFAULT_POLL_MS = 10_000;
const EMPTY_RECENT: SpcodeLogCommit[] = [];

/** Build the ETag Map key. Components don't all need to be present;
 *  any subset is a stable key for that filter combination. */
function etagKey(parts: {
  umo: string | null;
  worktree: string | null;
  filter: LogFilter;
}): string {
  const f = parts.filter;
  return [
    parts.umo ?? "",
    parts.worktree ?? "",
    f.ref ?? "HEAD",
    f.path ?? "",
    f.author ?? "",
    f.since ?? "",
    f.until ?? "",
    String(f.n ?? DEFAULT_N),
  ].join("|");
}

export function useSpcodeGitLog(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeGitLog {
  const state = ref<LogFetchState>({ kind: "idle" });
  const filter = ref<LogFilter>({ ref: "HEAD", n: DEFAULT_N });
  const spcodeStatus = useSpcodeProjectStatus();
  const etagMap = new Map<string, string>();
  let prevSnapshot: SpcodeLogSnapshot | null = null;
  let abortController: AbortController | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let isMounted = true;

  async function refresh(
    override?: Partial<LogFilter>,
    options?: { forceLoading?: boolean },
  ): Promise<void> {
    if (!isMounted) return;
    if (override) {
      // Replace (not merge) the filter for predictable behavior: explicit
      // overrides from "Apply" should reset the entire query.
      filter.value = { ref: "HEAD", n: DEFAULT_N, ...override };
    }
    const umo = spcodeStatus.status.value.umo;
    if (!umo) {
      const prev = prevSnapshot ?? undefined;
      state.value = { kind: "error", reason: "no_project_loaded", previousSnapshot: prev };
      return;
    }
    abortController?.abort();
    abortController = new AbortController();
    // isFirst covers the very first fetch (idle/error → loading). forceLoading
    // covers user-initiated re-fetches that want to give visual feedback even
    // when the previous state was already ok — e.g. the History view's Reset
    // button, which otherwise would not show a spinner while the request is
    // in flight and reads as "nothing happened".
    const isFirst = state.value.kind !== "ok";
    if (isFirst || options?.forceLoading) state.value = { kind: "loading" };

    const worktree = toValue(worktreeRef);
    const key = etagKey({ umo, worktree, filter: filter.value });
    const etag = etagMap.get(key);

    try {
      const resp = await pluginExtensionApi.get<unknown>(
        "spcode/git-log",
        {
          params: {
            umo,
            ...(worktree ? { worktree } : {}),
            ...(filter.value.ref ? { ref: filter.value.ref } : {}),
            ...(filter.value.path ? { path: filter.value.path } : {}),
            ...(filter.value.author ? { author: filter.value.author } : {}),
            ...(filter.value.since ? { since: filter.value.since } : {}),
            ...(filter.value.until ? { until: filter.value.until } : {}),
            n: filter.value.n ?? DEFAULT_N,
          },
          headers: etag ? { "If-None-Match": etag } : {},
          // Allow axios to surface 304 as a valid response so we can
          // branch on it (default behavior would throw an AxiosError).
          validateStatus: (s) => (s >= 200 && s < 300) || s === 304,
          signal: abortController.signal,
        },
      );
      if (!isMounted) return;

      if (resp.status === 304) {
        // 命中 ETag,复用上次 snapshot(spec §3.3.5)
        if (prevSnapshot) {
          state.value = { kind: "ok", snapshot: prevSnapshot, notModified: true };
        }
        // No prevSnapshot yet (theoretical race: 304 before any 200
        // — shouldn't happen but defensively fall through to loading).
        return;
      }

      const parsed = parseSpcodeGitLog(resp.data);
      if (parsed.kind !== "ok") {
        // Store the raw ReasonCode string. The template builds the
        // i18n key as `…error.reason.${reason}` — if `reason` is
        // already the i18nKey, the concatenation produces a non-
        // existent 6-segment path and the user sees the raw key.
        // The `no_project_loaded` branch above (line ~117) stores a
        // raw code; this branch must match.
        state.value = {
          kind: "error",
          reason: "unknown",
          previousSnapshot: prevSnapshot ?? undefined,
        };
        return;
      }
      const snap = parsed.snapshot;
      // Spec §5.1 (P0-3 fix): empty_repository is not a real error but a
      // discriminated "empty" state. The backend returns HTTP 200 with
      // snapshot.reason = "empty_repository"; we MUST convert it to
      // { kind: "error", reason: "empty_repository" } so:
      //   - GitLogView.isEmptyRepository computed (= kind === "error" &&
      //     reason === "empty_repository") fires and renders the empty-repo
      //     illustration (mdi-source-branch + emptyRepository i18n).
      //   - GitLogView error banner check `errorReason && !isEmptyRepository`
      //     correctly suppresses the generic error banner.
      //   - No snackbar is triggered (we never call showSnackbar in this
      //     transition path), so the user does NOT see a red toast.
      // We do NOT save this snapshot to prevSnapshot — 304 after empty_repo
      // should fall through (the prevSnapshot check at line ~150 only uses
      // prevSnapshot for the cache; the empty-illustration state requires
      // kind === "error" which only happens here, not on 304 replay).
      if (snap.reason === "empty_repository") {
        state.value = {
          kind: "error",
          reason: "empty_repository",
          previousSnapshot: prevSnapshot ?? undefined,
        };
        return;
      }
      prevSnapshot = snap;

      // Update ETag from response header if present.
      const newEtag = (resp.headers as Record<string, string> | undefined)?.["etag"]
        ?? (resp.headers as Record<string, string> | undefined)?.["ETag"];
      if (newEtag) etagMap.set(key, newEtag);

      state.value = { kind: "ok", snapshot: snap, notModified: false };
    } catch (err) {
      if (!isMounted) return;
      if ((err as { name?: string })?.name === "CanceledError") return;
      const anyErr = err as { code?: string; message?: string };
      // Store the raw ReasonCode string (see the matching comment in
      // the parse-failure branch above).
      const reason =
        anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")
          ? "network"
          : "unknown";
      state.value = {
        kind: "error",
        reason,
        previousSnapshot: prevSnapshot ?? undefined,
      };
    }
  }

  async function loadMore(): Promise<void> {
    // Double n up to MAX_N, then refresh. Spec §6.5.3.
    const currentN = filter.value.n ?? DEFAULT_N;
    const nextN = Math.min(MAX_N, currentN * 2);
    if (nextN === currentN) return; // already at max
    await refresh({ ...filter.value, n: nextN });
  }

  function startPolling(intervalMs: number = DEFAULT_POLL_MS): void {
    if (pollTimer) return;
    pollTimer = setInterval(() => {
      void refresh();
    }, intervalMs);
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function invalidateEtag(): void {
    // Spec §3.4 决策 #24 — 切 worktree / 切 umo 时调用
    etagMap.clear();
    // 不重置 prevSnapshot:切 worktree 后新请求可能产生新 snapshot,
    // prevSnapshot 仅作为 304 命中兜底;切 worktree 后即便收到 304
    // 也属新上下文,UI 应当 re-render。最安全的做法是同时清空。
    prevSnapshot = null;
  }

  /** Drop the ETag entry for exactly the given filter tuple (others are
   *  preserved). See the matching JSDoc on the public interface. */
  function invalidateEtagFor(target: LogFilter): void {
    const umo = spcodeStatus.status.value.umo;
    const worktree = toValue(worktreeRef);
    const key = etagKey({ umo, worktree, filter: target });
    etagMap.delete(key);
  }

  // Re-fetch when worktree changes (or umo changes — handled by caller
  // typically by invalidating ETag then calling refresh). We watch
  // worktree only; the orchestrator owns the umo-change lifecycle.
  watch(
    () => toValue(worktreeRef),
    () => {
      if (isMounted) void refresh();
    },
    { flush: "post" },
  );

  function dispose(): void {
    isMounted = false;
    stopPolling();
    abortController?.abort();
    abortController = null;
    etagMap.clear();
    prevSnapshot = null;
  }

  return {
    state,
    filter,
    refresh,
    loadMore,
    startPolling,
    stopPolling,
    invalidateEtag,
    invalidateEtagFor,
    dispose,
  };
}

// Re-export for templates that need a stable empty array
export { EMPTY_RECENT };
